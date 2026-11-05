"""Chronological hybrid retrieval shared by the local learner and Claude.

This module never embeds, trains on a corpus, calls an API, or reads query votes.
It combines externally supplied BGE cosine with stateless hashed word/bigram
cosine. Selection is label blind. At most two copies of the same normalized text
enter either the global or company pool; their union can contain up to four.
No vote-based balancing is performed. Historical votes are attached only after
selection. Meeting dates with a strict five-day lag proxy vote availability.
"""
from collections import Counter
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import HashingVectorizer
from threadpoolctl import threadpool_limits

from vector_model import KEY, META_FIELDS, MODEL, VOTES, _metadata, _vectors
from vote_features import normalize_text


VERSION = "hybrid-diverse-history-v1"
DEFAULT_DENSE_WEIGHT = 0.65
DEFAULT_MAX_PER_TEXT = 2
DEFAULT_TOP_K = 8
POLICY = "Historical meeting_date < query meeting_date - 5 days; own meeting excluded."
SCOPES = ("all", "global", "company")
STATS = (
    "count_log", "against_board_mean", "against_board_weighted",
    "against_board_recency_weighted", "first_against_board", "top3_against_board_mean",
    "top_score", "top_dense", "top_lexical", "latest_age_years", "mean_age_years",
    "unique_texts_log", "conflicting_votes", "conflicting_against_board",
)
FEATURE_NAMES = [f"hybrid_{scope}_{stat}" for scope in SCOPES for stat in STATS] + [
    f"hybrid_exact_{scope}_{stat}" for scope in ("all", "company")
    for stat in ("count_log", "against_board_mean", "conflicting_votes")
]


def _integer(value, name, minimum=1):
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _consistent_meetings(meta):
    if not meta.empty and meta.groupby("meeting_id")[["company_id", "company", "meeting_date"]].nunique().gt(1).any().any():
        raise ValueError("Meeting company/date metadata must be consistent")


class HybridHistoryRetriever:
    """Fixed lexical/dense scoring with deterministic, outcome-blind diversity.

    ``fit`` is an indexing operation, not vocabulary/IDF fitting. The label array
    stays separate from the allowlisted metadata used by ``select``. All score
    ties prefer the same company, then newer date, then canonical meeting/item.
    """

    def __init__(self, dense_weight=DEFAULT_DENSE_WEIGHT, max_per_text=DEFAULT_MAX_PER_TEXT):
        if isinstance(dense_weight, bool) or not np.isscalar(dense_weight):
            raise ValueError("dense_weight must be finite and between zero and one")
        try:
            dense_weight = float(dense_weight)
        except (TypeError, ValueError) as error:
            raise ValueError("dense_weight must be finite and between zero and one") from error
        if not np.isfinite(dense_weight) or not 0 <= dense_weight <= 1:
            raise ValueError("dense_weight must be finite and between zero and one")
        self.dense_weight = dense_weight
        self.max_per_text = _integer(max_per_text, "max_per_text")
        self.lexical = HashingVectorizer(n_features=2 ** 18, alternate_sign=False,
                                        ngram_range=(1, 2), stop_words="english", norm="l2")

    @property
    def configuration(self):
        return {"version": VERSION, "embedding_model": MODEL, "dense_weight": self.dense_weight,
                "lexical_weight": 1 - self.dense_weight, "lexical_features": 2 ** 18,
                "lexical_ngrams": [1, 2], "lexical_stop_words": "english",
                "max_per_normalized_text_per_pool": self.max_per_text,
                "history_policy": POLICY, "vocabulary_or_idf_fit": False}

    def fit(self, reference, embeddings):
        meta = _metadata(reference)
        _consistent_meetings(meta)
        if meta.empty or "nbim_vote" not in reference:
            raise ValueError("Nonempty historical references with known votes are required")
        votes = reference["nbim_vote"].reset_index(drop=True)
        if not votes.isin(VOTES).all() or not meta.mgmt_rec.isin(VOTES).all():
            raise ValueError("Historical NBIM and board votes must be known")
        vectors = _vectors(embeddings, len(meta))
        order = meta.sort_values(KEY, kind="stable").index.to_numpy()
        self.metadata = meta.iloc[order].reset_index(drop=True)
        self.embeddings = vectors[order]
        self.labels = votes.iloc[order].to_numpy(dtype=str)
        self.normalized_text = self.metadata.proposal_text.map(normalize_text).to_numpy()
        self.lexical_vectors = self.lexical.transform(self.metadata.proposal_text)
        self.dates = self.metadata.meeting_date.to_numpy(dtype="datetime64[D]")
        self.date_days = self.dates.astype(np.int64)
        self.companies = self.metadata.company_id.to_numpy()
        self.meetings = self.metadata.meeting_id.to_numpy()
        return self

    def _diverse(self, ranked, count):
        selected, seen, skipped = [], Counter(), 0
        for raw_index in ranked:
            index = int(raw_index)
            text = self.normalized_text[index]
            if seen[text] >= self.max_per_text:
                skipped += 1
                continue
            selected.append(index)
            seen[text] += 1
            if len(selected) == count:
                break
        return selected, skipped

    def select(self, query, embeddings, k_global=DEFAULT_TOP_K, k_company=DEFAULT_TOP_K):
        """Return selected canonical indices and scores, without consulting labels.

        This is useful for leakage tests. Query extra fields (including outcomes,
        rationales and externally supplied categories) are discarded by allowlist.
        References from the present/future never enter ranking or diversity.
        """
        if not hasattr(self, "embeddings"):
            raise ValueError("Fit the history index before retrieval")
        k_global = _integer(k_global, "k_global")
        k_company = _integer(k_company, "k_company")
        meta = _metadata(query)
        _consistent_meetings(meta)
        matrix = _vectors(embeddings, len(meta))
        lexical = self.lexical.transform(meta.proposal_text)
        results = []
        with threadpool_limits(limits=1):
            for start in range(0, len(meta), 128):
                dense_batch = np.clip(matrix[start:start + 128] @ self.embeddings.T, -1, 1)
                lexical_batch = np.clip((lexical[start:start + 128] @ self.lexical_vectors.T).toarray(), 0, 1)
                for offset, row in enumerate(meta.iloc[start:start + 128].to_dict("records")):
                    day = np.datetime64(row["meeting_date"], "D")
                    cutoff = day - np.timedelta64(5, "D")
                    same_company = self.companies == row["company_id"]
                    own_meeting = self.meetings == row["meeting_id"]
                    time_allowed = self.dates < cutoff
                    allowed = time_allowed & ~own_meeting & ~(same_company & (self.dates == day))
                    candidates = np.flatnonzero(allowed)
                    dense, lex = dense_batch[offset], lexical_batch[offset]
                    scores = self.dense_weight * dense + (1 - self.dense_weight) * lex
                    ranked = candidates[np.lexsort((candidates, -self.date_days[candidates],
                                                     ~same_company[candidates], -scores[candidates]))]
                    global_indices, global_skipped = self._diverse(ranked, k_global)
                    company_indices, company_skipped = self._diverse(ranked[same_company[ranked]], k_company)
                    chosen = set(global_indices) | set(company_indices)
                    # Overall score order also fixes the numeric features' top-k order.
                    chosen = [int(index) for index in ranked if int(index) in chosen]
                    matches = [{"index": index, "dense_similarity": float(dense[index]),
                                "lexical_similarity": float(lex[index]), "retrieval_score": float(scores[index]),
                                "selection": [scope for scope, indices in (("global", global_indices),
                                                                           ("company", company_indices)) if index in indices]}
                               for index in chosen]
                    audit = {"eligible_count": int(len(candidates)), "selected_count": len(chosen),
                             "excluded_time_count": int((~time_allowed).sum()),
                             "excluded_own_meeting_count": int(own_meeting.sum()),
                             "global_duplicate_skips": global_skipped, "company_duplicate_skips": company_skipped,
                             "selected_unique_texts": len({self.normalized_text[index] for index in chosen}),
                             "selected_distinct_meetings": len({str(self.meetings[index]) for index in chosen}),
                             "max_selected_date": max((str(self.dates[index]) for index in chosen), default=None),
                             "cutoff_violations": 0}
                    results.append({"meeting_id": row["meeting_id"], "item_no": row["item_no"],
                                    "query": row, "cutoff": str(cutoff), "eligible_count": int(len(candidates)),
                                    "matches": matches, "audit": audit})
        return results

    def retrieve(self, query, embeddings, k_global=DEFAULT_TOP_K, k_company=DEFAULT_TOP_K):
        """Attach only the selected earlier votes to the already fixed matches."""
        results = self.select(query, embeddings, k_global=k_global, k_company=k_company)
        records = self.metadata.to_dict("records")
        for result in results:
            attached = []
            for selected in result["matches"]:
                index = selected["index"]
                row = records[index]
                attached.append({**row, "id": f"{row['meeting_id']}:{row['item_no']}",
                                 "nbim_vote": str(self.labels[index]),
                                 **{key: value for key, value in selected.items() if key != "index"}})
            result["matches"] = attached
            validate_result(result)
        return results

    def features(self, query, embeddings, k_global=DEFAULT_TOP_K, k_company=DEFAULT_TOP_K):
        return features_from_results(self.retrieve(query, embeddings, k_global=k_global, k_company=k_company))


def validate_result(result):
    """Fail closed before a retrieved history is used as local or external input."""
    expected = {"meeting_id", "item_no", "query", "cutoff", "eligible_count", "matches", "audit"}
    if set(result) != expected or set(result["query"]) != set(META_FIELDS):
        raise ValueError("Unexpected retrieval or query fields")
    query = result["query"]
    if result["meeting_id"] != query["meeting_id"] or result["item_no"] != query["item_no"]:
        raise ValueError("Retrieval and query identities differ")
    cutoff = date.fromisoformat(query["meeting_date"]) - timedelta(days=5)
    if result["cutoff"] != cutoff.isoformat():
        raise ValueError("Incorrect decision cutoff")
    ids = set()
    for match in result["matches"]:
        if set(match) != {*META_FIELDS, "id", "nbim_vote", "dense_similarity", "lexical_similarity", "retrieval_score", "selection"}:
            raise ValueError("Unexpected historical fields")
        if match["id"] in ids or match["id"] != f"{match['meeting_id']}:{match['item_no']}":
            raise ValueError("Duplicate or incorrect historical identity")
        ids.add(match["id"])
        if (date.fromisoformat(match["meeting_date"]) >= cutoff or match["meeting_id"] == query["meeting_id"]):
            raise ValueError("Historical record crosses the decision cutoff")
        if match["nbim_vote"] not in VOTES or match["mgmt_rec"] not in VOTES:
            raise ValueError("Unknown historical vote")
        if not match["selection"] or len(set(match["selection"])) != len(match["selection"]) or not set(match["selection"]) <= {"global", "company"}:
            raise ValueError("Unknown or duplicate retrieval pool")
        if "company" in match["selection"] and match["company_id"] != query["company_id"]:
            raise ValueError("Company-pool history belongs to another company")
        for key in ("dense_similarity", "lexical_similarity", "retrieval_score"):
            if not isinstance(match[key], (float, int)) or not np.isfinite(match[key]) or not -1 <= match[key] <= 1:
                raise ValueError("Invalid retrieval score")
    return result


def features_from_results(results):
    """Aggregate only selected, temporally checked historical votes.

    These are uncalibrated historical measurements, not decision rules. Missing
    histories yield NaN rates/ages and zero counts; training must impute locally.
    Exact-text conflict refers to different *historical* NBIM votes, never the
    outcome of the current proposal. No labels determine retrieval membership.
    """
    output = np.empty((len(results), len(FEATURE_NAMES)), dtype=float)
    for row_index, result in enumerate(results):
        validate_result(result)
        query = result["query"]
        day = date.fromisoformat(query["meeting_date"])
        values = []
        for scope in SCOPES:
            matches = [m for m in result["matches"] if scope == "all" or scope in m["selection"]]
            if not matches:
                values += [0.0] + [np.nan] * 10 + [0.0, 0.0, 0.0]
                continue
            labels = np.array([m["nbim_vote"] != m["mgmt_rec"] for m in matches], dtype=float)
            scores = np.array([m["retrieval_score"] for m in matches])
            weights = np.exp((scores - scores.max()) / .10)
            ages = np.array([(day - date.fromisoformat(m["meeting_date"])).days for m in matches])
            recency = weights * np.exp2(-np.minimum(ages, 365000) / 365.)
            values += [float(np.log1p(len(matches))), float(labels.mean()),
                       float(np.average(labels, weights=weights)), float(np.average(labels, weights=recency)),
                       float(labels[0]), float(labels[:3].mean()), float(scores.max()),
                       float(max(m["dense_similarity"] for m in matches)),
                       float(max(m["lexical_similarity"] for m in matches)),
                       float(ages.min() / 365.25), float(ages.mean() / 365.25),
                       float(np.log1p(len({normalize_text(m["proposal_text"]) for m in matches}))),
                       float(len({m["nbim_vote"] for m in matches}) > 1), float(len(set(labels)) > 1)]
        query_text = normalize_text(query["proposal_text"])
        for scope in ("all", "company"):
            exact = [m for m in result["matches"] if query_text and normalize_text(m["proposal_text"]) == query_text
                     and (scope == "all" or m["company_id"] == query["company_id"])]
            values += [float(np.log1p(len(exact))),
                       float(np.mean([m["nbim_vote"] != m["mgmt_rec"] for m in exact])) if exact else np.nan,
                       float(len({m["nbim_vote"] for m in exact}) > 1)]
        output[row_index] = values
    return output, list(FEATURE_NAMES)
