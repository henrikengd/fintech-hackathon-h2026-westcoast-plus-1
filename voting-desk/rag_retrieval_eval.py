"""Offline comparison of retrieval methods on small development-only evidence anchors.

python rag_retrieval_eval.py --output data/local-rag/retrieval-evaluation.json

No LLM calls, model downloads, voting targets, or changes to the live retriever.
"""
import boot  # noqa: F401
import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
from itertools import zip_longest
import json
import os
from pathlib import Path
import re
import tempfile

from local_rag import RagIndex, cutoff


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data/local-rag/pilot-development.sqlite"
DEFAULT_CASES = ROOT / "rag_retrieval_cases.json"
TRAIN = ROOT / "data/mixed-80-20/train.csv"
TEST = ROOT / "data/mixed-80-20/test.csv"
METHODS = ("keyword", "vector", "hybrid", "alternate")
K = 5
DEPTH = 20
# Generic function words only. No company names, domain terms or expected-answer words.
STOPWORDS = frozenset("""a an and are as at be been being by did do does for from had has
have how in into is it its of on or our that the their these they this those to was
were what when where which who why will with would each also during""".split())
CAVEAT = (
    "Small, manually selected development-only regression anchors with incomplete relevance judgments. "
    "The primary comparison uses each full question. Predefined query variants are a separate sensitivity analysis. "
    "Anchor-hit@5 is not general retrieval recall, voting precision/recall, or an independent test score. "
    "Alternating retrieval is exploratory and must not be promoted based on these anchors alone. "
    "Exact source-quote validity verifies text provenance, not logical support for an answer."
)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def fingerprint(value):
    return sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def keyword_query(question):
    """Remove generic stopwords only from the experimental keyword branch."""
    return " ".join(word for word in re.findall(r"[^\W_]+", question, re.UNICODE)
                    if word.casefold() not in STOPWORDS)


def alternating(vector_hits, keyword_hits, k=K):
    """Interleave original ranks V1,K1,V2,K2,..., retaining each chunk once."""
    result, seen = [], set()
    for pair in zip_longest(vector_hits, keyword_hits):
        for hit in pair:
            if hit is not None and hit["id"] not in seen:
                result.append(hit)
                seen.add(hit["id"])
                if len(result) == k:
                    return result
    return result


def retrieve(index, query, meeting_id):
    """Use the same index and final evidence budget for all four methods."""
    vector = index.search(query, meeting_id, k=DEPTH, mode="vector")
    cleaned = keyword_query(query)
    lexical_cleaned = index.search(cleaned, meeting_id, k=DEPTH, mode="keyword") if cleaned else []
    return {
        "keyword": index.search(query, meeting_id, k=K, mode="keyword"),
        "vector": vector[:K],
        "hybrid": index.search(query, meeting_id, k=K, mode="hybrid"),
        "alternate": alternating(vector, lexical_cleaned),
    }


def load_cases(path=DEFAULT_CASES):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("cases"), list) or not data["cases"]:
        raise ValueError("Expected nonempty schema_version 1 retrieval cases")
    ids = set()
    for case in data["cases"]:
        required = ("id", "meeting_id", "question", "expected_quote", "source_document_id")
        if any(not isinstance(case.get(key), str) or not case[key].strip() for key in required):
            raise ValueError("Case lacks a nonempty question, source, or expected quotation")
        if case["id"] in ids:
            raise ValueError("Duplicate retrieval case ID")
        ids.add(case["id"])
        if not isinstance(case.get("queries", []), list) or any(not isinstance(q, str) or not q.strip() for q in case.get("queries", [])):
            raise ValueError("Query variants must be nonempty strings")
    return data


def source_check(index, hit, meeting_id):
    """Check retrieved text, source identity, meeting and pre-decision publication."""
    try:
        doc = index.document(hit["document_id"])
        start, end = hit["start"], hit["end"]
        exact = (isinstance(start, int) and isinstance(end, int)
                 and 0 <= start < end <= len(doc["text"])
                 and doc["text"][start:end] == hit["text"])
        metadata = all(hit[key] == doc[key] for key in
                       ("meeting_id", "company_id", "meeting_date", "filed", "url", "file"))
        valid = bool(exact and metadata and doc["meeting_id"] == meeting_id
                     and doc["filed"] < cutoff(doc["meeting_date"]))
        return {"chunk_id": hit.get("id"), "document_id": hit.get("document_id"),
                "exact_quote": bool(exact), "source_metadata_matches": bool(metadata), "valid": valid}
    except (KeyError, TypeError, ValueError):
        return {"chunk_id": hit.get("id"), "document_id": hit.get("document_id"),
                "exact_quote": False, "source_metadata_matches": False, "valid": False}


def score_query(index, case, query, query_id):
    # The expected quotation is used only here, after every retrieval has completed.
    found = retrieve(index, query, case["meeting_id"])
    methods = {}
    for method, hits in found.items():
        checks = [source_check(index, hit, case["meeting_id"]) for hit in hits]
        rank = next((n for n, (hit, check) in enumerate(zip(hits, checks), 1)
                     if check["valid"] and hit["document_id"] == case["source_document_id"]
                     and case["expected_quote"] in hit["text"]), None)
        methods[method] = {"anchor_rank_at_5": rank, "anchor_hit_at_5": rank is not None,
                           "reciprocal_rank_at_5": 1 / rank if rank else 0.0,
                           "returned": len(hits), "valid_source_quotes": sum(c["valid"] for c in checks),
                           "source_quote_checks": checks}
    return {"query_id": query_id, "case_id": case["id"], "meeting_id": case["meeting_id"],
            "query": query, "experimental_keyword_query": keyword_query(query), "methods": methods}


def summarize(rows):
    summary = {}
    for method in METHODS:
        records = [row["methods"][method] for row in rows]
        returned = sum(r["returned"] for r in records)
        valid = sum(r["valid_source_quotes"] for r in records)
        summary[method] = {
            "queries": len(records), "anchor_hits_at_5": sum(r["anchor_hit_at_5"] for r in records),
            "anchor_hit_at_5": sum(r["anchor_hit_at_5"] for r in records) / len(records) if records else None,
            "mrr_at_5": sum(r["reciprocal_rank_at_5"] for r in records) / len(records) if records else None,
            "returned_passages": returned, "valid_source_quotes": valid,
            "source_quote_validity": valid / returned if returned else None,
        }
    return summary


def development_partition(index):
    """Validate meeting and company/date membership using only partition metadata."""
    memberships = {}
    for name, path in (("train", TRAIN), ("test", TEST)):
        with Path(path).open(encoding="utf-8", newline="") as handle:
            memberships[name] = {(r["meeting_id"], r["company_id"], r["meeting_date"])
                                 for r in csv.DictReader(handle)}
    test_ids = {row[0] for row in memberships["test"]}
    test_groups = {row[1:] for row in memberships["test"]}
    documents = [json.loads(row[0]) for row in index.con.execute("SELECT data FROM documents")]
    for doc in documents:
        key = (doc["meeting_id"], doc["company_id"], doc["meeting_date"])
        if not doc["meeting_date"].startswith("2024-") or key not in memberships["train"]:
            raise ValueError("The index must contain only 2024 development meetings")
        if key[0] in test_ids or key[1:] in test_groups:
            raise ValueError("Index overlaps a reserved test meeting or company/date group")
    return {"train_sha256": file_hash(TRAIN), "test_sha256": file_hash(TEST),
            "all_index_meetings_checked": sorted({d["meeting_id"] for d in documents})}


def evaluate(index, data, include_variants=True):
    before = file_hash(index.path)
    partition = development_partition(index)
    sources, anchors = {}, []
    for case in data["cases"]:
        doc = index.document(case["source_document_id"])
        if doc["meeting_id"] != case["meeting_id"] or not doc["meeting_date"].startswith("2024-"):
            raise ValueError("Cases must refer to indexed 2024 development sources")
        if case["expected_quote"] not in doc["text"]:
            raise ValueError(f"Expected quotation absent from source for {case['id']}")
        source_id = case["source_document_id"]
        sources[source_id] = {"source_sha256": doc["sha256"], "meeting_id": doc["meeting_id"],
                              "meeting_date": doc["meeting_date"], "filed": doc["filed"], "url": doc["url"]}
        chunk_texts = (r[0] for r in index.con.execute("SELECT text FROM chunks WHERE document_id=?", (source_id,)))
        anchors.append({"case_id": case["id"], "source_document_id": source_id,
                        "source_exact_quote_valid": True,
                        "anchor_contained_in_any_chunk": any(case["expected_quote"] in text for text in chunk_texts)})
    identity = {"index_sha256": before, "index_version": index.info["version"],
                "model": index.info["model"], "dimension": index.info["dimension"],
                "model_assets_sha256": fingerprint(index.info["model_assets"]),
                "all_index_source_hashes": index.info["source_hashes"],
                "case_dataset_sha256": fingerprint(data), "evaluated_sources": sources,
                "development_partition": partition}
    primary, variants = [], []
    for case in data["cases"]:
        primary.append(score_query(index, case, case["question"], case["id"] + "/question"))
        if include_variants:
            for number, query in enumerate(case.get("queries", []), 1):
                variants.append(score_query(index, case, query, f"{case['id']}/query-{number}"))
    if file_hash(index.path) != before:
        raise ValueError("Index changed during the comparison")
    if file_hash(TRAIN) != partition["train_sha256"] or file_hash(TEST) != partition["test_sha256"]:
        raise ValueError("Development partition changed during the comparison")
    configuration = {"k": K, "alternating_candidate_depth": DEPTH, "methods": METHODS,
                     "alternate": "Unique V1,K1,V2,K2,... with stopwords removed only from keyword query",
                     "stopwords": sorted(STOPWORDS), "include_variants": include_variants,
                     "code_sha256": {name: file_hash(ROOT / name) for name in ("rag_retrieval_eval.py", "local_rag.py")}}
    return {"evaluation_kind": "EXPLORATORY_DEVELOPMENT_ANCHORS", "created_at": datetime.now(timezone.utc).isoformat(),
            "data_id": fingerprint(identity)[:16], "source_dataset_identity": identity,
            "config_id": fingerprint(configuration)[:16], "configuration": configuration,
            "caveat": CAVEAT, "anchor_checks": anchors,
            "primary_questions": {"summary": summarize(primary), "queries": primary},
            "sensitivity_query_variants": {"summary": summarize(variants), "queries": variants}}


def save_report(path, report):
    """Write a complete new report without replacing earlier experiment evidence."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-variants", action="store_true")
    args = parser.parse_args(argv)
    data = load_cases(args.cases)
    index = RagIndex(args.db)
    try:
        report = evaluate(index, data, include_variants=not args.no_variants)
    finally:
        index.close()
    if args.output:
        save_report(args.output, report)
    print(json.dumps({"data_id": report["data_id"], "config_id": report["config_id"],
                      "primary_questions": report["primary_questions"]["summary"],
                      "sensitivity_query_variants": report["sensitivity_query_variants"]["summary"],
                      "caveat": CAVEAT}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
