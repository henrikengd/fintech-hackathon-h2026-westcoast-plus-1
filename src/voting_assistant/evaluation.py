"""Run a frozen meeting split and score votes with reference data kept separate."""

import argparse
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, Field, ValidationError

from .cli import CliError
from .contracts import Agenda, Assessment, Contract, MeetingReference, NonEmpty, Sha256, Vote

Split = Literal["development", "test"]
DatasetKind = Literal["synthetic", "nbim_candidate", "nbim_verified"]
ManifestData = TypeVar("ManifestData", Agenda, MeetingReference)


class FileEntry(Contract):
    path: NonEmpty
    sha256: Sha256


class MeetingEntry(Contract):
    split: Split
    agenda: FileEntry
    reference: FileEntry


class Manifest(Contract):
    version: Literal[1]
    dataset_kind: DatasetKind
    split: Split = "test"
    meetings: list[MeetingEntry]
    policy_documents: dict[NonEmpty, Sha256] = Field(default_factory=dict)


@dataclass(frozen=True)
class Meeting:
    split: Split
    agenda: Agenda
    reference: MeetingReference


class Assessor(Protocol):
    def __call__(
        self, agenda: Agenda, remaining: Decimal, on_cost: Callable[[Decimal], None]
    ) -> BaseModel: ...


def _bytes(path: Path, description: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        raise CliError(f"cannot read {description}") from None


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_entry(
    directory: Path, entry: FileEntry, schema: type[ManifestData]
) -> ManifestData:
    path = Path(entry.path)
    if path.is_absolute():
        raise CliError("manifest file paths must be relative")
    raw = _bytes(directory / path, schema.__name__)
    if _sha(raw) != entry.sha256:
        raise CliError(f"{schema.__name__} checksum differs from manifest")
    try:
        return schema.model_validate_json(raw)
    except ValidationError:
        raise CliError(f"invalid {schema.__name__} in manifest") from None


def load_manifest(path: Path) -> tuple[Manifest, list[Meeting], str]:
    raw = _bytes(path, "manifest")
    try:
        manifest = Manifest.model_validate_json(raw)
    except ValidationError:
        raise CliError("invalid evaluation manifest") from None

    meetings = []
    seen = set()
    for entry in manifest.meetings:
        agenda = _read_entry(path.parent, entry.agenda, Agenda)
        reference = _read_entry(path.parent, entry.reference, MeetingReference)
        if agenda.meeting_id in seen:
            raise CliError("meeting occurs more than once in the manifest")
        seen.add(agenda.meeting_id)
        if reference.meeting_id != agenda.meeting_id or {
            vote.proposal_id for vote in reference.votes
        } != {proposal.proposal_id for proposal in agenda.proposals}:
            raise CliError("reference meeting or proposal IDs differ from the agenda")
        if manifest.dataset_kind == "nbim_verified" and reference.vote_semantics not in {
            "voting_intention", "cast_vote",
        }:
            raise CliError("verified NBIM dataset requires verified vote semantics")
        if (manifest.dataset_kind == "synthetic") != (reference.vote_semantics == "synthetic"):
            raise CliError("synthetic references require a synthetic dataset")
        sources = [
            agenda.document_source,
            *(source for proposal in agenda.proposals for source in proposal.sources),
        ]
        if any(source.document_date > agenda.meeting_date for source in sources):
            raise CliError("agenda contains a source dated after the meeting")
        meetings.append(Meeting(entry.split, agenda, reference))

    development = [m.agenda.meeting_date for m in meetings if m.split == "development"]
    test = [m.agenda.meeting_date for m in meetings if m.split == "test"]
    if development and test and max(development) >= min(test):
        raise CliError("test meetings must all be later than development meetings")
    return manifest, meetings, _sha(raw)


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _metrics(pairs: list[tuple[Vote, Vote | None]]) -> dict:
    counts = dict.fromkeys(("tp", "fp", "tn", "fn"), 0)
    for truth, predicted in pairs:
        if truth == Vote.MOT:
            counts["tp" if predicted == Vote.MOT else "fn"] += 1
        else:
            counts["fp" if predicted == Vote.MOT else "tn"] += 1
    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    return {
        **counts,
        "scored": len(pairs),
        "reference_mot": tp + fn,
        "mot_precision": _ratio(tp, tp + fp),
        "mot_recall": _ratio(tp, tp + fn),
    }


def _assessments(run: dict, agenda: Agenda) -> dict[str, Assessment]:
    expected = {proposal.proposal_id for proposal in agenda.proposals}
    try:
        results = [Assessment.model_validate(item) for item in run.get("assessments", [])]
    except (ValidationError, TypeError):
        return {}
    counts = Counter(item.proposal_id for item in results)
    return {
        item.proposal_id: item for item in results
        if item.proposal_id in expected and counts[item.proposal_id] == 1
    }


def _complete(run: dict, agenda: Agenda) -> bool:
    actual = _assessments(run, agenda)
    expected = [proposal.proposal_id for proposal in agenda.proposals]
    return (
        run.get("status") == "complete"
        and not run.get("errors")
        and not any(item.validation_errors for item in actual.values())
        and list(actual) == expected
        and len(run.get("assessments", [])) == len(expected)
    )


def summarize(meetings: list[Meeting], runs: dict[str, dict]) -> dict:
    model_pairs = []
    board_pairs = []
    counts = dict.fromkeys(("assessed", "manual_review", "missing_output", "missing_reference"), 0)
    types: Counter[str] = Counter()
    semantics: Counter[str] = Counter()
    manual_counts = dict.fromkeys(("valid_manual_review", "validation_failed_manual_review", "unclassified_manual_review"), 0)
    validation_error_rows = []
    exclusions = []
    meeting_errors = []
    complete = 0
    for meeting in meetings:
        agenda = meeting.agenda
        semantics[meeting.reference.vote_semantics] += 1
        run = runs.get(agenda.meeting_id, {})
        complete += _complete(run, agenda)
        results = _assessments(run, agenda)
        raw_rows = run.get("assessments", [])
        raw_results = {
            item.get("proposal_id"): item for item in raw_rows if isinstance(item, dict)
        } if isinstance(raw_rows, list) else {}
        if run.get("errors"):
            meeting_errors.append({"meeting_id": agenda.meeting_id, "errors": run["errors"]})
        refs = {vote.proposal_id: vote for vote in meeting.reference.votes}
        for proposal in agenda.proposals:
            types[proposal.proposal_type or "unknown"] += 1
            assessment = results.get(proposal.proposal_id)
            counts[assessment.status if assessment else "missing_output"] += 1
            if assessment and assessment.status == "manual_review":
                if assessment.validation_errors:
                    manual_counts["validation_failed_manual_review"] += 1
                    validation_error_rows.append({
                        "meeting_id": agenda.meeting_id, "proposal_id": proposal.proposal_id,
                        "errors": assessment.validation_errors,
                    })
                elif "validation_errors" not in raw_results[proposal.proposal_id] and run.get("errors"):
                    # Old reports do not distinguish row-level failures from genuine missing facts.
                    manual_counts["unclassified_manual_review"] += 1
                else:
                    manual_counts["valid_manual_review"] += 1
            ref = refs[proposal.proposal_id]
            if ref.vote is None:
                counts["missing_reference"] += 1
                exclusions.append({
                    "meeting_id": agenda.meeting_id, "proposal_id": proposal.proposal_id,
                    "reason": "reference_vote_unavailable",
                })
                continue
            model_pairs.append((ref.vote, assessment.recommendation if assessment else None))
            board_pairs.append((ref.vote, ref.board_recommendation))
    dated = sorted(meeting.agenda.meeting_date.isoformat() for meeting in meetings)
    num_proposals = sum(types.values())
    use_board = bool(board_pairs) and all(board is not None for _, board in board_pairs)
    baseline = board_pairs if use_board else [(vote, None) for vote, _ in board_pairs]
    return {
        "status": "complete" if meetings and complete == len(meetings) else "partial",
        "meetings": len(meetings),
        "complete_meetings": complete,
        "incomplete_meetings": len(meetings) - complete,
        "date_from": dated[0] if dated else None,
        "date_to": dated[-1] if dated else None,
        "proposals": num_proposals,
        "proposal_types": dict(types),
        "reference_semantics_by_meeting": dict(semantics),
        "reference_limitations": (
            ["Reference export semantics are unverified."] if semantics.get("unverified") else []
        ),
        **counts,
        **manual_counts,
        "validation_error_rows": validation_error_rows,
        "meeting_errors": meeting_errors,
        "exclusions": exclusions,
        "recommendation_coverage": _ratio(counts["assessed"], num_proposals),
        "model": _metrics(model_pairs),
        "baseline": {
            "name": "stem_som_styret" if use_board else "aldri_mot",
            "reason": None if use_board else "board recommendations missing or no scorable proposals",
            "missing_board_for_scored": sum(board is None for _, board in board_pairs),
            **_metrics(baseline),
        },
    }


def _money(value: str | Decimal) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        raise CliError("invalid cost or price") from None
    if not result.is_finite() or result < 0:
        raise CliError("cost and prices must be finite and nonnegative")
    return result


def _save(path: Path, report: dict) -> None:
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _lock(output: Path) -> Iterator[None]:
    output.parent.mkdir(parents=True, exist_ok=True)
    # Keep the lock inode stable. Removing a lock file can race another process.
    with output.with_name(output.name + ".lock").open("a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CliError("another evaluation is writing this output") from None
        yield


def _load_run(output: Path, config: dict, resume: bool) -> dict:
    if not output.exists():
        if resume:
            raise CliError("no previous output to resume")
        return {"configuration": config, "spent_usd": "0", "runs": {}, "attempts": {}}
    if not resume:
        raise CliError("output exists; choose a new output or use --resume")
    try:
        previous = json.loads(output.read_text(encoding="utf-8"))
        if (
            not isinstance(previous, dict)
            or previous.get("configuration") != config
            or not isinstance(previous.get("runs"), dict)
            or not all(isinstance(run, dict) for run in previous["runs"].values())
            or not isinstance(previous.get("attempts"), dict)
        ):
            raise CliError("checkpoint configuration differs or is invalid")
        _money(previous["spent_usd"])
        for attempts in previous["attempts"].values():
            if not isinstance(attempts, list):
                raise CliError("invalid attempt history")
            for attempt in attempts:
                if (
                    not isinstance(attempt, dict)
                    or attempt.get("status") not in {"running", "interrupted", "complete", "partial"}
                    or not isinstance(attempt.get("reason"), str)
                    or not isinstance(attempt.get("started_at"), str)
                    or not isinstance(attempt.get("run"), (dict, type(None)))
                ):
                    raise CliError("invalid attempt history")
                _money(attempt["cost_usd"])
    except (KeyError, json.JSONDecodeError, UnicodeError):
        raise CliError("invalid checkpoint") from None
    return previous


def _unassessed(agenda: Agenda, reason: str) -> dict:
    return {
        "status": "partial",
        "assessments": [
            Assessment(
                proposal_id=proposal.proposal_id, status="manual_review",
                recommendation=None, rationale=reason, policy_sources=[],
                factual_sources=[], missing_information=[reason],
                uncertainty_reason=reason,
                validation_errors=[reason],
            ).model_dump(mode="json")
            for proposal in agenda.proposals
        ],
        "errors": [reason],
    }


def _code_fingerprint() -> str:
    """Hash actual runtime source and lock data, independent of checkout path or docs commits."""
    package = Path(__file__).resolve().parent
    files = {f"voting_assistant/{path.relative_to(package).as_posix()}": path for path in package.rglob("*.py")}
    repository = package.parent.parent
    for name in ("pyproject.toml", "uv.lock"):
        if (repository / name).is_file():
            files[name] = repository / name
    return _sha(json.dumps({name: _sha(_bytes(path, "runtime source")) for name, path in sorted(files.items())}, sort_keys=True).encode())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_evaluation(
    manifest: Manifest,
    meetings: list[Meeting],
    manifest_sha256: str,
    output: Path,
    *,
    assessor: Assessor,
    max_cost_usd: Decimal,
    config: dict,
    resume: bool = False,
) -> dict:
    selected = [meeting for meeting in meetings if meeting.split == manifest.split]
    config = {
        **config,
        "checkpoint_version": 2,
        "code_sha256": _code_fingerprint(),
        "manifest_sha256": manifest_sha256,
        "dataset_kind": manifest.dataset_kind,
        "split": manifest.split,
    }
    budget = _money(max_cost_usd)
    if budget > 204:
        raise CliError("budget must be at most 204 USD")
    try:
        with _lock(output):
            report = _load_run(output, config, resume)
            runs = report["runs"]
            if _money(report["spent_usd"]) > budget:
                raise CliError("previous spend exceeds the requested budget")
            report["max_cost_usd"] = str(budget)
            report["split_counts"] = dict(Counter(meeting.split for meeting in meetings))
            for history in report["attempts"].values():
                for attempt in history:
                    if attempt["status"] == "running":
                        attempt["status"] = "interrupted"
                        attempt["interruption_detected_at"] = _now()

            def checkpoint() -> None:
                report["metrics"] = summarize(selected, runs)
                _save(output, report)

            checkpoint()
            for meeting in selected:
                agenda = meeting.agenda
                meeting_id = agenda.meeting_id
                if _complete(runs.get(meeting_id, {}), agenda):
                    continue
                spent_before = _money(report["spent_usd"])
                remaining = budget - spent_before
                if remaining <= 0:
                    if not runs.get(meeting_id, {}).get("assessments"):
                        runs[meeting_id] = _unassessed(agenda, "Kostnadsrammen er brukt opp.")
                        checkpoint()
                    continue

                previous_run = runs.get(meeting_id, {})
                history = report["attempts"].setdefault(meeting_id, [])
                attempt = {
                    "number": len(history) + 1,
                    "reason": "first_attempt" if not history else "resume_incomplete_attempt",
                    "previous_errors": previous_run.get("errors", []),
                    "status": "running", "started_at": _now(), "finished_at": None,
                    "cost_usd": "0", "run": None,
                }
                history.append(attempt)
                checkpoint()

                def account(cost: Decimal) -> None:
                    recorded = _money(cost)
                    attempt["cost_usd"] = str(recorded)
                    report["spent_usd"] = str(spent_before + recorded)
                    checkpoint()

                # History is persisted before the call, including conservative reservations.
                # Keep every previous result even when runs advances to the latest attempt.
                try:
                    result = assessor(agenda, remaining, account)
                    run = result.model_dump(mode="json")
                    account(_money(run["cost_usd"]))
                except OSError:
                    raise
                except Exception as error:
                    run = _unassessed(agenda, f"Vurderingen feilet ({type(error).__name__}).")
                if run.get("status") == "complete" and not _complete(run, agenda):
                    run["status"] = "partial"
                    run.setdefault("errors", []).append("assessment is incomplete or contains validation errors")
                attempt.update({"status": run["status"], "finished_at": _now(), "run": run})
                runs[meeting_id] = run
                checkpoint()
            return report
    except OSError:
        raise CliError("cannot read or write evaluation checkpoint") from None


def evaluate(args: argparse.Namespace) -> int:
    manifest, meetings, digest = load_manifest(args.manifest)
    output = args.output.resolve()
    inputs = {args.manifest.resolve(), args.index.resolve()}
    for entry in manifest.meetings:
        inputs.update(
            (args.manifest.parent / file_entry.path).resolve()
            for file_entry in (entry.agenda, entry.reference)
        )
    if output in inputs or output.with_name(output.name + ".lock") in inputs:
        raise CliError("output and lock must be separate from the input files")
    from .assessment import PROMPT_VERSION, ASSESSMENT_PROMPT, assess
    from .retrieval import PolicyIndex
    from anthropic import Anthropic

    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    model = os.getenv("ANTHROPIC_MODEL", "").strip()
    if not key or not model:
        raise CliError("set ANTHROPIC_API_KEY and ANTHROPIC_MODEL")
    prices = {
        "input_usd_per_mtok": _money(os.getenv("ANTHROPIC_INPUT_USD_PER_MTOK", "")),
        "output_usd_per_mtok": _money(os.getenv("ANTHROPIC_OUTPUT_USD_PER_MTOK", "")),
    }
    if any(price <= 0 for price in prices.values()):
        raise CliError("set positive Anthropic input and output prices")
    index_digest = _sha(_bytes(args.index, "policy index"))
    index = PolicyIndex.load(args.index)
    if _sha(_bytes(args.index, "policy index")) != index_digest:
        raise CliError("policy index changed while opening it")
    expected_corpus = "synthetic" if manifest.dataset_kind == "synthetic" else "nbim"
    if index.corpus_kind != expected_corpus:
        raise CliError("evaluation dataset and policy corpus kinds differ")

    if manifest.policy_documents:
        expected = set(manifest.policy_documents.items())
        available = set()
        for meeting in meetings:
            applicable = {
                (rule.policy_version, rule.source.sha256)
                for rule in index.valid_guidelines(meeting.agenda.meeting_date)
            }
            if not applicable or not applicable <= expected:
                raise CliError("policy documents differ from the frozen meeting manifest")
            available.update(applicable)
        if available != expected:
            raise CliError("frozen policy documents are missing from the index")

    with Anthropic(api_key=key, max_retries=0) as client:
        def assess_meeting(agenda: Agenda, remaining: Decimal, account: Callable[[Decimal], None]):
            return assess(
                agenda, index, client, model, max_cost_usd=remaining, on_cost=account, **prices
            )

        report = run_evaluation(
            manifest, meetings, digest, output,
            assessor=assess_meeting, max_cost_usd=args.max_cost_usd, resume=args.resume,
            config={
                "model": model,
                "prompt_version": PROMPT_VERSION,
                "prompt_sha256": _sha(ASSESSMENT_PROMPT.encode()),
                "index_sha256": index_digest,
                "index_version": index.index_version,
                "embedding_model": index.embedding_model,
                "corpus_kind": index.corpus_kind,
                "prices": {name: str(price) for name, price in prices.items()},
            },
        )
    print(f"Evaluation {report['metrics']['status']}; report saved to {output}")
    return 0 if report["metrics"]["status"] == "complete" else 1
