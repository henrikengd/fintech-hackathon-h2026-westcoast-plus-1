"""Frozen-model adapters for a new, label-blind meeting cohort.

No fitting, threshold selection, downloading, or automatic API retries. The
caller freezes the cohort and history snapshot before obtaining fresh outcomes.
The entire query cohort is excluded from historical context, including aliases
with another meeting ID but the same company/date.
"""
from collections import Counter
from datetime import date, timedelta
import json

import anthropic
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

import claude_board_context as frozen_claude
import vote_features
import vote_learner
from vector_model import DIMENSION, KEY, META_FIELDS, MODEL, VOTES, _metadata, _vectors


SYSTEM = frozen_claude.SYSTEM
Draft = frozen_claude.Draft
Drafts = frozen_claude.Drafts
TOP_K = frozen_claude.TOP_K
EXPERIMENT = frozen_claude.EXPERIMENT
SCOPE = frozen_claude.SCOPE
POLICY = frozen_claude.POLICY
LOCAL_CONFIG = {"name": "semantic-history-boost", "kind": "boost", "input": "semantic",
                "leaves": 15, "class_weight": None}


class ReviewValidationError(ValueError):
    """Preserve the returned provider response for a separate failure audit."""

    def __init__(self, category, response):
        super().__init__(category)
        self.category = category
        self.response = response
        self.usage = response.get("usage", {})
        self.stop_reason = response.get("stop_reason")


def _inputs(reference, query, reference_vectors, query_vectors, *, normalize=True):
    if not isinstance(query, pd.DataFrame) or query.empty or set(query.columns) != set(META_FIELDS):
        raise ValueError("Query must contain only the ballot metadata allowlist, with no outcomes")
    if not isinstance(reference, pd.DataFrame) or "nbim_vote" not in reference:
        raise ValueError("Reference requires historical NBIM votes")
    current, historical = _metadata(query), _metadata(reference)
    qvectors = _vectors(query_vectors, len(current))
    rvectors = _vectors(reference_vectors, len(historical))
    if not current.mgmt_rec.isin([*VOTES, ""]).all():
        raise ValueError("Unrecognized board recommendation")
    for frame in (current, historical):
        if frame.groupby("meeting_id")[["company_id", "company", "meeting_date"]].nunique().gt(1).any().any():
            raise ValueError("Meeting identity spans inconsistent metadata")
    # Reject no labels here: excluded cohort rows need never have outcomes read.
    query_ids = set(current.meeting_id)
    query_groups = set(zip(current.company_id, current.meeting_date))
    keep = ~historical.meeting_id.isin(query_ids)
    keep &= pd.Series([(company, day) not in query_groups
                       for company, day in zip(historical.company_id, historical.meeting_date)], index=historical.index)
    keep &= historical.meeting_date.lt((pd.Timestamp(current.meeting_date.max()) - pd.Timedelta(days=5)).strftime("%Y-%m-%d"))
    selected = np.flatnonzero(keep.to_numpy())
    historical = historical.iloc[selected].reset_index(drop=True)
    historical["nbim_vote"] = reference.iloc[selected]["nbim_vote"].to_numpy()
    if not historical.nbim_vote.isin(VOTES).all() or not historical.mgmt_rec.isin(VOTES).all():
        raise ValueError("Eligible history requires known board and NBIM votes")
    if not historical.meeting_date.ge("2019-01-01").all():
        raise ValueError("Historical dates before the frozen source period are unsupported")
    if normalize:
        return historical, current, rvectors[selected], qvectors
    # vote_features performs the frozen normalization itself. Avoid applying it
    # an additional time on this path, while retaining the validation above.
    return historical, current, np.asarray(reference_vectors)[selected], np.asarray(query_vectors)


def build_bundles(reference, query, reference_vectors, query_vectors):
    """Use frozen top-8 retrieval without requiring any current target column."""
    reference, query, rvectors, qvectors = _inputs(reference, query, reference_vectors, query_vectors)
    order = reference.sort_values(KEY, kind="stable").index.to_numpy()
    reference = reference.iloc[order].reset_index(drop=True)
    rvectors = rvectors[order]
    records = reference.to_dict("records")
    dates = reference.meeting_date.to_numpy(dtype="datetime64[D]")
    date_days = dates.astype(np.int64)
    companies, meetings = reference.company_id.to_numpy(), reference.meeting_id.to_numpy()
    bundles = {}
    with threadpool_limits(limits=1):
        for start in range(0, len(query), 128):
            similarities = np.clip(qvectors[start:start + 128] @ rvectors.T, -1, 1)
            for offset, row in enumerate(query.iloc[start:start + 128].to_dict("records")):
                day = np.datetime64(row["meeting_date"], "D")
                same_company = companies == row["company_id"]
                allowed = (dates < day - np.timedelta64(5, "D")) & (meetings != row["meeting_id"])
                allowed &= ~(same_company & (dates == day))
                candidates = np.flatnonzero(allowed)
                cosine = similarities[offset]
                ranked = candidates[np.lexsort((candidates, -date_days[candidates], ~same_company[candidates], -cosine[candidates]))]
                global_indices, company_indices = ranked[:TOP_K], ranked[same_company[ranked]][:TOP_K]
                chosen = list(dict.fromkeys([*global_indices, *company_indices]))
                bundle = bundles.setdefault(row["meeting_id"], {
                    "experiment": EXPERIMENT, "context_scope": SCOPE, "history_policy": POLICY,
                    "retrieval_model": MODEL, "top_k_global": TOP_K, "top_k_company": TOP_K,
                    "meeting": {key: row[key] for key in ("meeting_id", "company_id", "company", "meeting_date")},
                    "proposals": [], "history": {},
                })
                matches = []
                for index in chosen:
                    historical = records[index]
                    history_id = f"{historical['meeting_id']}:{historical['item_no']}"
                    bundle["history"][history_id] = {"id": history_id, **historical}
                    matches.append({"id": history_id, "cosine_similarity": float(cosine[index]),
                                    "selection": [kind for kind, indices in (("global", global_indices), ("company", company_indices)) if index in indices]})
                bundle["proposals"].append({"item": row["item_no"], "text": row["proposal_text"],
                    "proponent": row["proponent"], "board_recommendation": row["mgmt_rec"],
                    "history_ids": [match["id"] for match in matches], "history_matches": matches})
    result = []
    forbidden_meetings = set(query.meeting_id)
    forbidden_groups = set(zip(query.company_id, query.meeting_date))
    for bundle in sorted(bundles.values(), key=lambda item: (item["meeting"]["meeting_date"], item["meeting"]["meeting_id"])):
        bundle["proposals"].sort(key=lambda item: item["item"])
        bundle["history"] = [bundle["history"][key] for key in sorted(bundle["history"])]
        validate_bundle(bundle, forbidden_meetings, forbidden_groups)
        result.append(bundle)
    return result


def validate_bundle(bundle, forbidden_meetings=(), forbidden_groups=()):
    """Frozen outbound schema and strict as-of rule; no hardcoded query year."""
    expected = {"experiment", "context_scope", "history_policy", "retrieval_model", "top_k_global", "top_k_company", "meeting", "proposals", "history"}
    if set(bundle) != expected or bundle["experiment"] != EXPERIMENT or bundle["context_scope"] != SCOPE or bundle["history_policy"] != POLICY:
        raise ValueError("Unexpected context fields or scope")
    if bundle["retrieval_model"] != MODEL or (bundle["top_k_global"], bundle["top_k_company"]) != (TOP_K, TOP_K):
        raise ValueError("Unexpected retrieval configuration")
    meeting = bundle["meeting"]
    if set(meeting) != {"meeting_id", "company_id", "company", "meeting_date"} or not all(isinstance(v, str) for v in meeting.values()):
        raise ValueError("Invalid meeting metadata")
    day = date.fromisoformat(meeting["meeting_date"])
    if day.isoformat() != meeting["meeting_date"] or day < date(2019, 1, 1) or not meeting["meeting_id"] or not meeting["company_id"]:
        raise ValueError("Invalid query identity or date")
    excluded_ids = set(forbidden_meetings) | {meeting["meeting_id"]}
    excluded_groups = set(forbidden_groups) | {(meeting["company_id"], meeting["meeting_date"])}
    history = {}
    for entry in bundle["history"]:
        if set(entry) != {"id", *META_FIELDS, "nbim_vote"} or not all(isinstance(v, str) for v in entry.values()):
            raise ValueError("Unexpected historical fields")
        if entry["id"] != f"{entry['meeting_id']}:{entry['item_no']}" or entry["id"] in history:
            raise ValueError("Invalid or duplicate historical identity")
        historical_day = date.fromisoformat(entry["meeting_date"])
        if (historical_day.isoformat() != entry["meeting_date"] or historical_day < date(2019, 1, 1)
                or historical_day >= day - timedelta(days=5) or entry["meeting_id"] in excluded_ids
                or (entry["company_id"], entry["meeting_date"]) in excluded_groups):
            raise ValueError("Historical record crosses cohort or decision boundaries")
        if entry["nbim_vote"] not in VOTES or entry["mgmt_rec"] not in VOTES or not entry["company_id"]:
            raise ValueError("Unknown historical vote or company")
        history[entry["id"]] = entry
    item_ids, used = [], set()
    for proposal in bundle["proposals"]:
        if set(proposal) != {"item", "text", "proponent", "board_recommendation", "history_ids", "history_matches"}:
            raise ValueError("Unexpected current proposal fields")
        if any(not isinstance(proposal[key], str) for key in ("item", "text", "proponent", "board_recommendation")):
            raise ValueError("Invalid proposal metadata")
        if not proposal["item"] or proposal["board_recommendation"] not in (*VOTES, ""):
            raise ValueError("Unknown item or invalid board recommendation")
        item_ids.append(proposal["item"])
        ids = proposal["history_ids"]
        if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids) or len(ids) != len(set(ids)) or not set(ids) <= history.keys():
            raise ValueError("Unknown or duplicate proposal history IDs")
        if [match.get("id") for match in proposal["history_matches"]] != ids:
            raise ValueError("Retrieval matches disagree with history IDs")
        counts = Counter()
        for match in proposal["history_matches"]:
            if set(match) != {"id", "cosine_similarity", "selection"}:
                raise ValueError("Unexpected retrieval match fields")
            score, selection = match["cosine_similarity"], match["selection"]
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not np.isfinite(score) or not -1 <= score <= 1:
                raise ValueError("Invalid cosine similarity")
            if not isinstance(selection, list) or not selection or len(selection) != len(set(selection)) or not set(selection) <= {"global", "company"}:
                raise ValueError("Invalid retrieval selection")
            if "company" in selection and history[match["id"]]["company_id"] != meeting["company_id"]:
                raise ValueError("Company-specific match belongs to another company")
            counts.update(selection)
        if any(value > TOP_K for value in counts.values()):
            raise ValueError("Retrieval exceeds fixed top-k")
        used.update(ids)
    if not item_ids or len(item_ids) != len(set(item_ids)) or used != history.keys():
        raise ValueError("Missing/duplicate proposals or unused historical records")


def validate_response(bundle, reply):
    validate_bundle(bundle)
    if reply.get("stop_reason") != "end_turn":
        raise ReviewValidationError("incomplete_response", reply)
    try:
        text = "".join(part.get("text", "") for part in reply.get("content", []) if part.get("type") == "text")
        drafts = Drafts.model_validate_json(text).model_dump()["items"]
    except (ValueError, TypeError, KeyError):
        raise ReviewValidationError("invalid_response_schema", reply) from None
    proposals = {proposal["item"]: proposal for proposal in bundle["proposals"]}
    if Counter(item["item"] for item in drafts) != Counter(list(proposals)):
        raise ReviewValidationError("proposal_identity_mismatch", reply)
    checked = []
    for draft in drafts:
        proposal = proposals[draft["item"]]
        ids = draft["history_ids"]
        if len(ids) != len(set(ids)) or not set(ids) <= set(proposal["history_ids"]):
            raise ReviewValidationError("invalid_history_citation", reply)
        if not draft["why"].strip():
            raise ReviewValidationError("empty_explanation", reply)
        known = draft["vote"] is not None and proposal["board_recommendation"] in VOTES
        checked.append({**draft, "against_board": draft["vote"] != proposal["board_recommendation"] if known else None,
                        "history_ids_verified": True, "requires_human_signoff": True})
    return {"items": checked, "usage": reply.get("usage", {}), "stop_reason": reply.get("stop_reason"), "model": reply.get("model"),
            "context_scope": SCOPE, "citation_check": "Historical IDs exist in the supplied proposal context; this does not establish causal or guideline support."}


def generate_review(bundle, client=None, *, model, effort):
    """Use the original frozen prompt/schema; callers must pass frozen settings."""
    validate_bundle(bundle)
    if not isinstance(model, str) or not model or not isinstance(effort, str) or not effort:
        raise ValueError("Explicit frozen model and effort are required")
    client = client or anthropic.Anthropic(max_retries=0)
    reply = client.messages.create(
        model=model, max_tokens=min(16000, 1000 + 220 * len(bundle["proposals"])), system=SYSTEM,
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": anthropic.transform_schema(Drafts)}},
        messages=[{"role": "user", "content": json.dumps(bundle, ensure_ascii=False)}],
    ).model_dump()
    return validate_response(bundle, reply)


def local_predict(state, query, query_vectors, reference, reference_vectors, *, return_features=False):
    """Apply the frozen learner; no current targets or fit operation are needed."""
    names = vote_features.feature_names("against_board")
    if (state.get("target") != "against_board" or state.get("config") != LOCAL_CONFIG
            or state.get("feature_names") != names or len(names) != 59
            or state.get("history_transform") != "capped-counts-50-ages-3-v1"):
        raise ValueError("Expected the frozen semantic-history-boost disagreement learner")
    reference, query, rvectors, qvectors = _inputs(reference, query, reference_vectors, query_vectors, normalize=False)
    with threadpool_limits(limits=1):
        history, actual_names = vote_features.features(query, qvectors, reference, rvectors, target="against_board")
        if actual_names != names or history.shape != (len(query), 59) or qvectors.shape != (len(query), DIMENSION):
            raise ValueError("Frozen feature schema mismatch")
        scores = np.asarray(vote_learner.predict(state, query, history, qvectors), dtype=float).copy()
    if scores.shape != (len(query),):
        raise ValueError("Learner output row count changed")
    scores[~query.mgmt_rec.isin(VOTES).to_numpy()] = np.nan
    return (scores, history, names) if return_features else scores
