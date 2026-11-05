"""Choose the existing local board-disagreement model and threshold for F1.

This is a new, offline selection run over archived 2020–2023 forward predictions
and exposed 2024 calibration scores. It never opens the October test artifacts.
Old models, sources, predictions and reports remain unchanged.
"""
import boot  # noqa: F401
import argparse
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import joblib
import numpy as np
import pandas as pd

import board_experiment
import vote_learner
from rag_eval import immutable_json, fingerprint
from vector_experiment import ROOT, FIELDS, KEY, digest
from vote_targets import target_labels


OUTPUT = ROOT / "data/local-rag/f1-board-v1"
PREVIOUS = ROOT / "data/local-rag/board-disagreement-v1"
CLAUDE = ROOT / "data/local-rag/claude-board-v1"
TARGET = "against_board"
SOURCE_FILES = ("f1_experiment.py", "board_experiment.py", "vote_learner.py", "vote_features.py",
                "vote_targets.py", "vector_experiment.py", "vector_model.py", "rag_eval.py")
REQUIRED_PREVIOUS = {"validation.csv", "calibration.csv", "calibration-inputs.npz", "learner.joblib"}


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def checked_path(base, relative, expected):
    path = (Path(base) / relative).resolve()
    if not path.is_relative_to(Path(base).resolve()) or digest(path) != expected:
        raise ValueError("Artifact changed or unsafe artifact path")
    return path


def same_board_dependencies(archived, current):
    """Permit drift only inside the old run() function, which this code never calls.

    Imports, constants, helpers and every other top-level statement must match.
    The observed difference is the earlier UNKNOWN/error-column reporting fix.
    """
    def selected(path):
        module = ast.parse(Path(path).read_text(encoding="utf-8"))
        runners = [node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "run"]
        if len(runners) != 1:
            return None
        module.body = [node for node in module.body if node is not runners[0]]
        return ast.dump(module, include_attributes=False)

    old, new = selected(archived), selected(current)
    return old is not None and old == new


def best_f1(labels, scores):
    """Maximize positive-class F1 over all tied score groups, retaining missing rows.

    Equal F1 prefers precision, then a higher threshold. Thresholds are compared
    only within one model; their scales are not used to break model-selection ties.
    """
    raw = np.asarray(labels)
    values = np.asarray([np.nan if value is None else value for value in scores], dtype=float)
    if raw.ndim != 1 or values.shape != raw.shape or not np.isin(raw, [False, True]).all():
        raise ValueError("Selection requires aligned binary labels and scalar scores")
    y = raw.astype(bool)
    finite = np.isfinite(values)
    if not y.any() or not finite.any():
        raise ValueError("F1 selection requires a positive reference and finite scores")
    order = np.argsort(-values[finite], kind="stable")
    ranked, truth = values[finite][order], y[finite][order]
    ends = np.r_[np.flatnonzero(ranked[:-1] != ranked[1:]), len(ranked) - 1]
    tp = np.cumsum(truth)[ends]
    fp, fn = ends + 1 - tp, y.sum() - tp
    f1 = 2 * tp / (2 * tp + fp + fn)
    precision = tp / (tp + fp)
    index = max(range(len(ends)), key=lambda i: (f1[i], precision[i], ranked[ends[i]]))
    threshold = float(ranked[ends[index]])
    return {"threshold": threshold, "metrics": board_experiment.measure(y, values, threshold)}


def rank_candidates(validation, configurations):
    labels = target_labels(validation, TARGET)
    years = sorted(validation.meeting_date.str[:4].astype(int).unique())
    candidates = []
    for config in configurations:
        scores = np.asarray([float(value) if value != "" else np.nan for value in validation[config["name"]]], dtype=float)
        point = best_f1(labels, scores)
        per_year = []
        for year in years:
            mask = validation.meeting_date.str.startswith(str(year)).to_numpy()
            per_year.append({"year": int(year), **board_experiment.measure(labels[mask], scores[mask], point["threshold"])})
        candidates.append({"config": dict(config), "threshold": point["threshold"],
                           "validation": point["metrics"], "validation_per_year": per_year})
    # Python's stable sort retains the declared configuration order for final ties.
    candidates.sort(key=lambda candidate: (candidate["validation"]["f1"], candidate["validation"]["precision"]), reverse=True)
    return [{"rank": rank, **candidate} for rank, candidate in enumerate(candidates, 1)]


def validate_previous(previous=PREVIOUS):
    previous = Path(previous)
    summary = read_json(previous / "summary.json")
    if summary.get("target") != TARGET or not REQUIRED_PREVIOUS <= set(summary.get("artifacts", {})):
        raise ValueError("Previous experiment lacks the required target or frozen artifacts")
    for name, expected in summary["artifacts"].items():
        checked_path(previous, name, expected)
    for name, expected in summary["source_hashes"].items():
        archived = checked_path(previous, "source/" + name, expected)
        if digest(ROOT / name) != expected:
            if name != "board_experiment.py" or not same_board_dependencies(archived, ROOT / name):
                raise ValueError("Previous prediction code changed; do not reuse mismatched cached predictions")
    return summary


def read_predictions(path):
    # Parse decimal score strings with Python/NumPy only when used. This preserves
    # the archived float values without a CSV parser's lower-precision fast path.
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def check_cohorts(validation, calibration, fit, expected_calibration):
    expected_validation = fit.loc[fit.meeting_date.ge("2020-01-01")].reset_index(drop=True)
    for actual, expected in ((validation, expected_validation), (calibration, expected_calibration)):
        if actual[FIELDS].to_dict("records") != expected[FIELDS].to_dict("records"):
            raise ValueError("Archived prediction cohort differs from the declared temporal cohort")
        labels = target_labels(actual, TARGET)
        if actual.actual_disagreement.astype(str).str.lower().tolist() != [str(bool(value)).lower() for value in labels]:
            raise ValueError("Cached disagreement labels differ from the actual vote/board target")
    if not validation.meeting_date.between("2020-01-01", "2023-12-31").all():
        raise ValueError("Model selection crossed its declared years")
    if not calibration.meeting_date.between("2024-01-01", "2024-12-31").all():
        raise ValueError("Threshold calibration crossed its declared year")
    if set(validation.meeting_id) & set(calibration.meeting_id):
        raise ValueError("Meeting overlap between model selection and calibration")


def reuse_learner(previous, previous_summary, selected_config, output):
    """Never relabel a model's weights as another selected configuration."""
    if previous_summary["selected_config"] != selected_config:
        raise ValueError("F1 selected another model; fit that configuration before calibration instead of reusing these weights")
    source = checked_path(previous, "learner.joblib", previous_summary["artifacts"]["learner.joblib"])
    state = joblib.load(source)
    if state.get("target") != TARGET or state.get("config") != selected_config:
        raise ValueError("Saved learner target/configuration differs from the selected model")
    destination = Path(output) / "learner.joblib"
    with destination.open("xb") as handle:
        handle.write(source.read_bytes())
    return digest(destination)


def cached_claude(calibration, base=CLAUDE):
    """Compare saved hard votes without claiming to tune Claude's weights or prompt."""
    base = Path(base)
    plan = read_json(base / "plan.json")
    report = read_json(base / "report.json")
    if (plan.get("target") != TARGET or report.get("target") != TARGET
            or report.get("evaluation_kind") != "EXPOSED_2024_DEVELOPMENT" or report.get("complete") is not True):
        raise ValueError("Claude reference must be the completed, matched 2024 development comparison")
    checked_path(base, "evaluation-labels.csv", plan["evaluation_labels_sha256"])
    gold = read_predictions(base / "evaluation-labels.csv")
    if gold[FIELDS].to_dict("records") != calibration[FIELDS].to_dict("records"):
        raise ValueError("Claude and local model use different comparison rows")
    rows = read_json(base / "predictions.json")
    predicted = {}
    for row in rows:
        key = str(row["meeting_id"]), str(row["item_no"])
        if key in predicted:
            raise ValueError("Duplicate Claude prediction identity")
        predicted[key] = row
    keys = set(map(tuple, calibration[KEY].values))
    if set(predicted) != keys:
        raise ValueError("Claude predictions do not cover the full matched cohort including failures")
    scores = []
    for row in calibration.itertuples():
        vote = predicted[row.meeting_id, row.item_no].get("claude_vote")
        scores.append(float(vote != row.mgmt_rec) if vote in ("FOR", "MOT", "AVSTÅ") else None)
    measured = board_experiment.measure(target_labels(calibration, TARGET), scores, .5)
    if measured != report["claude"]["disagreement"]:
        raise ValueError("Claude individual predictions disagree with its aggregate report")
    return {"metrics": measured, "model": report["model"], "failed_meetings": report["failed_meetings"],
            "complete": True, "api_calls": 0, "new_model_optimization": False,
            "note": "Unchanged cached hard votes; no scalar decision threshold, prompt tuning or new API calls.",
            "artifacts": {name: digest(base / name) for name in ("plan.json", "report.json", "predictions.json", "evaluation-labels.csv")}}


def run(output=OUTPUT, previous=PREVIOUS, claude=CLAUDE):
    output, previous = Path(output), Path(previous)
    if output.exists():
        raise ValueError("Output exists; preserve previous experiments and choose another --output")
    old = validate_previous(previous)
    fit, expected_calibration, provenance = board_experiment.load_temporal()
    validation = read_predictions(previous / "validation.csv")
    calibration = read_predictions(previous / "calibration.csv")
    check_cohorts(validation, calibration, fit, expected_calibration)
    source_hashes = {name: digest(ROOT / name) for name in SOURCE_FILES}
    output.mkdir(parents=True)
    plan = {"created_at": now(), "objective": "maximize_f1", "target": TARGET,
            "model_selection": "Maximum positive-class F1 on pooled 2020–2023 forward predictions; ties precision then declared configuration order.",
            "threshold_selection": "Maximum positive-class F1; ties precision then higher threshold. Final threshold uses exposed 2024 calibration only.",
            "configurations": vote_learner.CONFIGS, "selection_period": "2020–2023", "calibration_period": "2024",
            "source_hashes": source_hashes, "previous_summary_sha256": digest(previous / "summary.json"),
            "compatible_reporting_source_drift": [{"name": name, "archived_sha256": expected, "current_sha256": digest(ROOT / name),
                    "verified_scope": "Entire module syntax tree excluding unused run(); includes all imports, constants and helpers.",
                    "used_functions": ["measure", "load_temporal", "sizes"],
                    "observed_difference": "Existing nonfinite-score UNKNOWN and error-column reporting fix inside run()."}
                    for name, expected in old["source_hashes"].items() if digest(ROOT / name) != expected],
            "source_compatibility_rule": "Feature/learner sources must match exactly. Board module syntax tree may differ only inside run(), which this experiment never invokes.",
            "previous_artifacts": {name: old["artifacts"][name] for name in REQUIRED_PREVIOUS},
            "test_evaluated": False, "october_test_unchanged": True, "october_inputs_used": False,
            "objective_change_context": "User requested F1 after seeing the October test; the new selection uses only archived 2020–2024 development data.",
            "api_calls": 0, **provenance}
    immutable_json(output / "plan.json", plan)
    candidates = rank_candidates(validation, vote_learner.CONFIGS)
    selected = candidates[0]
    immutable_json(output / "selection.json", {"objective": "maximize_f1", "selected": selected,
                   "candidates": candidates, "calibration_used_to_choose_model": False})
    learner_hash = reuse_learner(previous, old, selected["config"], output)
    labels, scores = target_labels(calibration, TARGET), calibration.score.to_numpy(dtype=float)
    point = best_f1(labels, scores)
    comparators = {"previous_balanced": {"threshold": old["selected_threshold"],
                    "metrics": board_experiment.measure(labels, scores, old["selected_threshold"])},
                  "cached_claude": cached_claude(calibration, claude),
                  "follow_board": {"metrics": board_experiment.measure(labels, np.zeros(len(labels)), .5)}}
    if comparators["previous_balanced"]["metrics"] != old["calibration_selected"]:
        raise ValueError("Previous calibrated metrics cannot be reproduced")
    replay = calibration[FIELDS + ["actual_disagreement", "score"]].copy()
    replay["threshold"] = point["threshold"]
    predicted = np.isfinite(scores) & (scores >= point["threshold"])
    replay["prediction"] = np.where(~np.isfinite(scores), "UNKNOWN", np.where(predicted, "DISAGREE", "WITH_BOARD"))
    replay["error"] = np.select([predicted & ~labels, ~predicted & labels], ["FP", "FN"], "")
    replay.to_csv(output / "calibration.csv", index=False)
    for name in ("validation.csv", "calibration-inputs.npz", "feature_names.json"):
        shutil.copy2(previous / name, output / name)
    source_dir = output / "source"
    source_dir.mkdir()
    for name in SOURCE_FILES:
        shutil.copy2(ROOT / name, source_dir / name)
    immutable_json(output / "calibration.json", {"period": "2024", "objective": "maximize_f1", **point,
                   "note": "Same exposed labels choose the threshold and measure this row; not an independent test."})
    summary = {"experiment": "LOCAL_CHRONOLOGICAL_F1", "created_at": now(), "objective": "maximize_f1",
               "target": TARGET, "positive_class": "NBIM != mgmt_rec", "evaluation_kind": "EXPOSED_2024_CALIBRATION",
               "fit_period": "2019–2023", "selection_period": "2020–2023", "calibration_period": "2024",
               "test_evaluated": False, "october_test_unchanged": True, "october_inputs_used": False,
               "api_calls": 0, "model_reused": True, "learner_sha256": learner_hash,
               "fit": board_experiment.sizes(fit), "calibration": board_experiment.sizes(calibration),
               "selected_config": selected["config"], "selected_threshold": point["threshold"],
               "validation_threshold": selected["threshold"], "model_selection_validation": selected["validation"],
               "calibration_selected": point["metrics"],
               "calibration_at_validation_threshold": board_experiment.measure(labels, scores, selected["threshold"]),
               "validation_per_year": selected["validation_per_year"], "candidates": candidates,
               "comparators": comparators, "source_hashes": source_hashes, "history_policy": old["history_policy"],
               "rules_used": False, "previous_summary_sha256": digest(previous / "summary.json"),
               "provenance": provenance,
               "caveats": ["2020–2023 F1 was maximized over configurations and thresholds; those selection scores are optimistic.",
                           "2024 threshold calibration is development, not an independent final test.",
                           "No October outcomes or predictions enter model or threshold selection; its original report remains unchanged.",
                           "The objective change was requested after seeing October results; this is a new development decision, not a protocol predeclared before that test.",
                           "Earlier literal-MOT models used another target and/or cohort and are not ranked as board-disagreement models.",
                           "Claude hard votes are unchanged; this run does not optimize Claude's weights or prompt.",
                           "The selected model remains the same, so existing fitted weights are copied byte-for-byte.",
                           "Higher development F1 does not establish better performance on new meetings."],
               "artifacts": {str(path.relative_to(output)): digest(path) for path in output.rglob("*") if path.is_file()}}
    summary["record_id"] = fingerprint(summary)
    immutable_json(output / "summary.json", summary)
    return summary


def predict(output, meeting, item):
    """Replay saved 2024 features using the active F1 threshold, never the old one."""
    output = Path(output)
    summary = read_json(output / "summary.json")
    if fingerprint({key: value for key, value in summary.items() if key != "record_id"}) != summary.get("record_id"):
        raise ValueError("F1 summary changed after selection")
    if summary.get("target") != TARGET or summary.get("objective") != "maximize_f1":
        raise ValueError("Expected an F1 board-disagreement experiment")
    for name, expected in summary["artifacts"].items():
        checked_path(output, name, expected)
    for name, expected in summary["source_hashes"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("Prediction code changed after the F1 selection")
    frame = read_predictions(output / "calibration.csv")
    selected = np.flatnonzero(frame.meeting_id.eq(str(meeting)) & frame.item_no.eq(str(item)))
    if len(selected) != 1:
        raise ValueError("Select one saved 2024 proposal")
    state = joblib.load(output / "learner.joblib")
    if state.get("target") != TARGET or state.get("config") != summary["selected_config"]:
        raise ValueError("Saved learner differs from the selected model")
    with np.load(output / "calibration-inputs.npz", allow_pickle=False) as features:
        history, vectors = features["history"][selected], features["vectors"][selected]
    query = frame.iloc[selected][[name for name in FIELDS if name != "nbim_vote"]]
    score = float(vote_learner.predict(state, query, history, vectors)[0])
    threshold = summary["selected_threshold"]
    return {"meeting_id": str(meeting), "item_no": str(item), "objective": "maximize_f1", "target": TARGET,
            "score": score, "threshold": threshold, "prediction": "DISAGREE" if score >= threshold else "WITH_BOARD",
            "vote_recommendation": None, "api_calls": 0, "note": "Saved 2024 replay; not a new independent test."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "predict"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--meeting")
    parser.add_argument("--item")
    args = parser.parse_args()
    if args.command == "run":
        summary = run(args.output)
        result = {key: summary[key] for key in ("objective", "selected_config", "selected_threshold", "validation_threshold",
                   "model_selection_validation", "calibration_selected", "calibration_at_validation_threshold", "test_evaluated")}
    else:
        if args.meeting is None or args.item is None:
            parser.error("predict requires --meeting and --item")
        result = predict(args.output, args.meeting, args.item)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
