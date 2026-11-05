"""Label-safe features for a supervised local voting model; no fitting or API calls.

Only proposal text, board recommendation and proponent describe the current item.
Company/meeting identities and dates route strictly earlier reference history. Every
reference vote used must be from the caller's fit partition, before query date minus
five days, and outside its meeting. Query votes, rationales and supplied proposal
categories are never read. Embeddings are supplied by the caller's allowlisted cache.

Counts use log1p; ages use years; unavailable rates/ages/similarities are NaN. Learners
must support or impute NaN using training data only. Recency weights have a fixed
365-day half-life; semantic weights are exp((cosine-1)/0.10). These are explanatory
features, not confidence estimates or verified evidence of a voting-rule violation.
"""
import re
import unicodedata

import numpy as np

from vector_model import KEY, VOTES, _metadata, _vectors
from vote_targets import target_labels, validate_target

FAMILIES = ("director", "pay", "auditor", "shareholder", "capital", "other")
_PATTERNS = {
    "pay": re.compile(r"\b(?:remuneration|compensation|incentive|salary|salaries|bonus|bonuses|severance|pay|stock option|equity plan)\b"),
    "auditor": re.compile(r"\b(?:auditor|auditors|audit firm|auditing|audit fees)\b"),
    "shareholder": re.compile(r"\b(?:shareholder proposal|political|climate|human rights|lobbying|gender pay|racial|environmental|net zero)\b"),
    "capital": re.compile(r"\b(?:capital|issuance|repurchase|buyback|dividend|stock split|share split|preemptive|pre emptive|rights issue)\b"),
    "director": re.compile(r"\b(?:director|directors|board|elect|reelect|re elect|committee member|member of .{0,30}committee)\b"),
}

FEATURE_NAMES = (
    [f"board_{vote.lower()}" for vote in VOTES] + ["board_unknown", "proponent_shareholder"]
    + [f"family_{name}" for name in FAMILIES] + ["has_named_person", "history_count_log"]
    + ["company_count_log", "company_mot_mean", "company_365d_count_log", "company_365d_mot_mean",
       "company_last20_mot_mean", "company_meetings_log", "company_latest_age_years"]
    + [f"{group}_{stat}" for group in ("exact_company", "exact_global", "person_company")
       for stat in ("count_log", "mot_mean", "last_mot", "last_age_years")]
    + [f"{group}_{stat}" for group in ("family_company", "family_global")
       for stat in ("count_log", "mot_mean", "recency_mot_mean")]
    + ["family_global_365d_count_log", "family_global_365d_mot_mean"]
    + [f"semantic_{scope}_top{k}_mot_mean" for scope in ("global", "company") for k in (1, 5, 20)]
    + ["top_mot_similarity", "top_nonmot_similarity", "mot_similarity_margin"]
    + [f"similarity_{threshold}_{stat}" for threshold in ("080", "090") for stat in ("count_log", "mot_mean")]
    + ["company_top_similarity", "global_top_similarity", "semantic_global_top20_recency_mot_mean",
       "semantic_company_top20_recency_mot_mean", "history_latest_mot_age_years", "company_latest_mot_age_years"]
)


def feature_names(target="mot"):
    """Same positions for both targets; current board indicators keep literal names."""
    validate_target(target)
    if target == "mot":
        return list(FEATURE_NAMES)
    return [name if name.startswith("board_") else name.replace("nonmot", "not_against_board").replace("mot", "against_board")
            for name in FEATURE_NAMES]


def normalize_text(text):
    """Normalize Unicode, case, whitespace and punctuation without adding information."""
    return " ".join(re.sub(r"[^\w\s]", " ", unicodedata.normalize("NFKC", text).casefold()).split())


def proposal_family(text):
    normalized = normalize_text(text)
    # Fixed text-only precedence. Director remuneration belongs to pay, for example.
    return next((name for name in ("shareholder", "pay", "auditor", "capital", "director")
                 if _PATTERNS[name].search(normalized)), "other")


def named_person(text):
    """Conservative name extraction; generic/bundled elections and audit firms abstain."""
    text = unicodedata.normalize("NFKC", text).strip()
    match = re.match(r"^(?:re[ -]?)?(elect|appoint)\s+(.+)$", text, flags=re.I)
    if not match:
        return ""
    if match.group(1).lower() == "appoint" and not re.search(r"\b(?:director|statutory auditor|internal auditor|committee)\b", text, flags=re.I):
        return ""
    person = re.split(r"\s+as\s+", match.group(2), maxsplit=1, flags=re.I)[0]
    person = re.sub(r"^(?:(?:a|an|the)\s+)?(?:(?:inside|outside|independent|non[ -]independent|executive|non[ -]executive|statutory|internal|supervisory|alternate)\s+)*(?:director|auditor)\s*", "", person, flags=re.I)
    person = normalize_text(re.sub(r"\([^)]*\)", "", person))
    if len(person.split()) < 2 or re.search(r"\b(?:two|three|four|five|six|seven|eight|nine|ten|directors|members|bundled|slate|vacancy|vacancies|board|committee)\b|\d", person):
        return ""
    return person


def _mean(labels, indices, weights=None):
    if not len(indices):
        return np.nan
    values = labels[indices]
    if weights is None:
        return float(np.mean(values))
    weight = weights[indices]
    weight = weight / weight.max()
    return float(np.sum(values * weight) / np.sum(weight))


def features(frame, X, reference, R, target="mot"):
    """Return (numeric matrix, names), using only the supplied fit reference votes.

    Reference order is canonicalized; exact cosine ties prefer the same company,
    then latest eligible date, then meeting/item identity. X and R must have 384
    finite nonzero coordinates per row. Reference labels must all be known for
    the chosen target. Query NBIM votes are never read, even for against_board.
    """
    names = feature_names(target)
    query = _metadata(frame)
    ref = _metadata(reference)
    labels = target_labels(reference, target)
    qvectors, rvectors = _vectors(X, len(query)), _vectors(R, len(ref))
    order = ref.sort_values(KEY, kind="stable").index.to_numpy()
    # Actual reference votes stay unchanged; only this separate binary target is aggregated.
    mot = labels[order].astype(float)
    ref = ref.iloc[order].reset_index(drop=True)
    rvectors = rvectors[order]
    dates = ref["meeting_date"].to_numpy(dtype="datetime64[D]").astype(np.int64)
    companies = ref["company_id"].to_numpy()
    meetings = ref["meeting_id"].to_numpy()
    exact = ref["proposal_text"].map(normalize_text).to_numpy()
    people = ref["proposal_text"].map(named_person).to_numpy()
    families = ref["proposal_text"].map(proposal_family).to_numpy()
    output = np.empty((len(query), len(FEATURE_NAMES)), dtype=np.float64)
    for start in range(0, len(query), 256):
        similarities = np.clip(qvectors[start:start + 256] @ rvectors.T, -1.0, 1.0)
        for offset, row in enumerate(query.iloc[start:start + 256].to_dict("records")):
            day = np.datetime64(row["meeting_date"], "D").astype(np.int64)
            age = day - dates
            same_company = companies == row["company_id"]
            eligible = (age > 5) & (meetings != row["meeting_id"]) & ~(same_company & (age == 0))
            history = np.flatnonzero(eligible)
            company = np.flatnonzero(eligible & same_company)
            text, person, family = normalize_text(row["proposal_text"]), named_person(row["proposal_text"]), proposal_family(row["proposal_text"])
            family_history = np.flatnonzero(eligible & (families == family))
            family_company = np.flatnonzero(eligible & same_company & (families == family))
            similarity = similarities[offset].astype(np.float64)
            # Only eligible rows are aggregated. Clipping protects unused future-row weights.
            recency = np.exp2(-np.clip(age, 0, 365000) / 365.0)
            semantic = np.exp((similarity - 1.0) / 0.10)
            ranked = history[np.lexsort((history, -dates[history], ~same_company[history], -similarity[history]))]
            ranked_company = ranked[same_company[ranked]]
            recent_company = company[age[company] <= 365]
            latest_company = company[np.lexsort((company, -dates[company]))[:20]]
            values = [float(row["mgmt_rec"] == vote) for vote in VOTES]
            values += [float(row["mgmt_rec"] not in VOTES), float(bool(re.search(r"shareholder|stockholder|share owner", row["proponent"], flags=re.I)))]
            values += [float(family == name) for name in FAMILIES] + [float(bool(person)), np.log1p(len(history))]
            values += [np.log1p(len(company)), _mean(mot, company), np.log1p(len(recent_company)), _mean(mot, recent_company),
                       _mean(mot, latest_company), np.log1p(len(np.unique(dates[company]))), float(age[company].min() / 365.25) if len(company) else np.nan]
            groups = (np.flatnonzero(eligible & same_company & (exact == text)) if text else np.array([], dtype=int),
                      np.flatnonzero(eligible & (exact == text)) if text else np.array([], dtype=int),
                      np.flatnonzero(eligible & same_company & (people == person)) if person else np.array([], dtype=int))
            for group in groups:
                last = group[np.lexsort((group, -dates[group]))[0]] if len(group) else None
                values += [np.log1p(len(group)), _mean(mot, group), float(mot[last]) if last is not None else np.nan,
                           float(age[last] / 365.25) if last is not None else np.nan]
            for group in (family_company, family_history):
                values += [np.log1p(len(group)), _mean(mot, group), _mean(mot, group, recency)]
            recent_family = family_history[age[family_history] <= 365]
            values += [np.log1p(len(recent_family)), _mean(mot, recent_family)]
            for group in (ranked, ranked_company):
                values += [_mean(mot, group[:k], semantic) for k in (1, 5, 20)]
            positive, negative = history[mot[history] == 1], history[mot[history] == 0]
            best_positive = float(similarity[positive].max()) if len(positive) else np.nan
            best_negative = float(similarity[negative].max()) if len(negative) else np.nan
            values += [best_positive, best_negative, best_positive - best_negative]
            for threshold in (0.80, 0.90):
                close = history[similarity[history] >= threshold]
                values += [np.log1p(len(close)), _mean(mot, close)]
            values += [float(similarity[ranked_company[0]]) if len(ranked_company) else np.nan,
                       float(similarity[ranked[0]]) if len(ranked) else np.nan,
                       _mean(mot, ranked[:20], semantic * recency), _mean(mot, ranked_company[:20], semantic * recency),
                       float(age[positive].min() / 365.25) if len(positive) else np.nan,
                       float(age[positive[same_company[positive]]].min() / 365.25) if np.any(same_company[positive]) else np.nan]
            output[start + offset] = values
    return output, names
