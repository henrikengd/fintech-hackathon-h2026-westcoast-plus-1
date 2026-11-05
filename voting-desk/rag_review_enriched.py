"""Retrieve shared meeting facts in addition to each proposal's evidence.

Fixed questions follow governance topics, not observed voting outcomes. The
generation prompt, rules, model and quote validation remain in rag_review.
"""
import re

from local_rag import DEFAULT_DB, RagIndex
import rag_review


BOARD_QUERIES = (
    "board size number of directors independent directors independence determination",
    "controlled company majority voting power ownership independent board exemption",
    "audit compensation nominating governance committee members independence chair",
    "directors attended board committee meetings attendance seventy-five percent",
    "board diversity female women directors number percentage",
    "chairman chief executive officer combined roles independent lead director",
)
PAY_QUERIES = (
    "executive compensation equity awards vesting period performance conditions holding period",
    "long term incentive performance metrics targets payout maximum dilution stock options",
    "say on pay shareholder support previous vote compensation committee response",
)
AUDITOR_QUERIES = (
    "independent registered public accounting firm audit fees non-audit fees tenure ratification",
)
FIELDS = ("id", "document_id", "text", "url", "filed", "start", "end", "heading")


def shared_queries(proposals):
    text = " ".join(p["text"] for p in proposals)
    queries = []
    if re.search(r"director|board|nominee", text, re.I):
        queries.extend(BOARD_QUERIES)
    if re.search(r"compensation|remuneration|pay|incentive|equity plan", text, re.I):
        queries.extend(PAY_QUERIES)
    if re.search(r"auditor|audit firm|accountant", text, re.I):
        queries.extend(AUDITOR_QUERIES)
    return queries


def prepare_bundle(meeting_id, db=DEFAULT_DB, mode="hybrid", k=3,
                   votes_csv=rag_review.VOTES, index=None):
    own_index = index is None
    index = index or RagIndex(db)
    try:
        bundle = rag_review.prepare_bundle(meeting_id, db, mode, k, votes_csv, index)
        passages = {p["id"]: p for p in bundle["passages"]}
        searches = []
        for query in shared_queries(bundle["proposals"]):
            found = index.search(query, str(meeting_id), k=k, mode=mode)
            for passage in found:
                if any(passage[key] != bundle["meeting"][key]
                       for key in ("meeting_id", "company_id", "meeting_date")):
                    raise ValueError("Shared evidence belongs to another meeting")
                passages[passage["id"]] = {key: passage[key] for key in FIELDS}
            searches.append({"query": query, "chunk_ids": [p["id"] for p in found]})
        bundle.update(query_strategy="meeting", shared_searches=searches,
                      passages=list(passages.values()))
        return bundle
    finally:
        if own_index:
            index.close()
