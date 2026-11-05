"""Chronological, local NBIM-versus-board classifier with walk-forward history.

Fit/model selection: 2019–2023. Operating threshold: exposed 2024 calibration.
The already evaluated 2025–2026 period is never scored or used for tuning here.
Earlier same-period votes may enter historical features after the five-day lag;
model coefficients stay fixed throughout each validation/calibration period.
"""
import boot  # noqa: F401
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

import vote_features
import vote_learner
from vote_targets import known_target, target_labels
from vector_model import VectorVoteModel
from vector_experiment import ROOT, FIELDS, KEY, digest, write_json, embedding_matrix, forward_folds, metrics
from vote_experiment import threshold_options

SOURCE = ROOT / "data/real_votes.csv"
OUTPUT = ROOT / "data/local-rag/board-disagreement-v1"
TARGET = "against_board"
GOAL = .85


def load_temporal(source=SOURCE):
    """Read outcomes only for dates <2025; later rows supply identity counts only."""
    source = Path(source)
    source_hash = digest(source)
    if source.resolve() == SOURCE.resolve():
        expected = json.loads((ROOT / "results/freeze.json").read_text())["hashes"]["data/real_votes.csv"]
        if source_hash != expected:
            raise ValueError("Original voting source changed")
    rows, identities, meetings = [], set(), {}
    inventory = {name: {"rows": 0, "meetings": set()} for name in ("fit", "calibration", "old_test")}
    with source.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            day = row["meeting_date"]
            if pd.Timestamp(day).strftime("%Y-%m-%d") != day:
                raise ValueError("Meeting date must use YYYY-MM-DD")
            if not "2019-01-01" <= day <= "2026-12-31":
                raise ValueError("Unexpected source period")
            identity = tuple(row[key] for key in KEY)
            group = (row["company_id"], day)
            if not all(identity + group) or identity in identities:
                raise ValueError("Missing or duplicate proposal identity")
            identities.add(identity)
            if row["meeting_id"] in meetings and meetings[row["meeting_id"]] != group:
                raise ValueError("Meeting identity spans company/date groups")
            meetings[row["meeting_id"]] = group
            part = "fit" if day < "2024-01-01" else "calibration" if day < "2025-01-01" else "old_test"
            inventory[part]["rows"] += 1
            inventory[part]["meetings"].add(row["meeting_id"])
            if part == "old_test":
                continue  # Never inspect later vote labels, categories or rationales.
            if row.get("injection_flag", "0") != "0":
                raise ValueError("Injection fixtures must not enter ordinary model data")
            rows.append({field: row[field] for field in FIELDS})
    frame = pd.DataFrame(rows, columns=FIELDS)
    if frame.empty:
        raise ValueError("No development data")
    allowed = ["", "FOR", "MOT", "AVSTÅ"]
    if not frame.nbim_vote.isin(allowed).all() or not frame.mgmt_rec.isin(allowed).all():
        raise ValueError("Unexpected vote label before 2025")
    excluded = {}
    for part, mask in (("fit", frame.meeting_date.lt("2024-01-01")),
                       ("calibration", frame.meeting_date.ge("2024-01-01"))):
        subset = frame.loc[mask]
        excluded[part] = {"unknown_nbim": int(subset.nbim_vote.eq("").sum()),
                          "known_nbim_unknown_board": int((subset.nbim_vote.ne("") & subset.mgmt_rec.eq("")).sum())}
    frame = frame.loc[known_target(frame, TARGET)].sort_values(["meeting_date", *KEY], kind="stable").reset_index(drop=True)
    fit = frame.loc[frame.meeting_date.lt("2024-01-01")].reset_index(drop=True)
    calibration = frame.loc[frame.meeting_date.ge("2024-01-01")].reset_index(drop=True)
    if fit.empty or calibration.empty:
        raise ValueError("Need both training and calibration periods")
    if set(fit.meeting_id) & set(calibration.meeting_id):
        raise ValueError("Training and calibration meetings overlap")
    return fit, calibration, {"source_sha256": source_hash, "protocol": "WHOLE_SOURCE_CHRONOLOGICAL",
                              "mixed_80_20_used": False, "supersedes_mixed_split_for_this_experiment": True,
                              "source_inventory": {k: {"rows": v["rows"], "meetings": len(v["meetings"])} for k, v in inventory.items()},
                              "excluded_unknown_labels": excluded, "test_labels_read": False,
                              "prior_exposure": "Data have been used in earlier experiments; 2024 is threshold-calibration data, not an independent test."}


def measure(labels, scores, threshold):
    result = metrics(labels, scores, threshold)
    result["positive"] = result.pop("mot")
    result["predicted_positive"] = result.pop("predicted_mot")
    result["predicted_positive_share"] = result.pop("predicted_mot_share")
    return result


def options(labels, scores):
    return {name: {"threshold": point["threshold"],
                   "metrics": measure(labels, scores, point["threshold"]) if point["threshold"] is not None else None}
            for name, point in threshold_options(labels, scores, GOAL).items()}


def quality(candidate):
    result = candidate["operating_points"]["balanced"]["metrics"]
    return min(result["precision"], result["recall"]), result["f1"], result["precision"]


def sizes(frame):
    return {"rows": len(frame), "positive": int(target_labels(frame, TARGET).sum()),
            "literal_mot": int(frame.nbim_vote.eq("MOT").sum()), "meetings": int(frame.meeting_id.nunique()),
            "companies": int(frame.company_id.nunique())}


def historical_reference(calibration):
    path = ROOT / "results/items_val.csv"
    if not path.exists():
        return None
    old = pd.read_csv(path, usecols=["meeting_id", "item", "draft"], dtype=str, keep_default_na=False).rename(columns={"item": "item_no"})
    frame = calibration.merge(old, on=KEY, how="left", validate="one_to_one")
    known = frame.draft.isin(["FOR", "MOT", "AVSTÅ"])
    scores = np.where(known, frame.draft.ne(frame.mgmt_rec).astype(float), np.nan)
    mot_scores = np.where(known, frame.draft.eq("MOT").astype(float), np.nan)
    return {"against_board": measure(target_labels(frame, TARGET), scores, .5),
            "mot": metrics(frame.nbim_vote.eq("MOT"), mot_scores, .5), "artifact_sha256": digest(path),
            "note": "Previously generated full voting drafts, different prompt and development process. Historical descriptive reference, not a controlled retraining."}


def run(output=OUTPUT, source=SOURCE):
    started = time.monotonic()
    output = Path(output)
    if output.exists():
        raise ValueError("Output exists; preserve previous experiments and choose a new --output")
    fit, calibration, provenance = load_temporal(source)
    output.mkdir(parents=True)
    files = ("board_experiment.py", "vote_targets.py", "vote_features.py", "vote_learner.py", "vote_experiment.py",
             "vector_experiment.py", "vector_model.py")
    sources = {name: digest(ROOT / name) for name in files}
    (output / "source").mkdir()
    for name in files:
        shutil.copy2(ROOT / name, output / "source" / name)
    write_json(output / "plan.json", {**provenance, "target": TARGET, "positive_class": "NBIM != mgmt_rec",
                                     "target_precision": GOAL, "target_recall": GOAL,
                                     "model_selection": "max min(precision,recall) on 2020–2023 forward validation; ties F1 then precision",
                                     "threshold_selection": "same criterion on exposed 2024 calibration only, after model selection",
                                     "history_policy": "walk_forward_5d", "history_date_rule": "reference meeting date < query meeting date - 5 days; exclude own meeting",
                                     "configurations": vote_learner.CONFIGS, "source_hashes": sources,
                                     "test_evaluated": False})
    all_rows = pd.concat([fit, calibration], ignore_index=True)
    vectors, embedding = embedding_matrix(all_rows)
    X, C = vectors[:len(fit)], vectors[len(fit):]
    print(f"Target: NBIM != board. Fit {len(fit)}; 2024 calibration {len(calibration)}; no later test labels", flush=True)
    # This computation has the same information regime for fit and validation:
    # only strictly earlier meetings contribute, including earlier same-year meetings.
    H, feature_names = vote_features.features(fit.drop(columns="nbim_vote"), X, fit, X, target=TARGET)
    y = target_labels(fit, TARGET)
    folds = forward_folds(fit)
    checks = np.concatenate([check for _, _, check in folds])
    scores_by_model = {config["name"]: np.full(len(fit), np.nan) for config in vote_learner.CONFIGS}
    for year, train, check in folds:
        print(f"Forward year {year}: train {len(train)}, validate {len(check)}; historical context updates within year", flush=True)
        for config in vote_learner.CONFIGS:
            model = vote_learner.fit(config, fit.iloc[train], H[train], X[train], target=TARGET)
            scores_by_model[config["name"]][check] = vote_learner.predict(model, fit.iloc[check].drop(columns="nbim_vote"), H[check], X[check])
    candidates = [{"config": config, "operating_points": options(y[checks], scores_by_model[config["name"]][checks])}
                  for config in vote_learner.CONFIGS]
    selected = max(candidates, key=quality)
    config = selected["config"]
    validation_threshold = selected["operating_points"]["balanced"]["threshold"]
    write_json(output / "selection.json", {"selected": selected, "configurations": candidates,
                                          "selection_period": "2020–2023", "calibration_used_to_choose_model": False})
    validation = fit.iloc[checks][FIELDS].copy()
    validation["actual_disagreement"] = y[checks]
    for name, scores in scores_by_model.items():
        validation[name] = scores[checks]
    validation.to_csv(output / "validation.csv", index=False)
    print(f"Locked model {config['name']}; now scoring/calibrating 2024", flush=True)
    model = vote_learner.fit(config, fit, H, X, target=TARGET)
    joblib.dump(model, output / "learner.joblib", compress=3)
    Q, actual_names = vote_features.features(calibration.drop(columns="nbim_vote"), C, all_rows, vectors, target=TARGET)
    if actual_names != feature_names:
        raise ValueError("Feature schema changed")
    scores = vote_learner.predict(model, calibration.drop(columns="nbim_vote"), Q, C)
    labels = target_labels(calibration, TARGET)
    calibration_options = options(labels, scores)
    threshold = calibration_options["balanced"]["threshold"]
    frame = calibration[FIELDS].copy()
    frame["actual_disagreement"] = labels
    frame["score"], frame["threshold"] = scores, threshold
    predicted = np.isfinite(scores) & (scores >= threshold)
    frame["prediction"] = np.where(~np.isfinite(scores), "UNKNOWN", np.where(predicted, "DISAGREE", "WITH_BOARD"))
    frame["error"] = np.select([predicted & ~labels, ~predicted & labels], ["FP", "FN"], "")
    frame.to_csv(output / "calibration.csv", index=False)
    write_json(output / "calibration.json", {"period": "2024", "selected_threshold": threshold, "operating_points": calibration_options,
                                            "note": "These labels choose the operating threshold; these are calibration results, not unbiased test scores."})
    np.savez_compressed(output / "calibration-inputs.npz", history=Q, vectors=C)
    VectorVoteModel().fit(fit, X).save(output / "reference")
    # Only this frozen training reference is saved for general inference. The CLI
    # below replays saved features; new live calls need an explicit as-of history.
    write_json(output / "feature_names.json", {"names": feature_names, "target": TARGET})
    hist = historical_reference(calibration)
    summary = {"experiment": "LOCAL_CHRONOLOGICAL_BOARD_DISAGREEMENT", "created_at": datetime.now(timezone.utc).isoformat(),
               **provenance, "target": TARGET, "positive_class": "NBIM != mgmt_rec", "api_calls": 0,
               "fit_period": "2019–2023", "calibration_period": "2024", "test_period": "2025–2026", "test_evaluated": False,
               "fit": sizes(fit), "calibration": sizes(calibration), "history_policy": "walk_forward_5d", "rules_used": False,
               "target_precision": GOAL, "target_recall": GOAL, "selected_config": config, "selected_threshold": threshold,
               "validation_threshold": validation_threshold,
               "model_selection_validation": selected["operating_points"]["balanced"]["metrics"],
               "validation_per_year": [{"year": year, **measure(y[check], scores_by_model[config["name"]][check], validation_threshold)}
                                       for year, _, check in folds],
               "calibration_selected": calibration_options["balanced"]["metrics"],
               "calibration_at_validation_threshold": measure(labels, scores, validation_threshold),
               "calibration_no_disagreement": measure(labels, np.zeros(len(labels)), .5),
               "historical_vote_reference": hist, "operating_points": calibration_options,
               "literal_mot_new_model": {"status": "not_defined", "reason": "A binary disagreement score is not a FOR/MOT/AVSTÅ recommendation. No opposite-board heuristic is counted as a model vote."},
               "feature_count": len(feature_names), "embedding": embedding, "source_hashes": sources,
               "elapsed_seconds": time.monotonic() - started,
               "caveats": ["The former mixed 80/20 partition is superseded for this experiment; its artifacts remain unchanged.",
                           "2024 is previously exposed threshold calibration, not a new independent final test.",
                           "Earlier same-year outcomes enter history only after the strict five-day cutoff; model coefficients stay fixed.",
                           "No 2025–2026 target labels are read or scored.",
                           "Disagreement flags do not specify a vote direction or establish guideline compliance.",
                           "Historical meeting dates approximate information availability; exact publication times are not present.",
                           "The pretrained embedding model has no verified historical training cutoff."],
               "artifacts": {str(path.relative_to(output)): digest(path) for path in output.rglob("*") if path.is_file()}}
    write_json(output / "summary.json", summary)
    print(json.dumps({"selected_config": config, "validation": summary["model_selection_validation"],
                      "calibration_before_retuning": summary["calibration_at_validation_threshold"],
                      "calibration_selected": summary["calibration_selected"], "test_evaluated": False}, indent=2), flush=True)
    return summary


def predict(output, meeting, item):
    """Replay a saved 2024 feature vector; no training or current-item target access."""
    output = Path(output)
    summary = json.loads((output / "summary.json").read_text())
    for relative, expected in summary["artifacts"].items():
        path = (output / relative).resolve()
        if not path.is_relative_to(output.resolve()) or digest(path) != expected:
            raise ValueError("Saved experiment artifact changed or unsafe path")
    frame = pd.read_csv(output / "calibration.csv", dtype=str, keep_default_na=False)
    selected = np.flatnonzero(frame.meeting_id.eq(str(meeting)) & frame.item_no.eq(str(item)))
    if len(selected) != 1:
        raise ValueError("Select one saved calibration proposal")
    with np.load(output / "calibration-inputs.npz", allow_pickle=False) as data:
        history, vectors = data["history"][selected], data["vectors"][selected]
    state = joblib.load(output / "learner.joblib")
    if state.get("target") != TARGET:
        raise ValueError("Saved learner is not a board-disagreement model")
    query = frame.iloc[selected].drop(columns=["nbim_vote", "actual_disagreement", "score", "threshold", "prediction", "error"])
    score = float(vote_learner.predict(state, query, history, vectors)[0])
    return {"meeting_id": str(meeting), "item_no": str(item), "target": TARGET, "score": score,
            "threshold": summary["selected_threshold"], "prediction": "DISAGREE" if score >= summary["selected_threshold"] else "WITH_BOARD",
            "vote_recommendation": None, "api_calls": 0, "note": "Uncalibrated exception score; not a vote direction or verified rule violation."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "predict"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--meeting")
    parser.add_argument("--item")
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        if args.command == "run":
            run(args.output)
        else:
            if args.meeting is None or args.item is None:
                parser.error("predict requires --meeting and --item")
            print(json.dumps(predict(args.output, args.meeting, args.item), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
