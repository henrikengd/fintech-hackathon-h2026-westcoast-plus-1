"""Load one manually matched meeting from the organizer's real-vote export."""

import csv
import hashlib
import io
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Literal, TypedDict

VoteText = Literal["FOR", "MOT", "AVSTÅ"]

_VOTES: dict[str, VoteText | None] = {
    "": None,
    "none": None,
    "do not vote": None,
    "one year": None,
    "two years": None,
    "three years": None,
    "for": "FOR",
    "against": "MOT",
    "withhold": "MOT",
    "abstain": "AVSTÅ",
}
_REQUIRED_COLUMNS = {
    "meeting_id", "company_id", "meeting_date", "item_no",
    "nbim_vote_raw", "nbim_vote",
}
_NPX_COLUMNS = {"split_year", "n_funds", "funds_disagree"}


class ImportedVote(TypedDict):
    proposal_id: str
    vote: VoteText | None
    board_recommendation: VoteText | None
    raw_vote: str


class ImportedReference(TypedDict):
    meeting_id: str
    source: dict[str, str]
    vote_semantics: Literal["unverified"]
    votes: list[ImportedVote]


def load_organizer_reference(
    path: Path,
    *,
    sha256: str,
    export_version: str,
    received_on: date,
    meeting_id: str,
    company_id: str,
    meeting_date: date,
    proposal_crosswalk: Mapping[str, str],
    board_recommendations: Mapping[str, VoteText] | None = None,
    source_meeting_id: str | None = None,
) -> ImportedReference:
    """Return MeetingReference data without reading proposal text into the result.

    Crosswalk keys are verified CSV item numbers. Values are agenda proposal
    IDs, supplied in the agenda's order after checking the original notice.
    Use source_meeting_id when the export has its own meeting identifier.
    Board recommendations come from that notice and are keyed by proposal ID.
    Source document_date records delivery of the export, whose actual date of
    compilation is unknown.
    """
    if not all(value.strip() for value in (meeting_id, company_id, export_version)):
        raise ValueError("Meeting ID, company ID and export version are required")
    if (
        not proposal_crosswalk
        or any(not key.strip() or not value.strip() for key, value in proposal_crosswalk.items())
        or len(set(proposal_crosswalk.values())) != len(proposal_crosswalk)
    ):
        raise ValueError("Proposal crosswalk must be nonempty and one-to-one")
    board = board_recommendations or {}
    if not board.keys() <= set(proposal_crosswalk.values()) or any(
        vote not in {"FOR", "MOT", "AVSTÅ"} for vote in board.values()
    ):
        raise ValueError("Invalid notice-sourced board recommendation")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != sha256:
        raise ValueError("Organizer reference checksum mismatch")

    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
    columns = reader.fieldnames or []
    if (
        len(set(columns)) != len(columns)
        or not _REQUIRED_COLUMNS <= set(columns)
        or _NPX_COLUMNS.intersection(columns)
    ):
        raise ValueError("Expected organizer real_votes.csv schema")
    matching: dict[str, ImportedVote] = {}
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"Invalid CSV row width at line {reader.line_num}")
        if row["meeting_id"] != (source_meeting_id or meeting_id):
            continue
        if row["company_id"] != company_id or row["meeting_date"] != meeting_date.isoformat():
            raise ValueError(f"Meeting identity mismatch at line {reader.line_num}")
        item_no = row["item_no"]
        if item_no not in proposal_crosswalk or item_no in matching:
            raise ValueError(f"Unexpected or repeated item at line {reader.line_num}")
        raw_vote = row["nbim_vote_raw"]
        value = raw_vote.strip().casefold()
        if value not in _VOTES:
            raise ValueError(f"Unknown raw vote at line {reader.line_num}")
        vote = _VOTES[value]
        if row["nbim_vote"].strip() != (vote or ""):
            raise ValueError(f"Normalized vote differs from raw vote at line {reader.line_num}")
        proposal_id = proposal_crosswalk[item_no]
        matching[item_no] = {
            "proposal_id": proposal_id,
            "vote": vote,
            "raw_vote": raw_vote,
            "board_recommendation": board.get(proposal_id),
        }
    if matching.keys() != proposal_crosswalk.keys():
        raise ValueError("Reference export does not cover the entire proposal crosswalk")
    return {
        "meeting_id": meeting_id,
        "source": {
            "document": path.name,
            "document_date": received_on.isoformat(),
            "version": export_version,
            "sha256": digest,
        },
        "vote_semantics": "unverified",
        "votes": [matching[item_no] for item_no in proposal_crosswalk],
    }
