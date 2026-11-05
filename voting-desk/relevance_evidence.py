"""Retrieve dated, source-checked meeting evidence without outcome information.

Dense and lexical rankings are computed within the selected meeting only. No
corpus-wide IDF is fitted, so adding a later meeting cannot change earlier hits.
The historical 2026 rules.json is deliberately not treated as a 2024 policy.
"""
import boot  # noqa: F401
import argparse
from collections import Counter
from datetime import date, timedelta
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from threadpoolctl import threadpool_limits

from local_rag import RagIndex, load_model, model_fingerprint, unit_vectors, MODEL
from rag_corpus import extract_html

ROOT = Path(__file__).resolve().parent
DEFAULT_INDEX = ROOT / "data/local-rag/relevance-evidence-v1/index.sqlite"
DEFAULT_REUSE = tuple(ROOT / "data/local-rag" / name for name in
                      ("development-2024.sqlite", "index.sqlite", "pilot-development.sqlite"))
INPUT_FIELDS = ("meeting_id", "company_id", "company", "meeting_date", "item_no", "proposal_text")
PASSAGE_FIELDS = {"id", "document_id", "meeting_id", "company_id", "meeting_date", "filed", "url", "sha256", "start", "end", "text", "heading"}
POLICY_GAP = "No historically verified policy source is configured for this decision date; rules.json retrieved in 2026 is excluded."
STRATEGY = "within-meeting BGE + hashed word/bigram cosine reciprocal rank fusion; fixed fact questions; max 6 diverse passages"
TOPICS = (
    (r"director|board|nominee", (
        "director nominees independence determination independent non-independent executive",
        "board audit compensation nominating committee members chairman chief executive officer",
        "director attendance other boards directorships biographies experience")),
    (r"compensation|remuneration|pay|incentive|equity plan", (
        "executive compensation equity awards vesting performance conditions holding period",
        "compensation performance metrics targets payout maximum dilution shareholder support")),
    (r"auditor|audit firm|accountant", (
        "auditor audit fees non-audit fees independence tenure accounting firm",)),
    (r"amend|article|bylaw|constitution", (
        "proposed amendments current amended articles bylaws shareholder approval rights",)),
    (r"repurchase|issuance|issue shares|capital|share authorization", (
        "share issuance repurchase authorization purpose limits preemptive shareholder rights",)),
)


def clean_query(row):
    """Select only ballot inputs; labels and rationales never reach retrieval."""
    query = {key: str(row[key]) for key in INPUT_FIELDS}
    if not all(query.values()):
        raise ValueError("Evidence query requires nonempty ballot identity and text")
    date.fromisoformat(query["meeting_date"])
    return query


def queries_for(row):
    text = row["proposal_text"]
    queries = [text[:900]]
    for pattern, questions in TOPICS:
        if re.search(pattern, text, re.I):
            queries.extend(questions)
    return list(dict.fromkeys(queries))


def validate_evidence(bundle):
    """Fail closed before sending context; verify dates, identity and schema.

    Exact quotes and source bytes are checked by EvidenceRetriever at extraction.
    The bundle carries hashes and offsets so these checks can also be audited.
    """
    if set(bundle) != {"query", "strategy", "passages", "rules", "missing"}:
        raise ValueError("Unexpected evidence bundle fields")
    if set(bundle["query"]) != set(INPUT_FIELDS) or clean_query(bundle["query"]) != bundle["query"]:
        raise ValueError("Evidence contains non-ballot input fields")
    if bundle["strategy"] != STRATEGY or bundle["rules"] != []:
        raise ValueError("Unsupported retrieval strategy or unverified rules")
    cutoff = date.fromisoformat(bundle["query"]["meeting_date"]) - timedelta(days=5)
    ids = set()
    for passage in bundle["passages"]:
        if set(passage) != PASSAGE_FIELDS:
            raise ValueError("Unexpected passage fields")
        for key in ("meeting_id", "company_id", "meeting_date"):
            if passage[key] != bundle["query"][key]:
                raise ValueError("Passage belongs to another meeting or company")
        if date.fromisoformat(passage["filed"]) >= cutoff:
            raise ValueError("Passage was unavailable before decision cutoff")
        if not re.fullmatch(r"[0-9a-f]{64}", passage["sha256"]):
            raise ValueError("Missing source checksum")
        if not passage["url"].startswith("https://www.sec.gov/Archives/edgar/data/"):
            raise ValueError("Only original SEC filing sources are supported")
        if (passage["id"] in ids or not passage["text"] or not 0 <= passage["start"] < passage["end"]
                or passage["end"] - passage["start"] != len(passage["text"])):
            raise ValueError("Invalid or duplicate evidence passage")
        ids.add(passage["id"])
    if len(ids) > 6 or POLICY_GAP not in bundle["missing"]:
        raise ValueError("Evidence budget or policy gap is invalid")
    return bundle


class EvidenceRetriever:
    def __init__(self, path=DEFAULT_INDEX, embedder=None):
        self.index = RagIndex(path, embedder=embedder)
        if embedder is None:
            if self.index.info["model"] != MODEL or self.index.info["model_assets"] != model_fingerprint():
                self.index.close()
                raise ValueError("Evidence embedding source does not match local model")
        self.embedder = embedder
        self.lexical = HashingVectorizer(n_features=2**18, ngram_range=(1, 2),
                                        alternate_sign=False, norm="l2", stop_words="english")
        self._meetings = {m["meeting_id"]: m for m in self.index.meetings()}
        self._loaded, self._vectors = {}, {}

    def close(self):
        self.index.close()

    def _meeting(self, row):
        meeting_id = row["meeting_id"]
        if meeting_id in self._loaded:
            return self._loaded[meeting_id]
        rows = self.index.con.execute("SELECT data, vector FROM chunks WHERE meeting_id=? ORDER BY id", (meeting_id,)).fetchall()
        passages, dense, documents = [], [], {}
        cutoff = date.fromisoformat(row["meeting_date"]) - timedelta(days=5)
        for stored in rows:
            passage = json.loads(stored["data"])
            if passage["document_id"] not in documents:
                document = self.index.document(passage["document_id"])
                raw = Path(document["file"]).read_bytes()
                if sha256(raw).hexdigest() != document["sha256"]:
                    raise ValueError("Original filing bytes changed")
                if extract_html(raw.decode("utf-8-sig", errors="replace"))[0] != document["text"]:
                    raise ValueError("Indexed document differs from original filing text")
                documents[passage["document_id"]] = document
            document = documents[passage["document_id"]]
            for key in ("meeting_id", "company_id", "meeting_date", "filed", "url"):
                if passage[key] != document[key]:
                    raise ValueError("Passage provenance differs from source document")
            if any(passage[key] != row[key] for key in ("meeting_id", "company_id", "meeting_date")):
                raise ValueError("Evidence query identity does not match indexed meeting")
            if date.fromisoformat(passage["filed"]) >= cutoff:
                raise ValueError("Index contains a filing after decision cutoff")
            if document["text"][passage["start"]:passage["end"]] != passage["text"]:
                raise ValueError("Passage quote does not match exact source offsets")
            clean = {key: passage[key] for key in PASSAGE_FIELDS if key != "sha256"}
            clean["sha256"] = document["sha256"]
            passages.append(clean)
            dense.append(np.frombuffer(stored["vector"], dtype="<f4"))
        result = (passages, np.asarray(dense), self.lexical.transform(p["text"] for p in passages)) if passages else ([], None, None)
        self._loaded[meeting_id] = result
        return result

    def _prime(self, queries):
        missing = sorted(set(queries) - self._vectors.keys())
        if missing:
            self.embedder = self.embedder or load_model(download=False)
            vectors = unit_vectors(list(self.embedder.query_embed(missing, batch_size=32)))
            if len(vectors) != len(missing):
                raise ValueError("Query embedding count mismatch")
            self._vectors.update(zip(missing, vectors))

    def validate(self, bundle):
        """Validate outbound passages against the source-checked index records."""
        validate_evidence(bundle)
        passages, _, _ = self._meeting(bundle["query"])
        source = {passage["id"]: passage for passage in passages}
        if any(source.get(passage["id"]) != passage for passage in bundle["passages"]):
            raise ValueError("Outbound evidence differs from verified source passage")
        return bundle

    def retrieve(self, row):
        row = clean_query(row)
        passages, dense, lexical = self._meeting(row)
        bundle = {"query": row, "strategy": STRATEGY, "passages": [], "rules": [], "missing": [POLICY_GAP]}
        if not passages:
            bundle["missing"].append("No eligible original filing is indexed for this meeting.")
            return self.validate(bundle)
        queries = queries_for(row)
        self._prime(queries)
        rankings = []
        with threadpool_limits(limits=1):
            for query in queries:
                similarities = dense @ self._vectors[query]
                lexical_scores = (lexical @ self.lexical.transform([query]).T).toarray().ravel()
                scores = np.zeros(len(passages))
                lexical_order = np.argsort(-lexical_scores, kind="stable")
                lexical_order = lexical_order[lexical_scores[lexical_order] > 0]
                for order in (np.argsort(-similarities, kind="stable"), lexical_order):
                    for rank, index in enumerate(order, 1):
                        scores[index] += 1 / (60 + rank)
                rankings.append(list(np.argsort(-scores, kind="stable")))
        # Give the proposal two slots, then add facts from fixed topic questions.
        # Selection never consults current or historical vote outcomes.
        order = rankings[0][:2]
        for rank in range(len(passages)):
            for ranking in rankings:
                if rank < len(ranking):
                    order.append(ranking[rank])
        chosen, normalized = [], set()
        for index in order:
            candidate = passages[index]
            text = " ".join(candidate["text"].lower().split())
            if text in normalized:
                continue
            if any(candidate["document_id"] == old["document_id"] and
                   max(0, min(candidate["end"], old["end"]) - max(candidate["start"], old["start"])) /
                   min(candidate["end"] - candidate["start"], old["end"] - old["start"]) > 0.35 for old in chosen):
                continue
            chosen.append(dict(candidate))
            normalized.add(text)
            if len(chosen) == 6:
                break
        bundle["passages"] = chosen
        return self.validate(bundle)

    def retrieve_many(self, rows):
        rows = [clean_query(row) for row in rows]
        keys = [f"{row['meeting_id']}:{row['item_no']}" for row in rows]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate ballot identities")
        self._prime(query for row in rows if row["meeting_id"] in self._meetings for query in queries_for(row))
        return {key: self.retrieve(row) for key, row in zip(keys, rows)}


def coverage(bundles):
    rows = list(bundles.values())
    return {"proposals": len(rows), "meetings": len({b["query"]["meeting_id"] for b in rows}),
            "proposals_with_filings": sum(bool(b["passages"]) for b in rows),
            "meetings_with_filings": len({b["query"]["meeting_id"] for b in rows if b["passages"]}),
            "unique_passages": len({p["id"] for b in rows for p in b["passages"]}),
            "rules": 0, "missing": dict(Counter(m for b in rows for m in b["missing"]))}


def build_evidence_index(corpus, path, reuse_paths=()):
    """Reuse only vectors with matching model assets and exact source/chunk data.

    Cached vectors are independent of vote outcomes. The newly published index
    records every reused index checksum and the number of new computations.
    """
    from local_rag import create_index, embedding_text
    path = Path(path)
    if path.exists():
        raise ValueError("Index already exists; choose a new path")
    model = load_model(download=True)
    assets = model_fingerprint()
    expected = {chunk["id"]: chunk for chunk in corpus["chunks"]}
    documents = {document["id"]: document for document in corpus["documents"]}
    cached, sources = {}, []
    duplicate_vectors, maximum_duplicate_difference = 0, 0.0
    for source in sorted({Path(value).resolve() for value in reuse_paths}):
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as con:
            info = json.loads(con.execute("SELECT value FROM metadata").fetchone()[0])
            if info["model"] != MODEL or info["model_assets"] != assets:
                raise ValueError("Cached embedding model assets do not match")
            checked_documents = set()
            for key, raw in con.execute("SELECT id,data FROM documents"):
                doc = json.loads(raw)
                if key in documents and doc == documents[key]:
                    checked_documents.add(key)
            reused = 0
            for raw, encoded in con.execute("SELECT data,vector FROM chunks ORDER BY id"):
                chunk = json.loads(raw)
                original = expected.get(chunk["id"])
                if not original or chunk["document_id"] not in checked_documents:
                    continue
                if any(original.get(key) != value for key, value in chunk.items()):
                    continue
                vector = np.frombuffer(encoded, dtype="<f4").copy()
                if len(vector) != info["dimension"] or not np.isfinite(vector).all() or not np.isclose(np.linalg.norm(vector), 1, atol=1e-5):
                    raise ValueError("Invalid cached embedding")
                if chunk["id"] in cached:
                    # Equivalent ONNX batches can differ by small floating-point
                    # amounts. The canonical first source remains deterministic.
                    if float(cached[chunk["id"]] @ vector) < 0.99999:
                        raise ValueError("Conflicting cached embeddings for identical source")
                    duplicate_vectors += 1
                    maximum_duplicate_difference = max(maximum_duplicate_difference,
                                                       float(np.max(np.abs(cached[chunk["id"]] - vector))))
                else:
                    cached[chunk["id"]] = vector
                    reused += 1
            sources.append({"path": str(source), "sha256": sha256(source.read_bytes()).hexdigest(), "reused_chunks": reused})
    chunks = corpus["chunks"]
    reuse = {"source_indexes": sources, "reused_chunks": len(cached), "newly_embedded_chunks": len(chunks) - len(cached),
             "duplicate_vectors": duplicate_vectors, "maximum_duplicate_component_difference": maximum_duplicate_difference,
             "duplicate_selection": "First source in canonical path order; duplicate cosine must be at least0.99999",
             "validation": "Exact document and chunk metadata/text; identical BGE asset hashes; finite unit vectors"}
    print(json.dumps(reuse), flush=True)

    class ReusingEmbedder:
        def passage_embed(self, texts, batch_size=32):
            if texts != [embedding_text(chunk) for chunk in chunks]:
                raise ValueError("Embedding input differs from verified corpus")
            missing = [text for text, chunk in zip(texts, chunks) if chunk["id"] not in cached]
            fresh = iter(model.passage_embed(missing, batch_size=batch_size)) if missing else iter(())
            completed = 0
            for chunk in chunks:
                if chunk["id"] in cached:
                    yield cached[chunk["id"]]
                else:
                    yield next(fresh)
                    completed += 1
                    if completed % 256 == 0 or completed == len(missing):
                        print(f"Embedded {completed}/{len(missing)} new filing passages", flush=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".evidence-build-", dir=path.parent) as directory:
        staged = Path(directory) / "index.sqlite"
        info = create_index(corpus, staged, embedder=ReusingEmbedder())
        # create_index marks externally supplied embeddings as test data by default.
        # Here their provenance was verified against actual BGE model assets above.
        info.update(model=MODEL, model_assets=assets, fastembed_version=importlib.metadata.version("fastembed"),
                    embedding_reuse=reuse)
        with sqlite3.connect(staged) as con:
            con.execute("UPDATE metadata SET value=?", (json.dumps(info),))
        os.link(staged, path)
    return info


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--output", type=Path, default=DEFAULT_INDEX.parent / "calibration-evidence.json")
    parser.add_argument("--build", action="store_true", help="Build a new index from all eligible original 2024 filings")
    parser.add_argument("--reuse-index", action="append", type=Path,
                        help="Verified existing filing index to reuse; default: available existing project indices")
    args = parser.parse_args(argv)
    if args.build:
        if args.index.exists():
            parser.error("Index already exists; choose a new path")
        from rag_corpus import build_corpus
        corpus = build_corpus(year="2024")
        print(f"Embedding {len(corpus['chunks'])} passages from {len(corpus['documents'])} dated filings", flush=True)
        reuse_paths = args.reuse_index if args.reuse_index is not None else [value for value in DEFAULT_REUSE if value.is_file()]
        info = build_evidence_index(corpus, args.index, reuse_paths)
        print(json.dumps({key: info[key] for key in ("documents", "chunks", "by_year", "skipped")}, indent=2))
        return
    if args.output.exists():
        parser.error("Output already exists; choose a new path")
    from board_experiment import load_temporal
    _, calibration, _ = load_temporal()
    inputs = calibration.loc[:, list(INPUT_FIELDS)].to_dict("records")
    retriever = EvidenceRetriever(args.index)
    try:
        bundles = retriever.retrieve_many(inputs)
    finally:
        retriever.close()
    result = {"version": 1, "strategy": STRATEGY, "index_sha256": sha256(args.index.read_bytes()).hexdigest(),
              "filing_dates_source": "SEC filing dates recorded in data/meetings/us.csv, never download or file modification dates",
              "filing_index_sha256": sha256((ROOT / "data/meetings/us.csv").read_bytes()).hexdigest(),
              "input_fields": list(INPUT_FIELDS), "coverage": coverage(bundles),
              "historical_training_coverage": "No original filing sources are available for 2019–2023.",
              "policy_status": POLICY_GAP, "bundles": bundles}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps(result["coverage"], indent=2))


if __name__ == "__main__":
    main()
