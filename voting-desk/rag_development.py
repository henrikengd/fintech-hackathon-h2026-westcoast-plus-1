"""Prepare the 2024 RAG development corpus inside the existing training partition."""
import argparse
import json
from pathlib import Path

import dataset
from local_rag import create_index
from rag_corpus import build_corpus


def corpus(limit=None):
    frames = dataset.load_split()
    train = frames["train"]
    allowed = set(train.loc[train.meeting_date.str.startswith("2024-"), "meeting_id"].astype(str))
    sources = build_corpus(year="2024")
    documents = [doc for doc in sources["documents"] if doc["meeting_id"] in allowed]
    documents.sort(key=lambda doc: (doc["meeting_date"], doc["meeting_id"]))
    if limit is not None:
        if limit < 1:
            raise ValueError("Limit must be positive")
        documents = documents[:limit]
    selected = {doc["id"] for doc in documents}
    return {"documents": documents,
            "chunks": [chunk for chunk in sources["chunks"] if chunk["document_id"] in selected],
            "skipped": sources["skipped"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/local-rag/development-2024.sqlite"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--build", action="store_true", help="Embed and create a new index; otherwise just show corpus size")
    args = parser.parse_args(argv)
    selected = corpus(args.limit)
    result = {"documents": len(selected["documents"]), "chunks": len(selected["chunks"]),
              "meeting_ids": [d["meeting_id"] for d in selected["documents"]]}
    if args.build:
        result["index"] = create_index(selected, args.db)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
