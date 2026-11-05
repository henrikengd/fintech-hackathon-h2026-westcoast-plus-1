"""Prepare the checked public pilot meetings from a pinned issuer PDF."""
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROXY_URL = (
    "https://investors.sprinklr.com/financial-information/all-sec-filings/"
    "content/0001140361-25-017121/0001140361-25-017121.pdf"
)
PROXY_SHA256 = "23dc506b308b7a76276d1945a4c61449d261d7e4066ba49f8247c5b2eb35e170"
SPRINKLR_PROPOSALS = (
    ("1a", "Elect Jan R. Hauser", "director_election", (2, 13, 14, 15)),
    ("1b", "Elect Kevin Haverty", "director_election", (2, 13, 14, 15)),
    ("1c", "Elect Ragy Thomas", "director_election", (2, 13, 14, 15)),
    ("2", "Advisory vote on executive compensation", "say_on_pay", (2, 23, 26, 27, 28, 32, 40, 42)),
    ("3", "Ratify KPMG LLP as auditor", "auditor_ratification", (2, 61)),
)


def write_json(directory: Path, name: str, value: object) -> dict[str, str]:
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    (directory / name).write_bytes(payload)
    return {"path": name, "sha256": sha256(payload).hexdigest()}


def prepare(proxy: Path, directory: Path, split: str) -> None:
    raw = proxy.read_bytes()
    if sha256(raw).hexdigest() != PROXY_SHA256:
        raise ValueError("Sprinklr proxy PDF checksum differs from the verified edition")
    # Keep the verified one-based PDF page numbers when extracting evidence.
    pages = subprocess.run(
        ["pdftotext", "-layout", "-", "-"],
        input=raw, check=True, capture_output=True,
    ).stdout.decode("utf-8").split("\f")
    source = {
        "document": "Sprinklr 2025 definitive proxy statement",
        "url": PROXY_URL, "document_date": "2025-05-02",
        "version": "0001140361-25-017121", "sha256": PROXY_SHA256,
    }
    proposals = [
        {
            "proposal_id": item, "original_text": text, "proposal_type": kind,
            "sources": [
                {**source, "page": page, "section": f"Proposal {item}",
                 "quote": pages[page - 1].strip()}
                for page in evidence_pages
            ],
        }
        for item, text, kind, evidence_pages in SPRINKLR_PROPOSALS
    ]
    if any(not evidence["quote"] for proposal in proposals for evidence in proposal["sources"]):
        raise ValueError("Proxy text extraction returned an empty evidence page")
    agenda = {
        "meeting_id": "sprinklr-2025-06-12", "company_id": "sec-cik-1569345",
        "meeting_date": "2025-06-12", "document_source": source, "proposals": proposals,
    }
    generated = {"manifest.json"} | {
        f"{meeting}-{kind}.json"
        for meeting in ("ccc-2025-05-22", "sprinklr-2025-06-12")
        for kind in ("agenda", "reference")
    }
    if proxy.resolve() in {(directory / name).resolve() for name in generated}:
        raise ValueError("Pilot output must be separate from the source PDF")
    directory.mkdir(parents=True, exist_ok=True)
    meetings = []
    for key, cohort, meeting in (
        ("ccc-2025-05-22", "development", json.loads(
            (ROOT / "data/meetings/ccc-2025-05-22.json").read_text(encoding="utf-8")
        )),
        ("sprinklr-2025-06-12", "test", agenda),
    ):
        ref = json.loads((ROOT / f"data/reference/{key}.json").read_text(encoding="utf-8"))
        meetings.append({
            "split": cohort,
            "agenda": write_json(directory, f"{key}-agenda.json", meeting),
            "reference": write_json(directory, f"{key}-reference.json", ref),
        })
    write_json(directory, "manifest.json", {
        "version": 1, "dataset_kind": "nbim_verified", "split": split, "meetings": meetings,
        "policy_documents": {
            "2025-05-13": "cde5f906ff68e4c13a0408a9b516ca346c821f642db3603405c1736cf7d6378c",
        },
    })


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--sprinklr-proxy", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw/pilot"))
    parser.add_argument("--split", choices=("development", "test"), default="test")
    args = parser.parse_args()
    try:
        prepare(args.sprinklr_proxy, args.output_dir, args.split)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Could not prepare pilot: {error}\n")
    print(args.output_dir / "manifest.json")


if __name__ == "__main__":
    main()
