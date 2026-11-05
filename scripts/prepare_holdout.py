"""Rebuild the frozen three-meeting holdout from pinned public issuer PDFs.

No model or NBIM API calls occur here. Downloading is an explicit convenience;
references are the separately reviewed, committed public voting intentions.
"""
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from urllib.request import Request, urlopen

from voting_assistant.contracts import Agenda, MeetingReference
from voting_assistant.evaluation import load_manifest

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "data/meetings/holdout-2025-plan.json"
FREEZE = ROOT / "data/meetings/holdout-2025-freeze.json"
POLICY_HASH = "cde5f906ff68e4c13a0408a9b516ca346c821f642db3603405c1736cf7d6378c"


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def page_text(text: str) -> str:
    """Normalize PDF layout whitespace, preserving every extracted word and line."""
    return "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())


def build_agenda(meeting: dict, source_dir: Path) -> dict:
    raw = (source_dir / meeting["source_file"]).read_bytes()
    if sha256(raw).hexdigest() != meeting["source"]["sha256"]:
        raise ValueError(f"Issuer PDF checksum changed: {meeting['meeting_id']}")
    pages = subprocess.run(
        ["pdftotext", "-layout", "-", "-"], input=raw, capture_output=True, check=True
    ).stdout.decode("utf-8").split("\f")
    proposals = []
    for proposal in meeting["proposals"]:
        evidence = []
        for page in proposal["evidence_pages"]:
            if page < 1 or page > len(pages) or not page_text(pages[page - 1]):
                raise ValueError("Issuer PDF has an empty or missing evidence page")
            evidence.append({
                **meeting["source"], "page": page,
                "section": f"Proposal {proposal['proposal_id']}",
                "quote": page_text(pages[page - 1]),
            })
        proposals.append({
            "proposal_id": proposal["proposal_id"],
            "original_text": proposal["original_text"],
            "proposal_type": proposal["proposal_type"], "sources": evidence,
        })
    agenda = {
        "meeting_id": meeting["meeting_id"], "company_id": meeting["company_id"],
        "meeting_date": meeting["meeting_date"],
        "document_source": meeting["source"], "proposals": proposals,
    }
    Agenda.model_validate(agenda)
    return agenda


def checked_reference(meeting: dict) -> dict:
    reference = json.loads((ROOT / meeting["reference_file"]).read_text())
    parsed = MeetingReference.model_validate(reference)
    if parsed.vote_semantics != "voting_intention" or parsed.meeting_id != meeting["meeting_id"]:
        raise ValueError("Unexpected reference identity or semantics")
    if [v.proposal_id for v in parsed.votes] != [p["proposal_id"] for p in meeting["proposals"]]:
        raise ValueError("Reference order/coverage differs from frozen proposal mapping")
    return reference


def prepare(source_dir: Path, development_manifest: Path, output_dir: Path) -> Path:
    plan = json.loads(PLAN.read_text())
    freeze = json.loads(FREEZE.read_text())
    if sha256(PLAN.read_bytes()).hexdigest() != freeze["plan_sha256"]:
        raise ValueError("Holdout plan changed after freezing")
    _, development, _ = load_manifest(development_manifest)
    expected = plan["development_meetings"]
    if [m.agenda.meeting_id for m in development] != expected:
        raise ValueError("Development manifest must contain exactly CCC then Sprinklr")
    if any(m.agenda.meeting_date.isoformat() >= plan["meetings"][0]["meeting_date"] for m in development):
        raise ValueError("Development meetings must precede every holdout meeting")
    # Materialize and validate every input before touching the destination.
    payloads = {}
    entries = []
    for meeting in development:
        entries.append(("development", meeting.agenda.meeting_id,
                        meeting.agenda.model_dump(mode="json", exclude_none=True),
                        meeting.reference.model_dump(mode="json", exclude_none=True)))
    for meeting in plan["meetings"]:
        key = meeting["meeting_id"]
        agenda, reference = build_agenda(meeting, source_dir), checked_reference(meeting)
        if sha256(encoded(agenda)).hexdigest() != freeze["test_agendas"][key]:
            raise ValueError("Extracted agenda differs from frozen bytes; inspect PDF extraction version")
        if sha256(encoded(reference)).hexdigest() != freeze["test_references"][key]:
            raise ValueError("Holdout reference changed after freezing")
        entries.append(("test", key, agenda, reference))
    meetings = []
    for split, key, agenda, reference in entries:
        files = {}
        for kind, value in (("agenda", agenda), ("reference", reference)):
            name = f"{key}-{kind}.json"
            raw = encoded(value)
            payloads[name] = raw
            files[kind] = {"path": name, "sha256": sha256(raw).hexdigest()}
        meetings.append({"split": split, **files})
    manifest = encoded({
        "version": 1, "dataset_kind": "nbim_verified", "split": "test",
        "meetings": meetings, "policy_documents": {"2025-05-13": POLICY_HASH},
    })
    payloads["manifest.json"] = manifest
    # Never replace a source, a development input, or a previous run's files.
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Use an empty output directory; frozen inputs are never overwritten")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, raw in payloads.items():
        (output_dir / name).write_bytes(raw)
    result = output_dir / "manifest.json"
    load_manifest(result)
    return result


def download(source_dir: Path) -> None:
    plan = json.loads(PLAN.read_text())
    source_dir.mkdir(parents=True, exist_ok=True)
    for meeting in plan["meetings"]:
        target = source_dir / meeting["source_file"]
        if target.exists():
            if sha256(target.read_bytes()).hexdigest() != meeting["source"]["sha256"]:
                raise ValueError(f"Existing source checksum changed: {target.name}")
            continue
        request = Request(meeting["source"]["url"], headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=45) as response:
            raw = response.read()
        if sha256(raw).hexdigest() != meeting["source"]["sha256"]:
            raise ValueError(f"Downloaded source checksum changed: {target.name}")
        target.write_bytes(raw)


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("data/raw/holdout-sources"))
    parser.add_argument("--development-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw/holdout-2025"))
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    try:
        if args.download:
            download(args.source_dir)
        result = prepare(args.source_dir, args.development_manifest, args.output_dir)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Could not prepare holdout: {error}\n")
    print(result)
    print(f"Manifest SHA-256: {sha256(result.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
