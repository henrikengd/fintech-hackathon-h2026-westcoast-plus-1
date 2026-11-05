"""A predeclared chronological ablation of hybrid, diverse voting history.

Model selection uses only 2020–2023 forward predictions. Each learner is fit on
earlier years; references may update only after the five-day information lag.
2024 remains exposed calibration, and no later-period outcomes are opened.
"""
import boot  # noqa: F401
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import shutil
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

import board_experiment
import f1_experiment
import relevance_retrieval
import vote_features
import vote_learner
from rag_eval import fingerprint, immutable_json
from vector_experiment import ROOT, FIELDS, KEY, digest, embedding_matrix, forward_folds
from vote_targets import target_labels


OUTPUT = ROOT / "data/local-rag/relevance-board-v1"
PREVIOUS = ROOT / "data/local-rag/board-disagreement-v1"
TARGET = "against_board"
BASELINE = {"name": "semantic-history-boost", "kind": "baseline", "semantic": True}
CONFIGS = [BASELINE,
           {"name": "hybrid-history-boost", "kind": "boost", "semantic": False},
           {"name": "hybrid-semantic-boost", "kind": "boost", "semantic": True},
           {"name": "hybrid-semantic-logistic", "kind": "logistic", "semantic": True}]
RETRIEVAL = {"dense_weight": .65, "max_per_text": 2, "k_global": 8, "k_company": 8}
SOURCE_FILES = ("relevance_experiment.py", "relevance_retrieval.py", "board_experiment.py",
                "f1_experiment.py", "vote_learner.py", "vote_features.py", "vote_targets.py",
                "vector_model.py", "vector_experiment.py", "rag_eval.py")


def now():
    return datetime.now(timezone.utc).isoformat()


def numeric_inputs(history, retrieval, embeddings, semantic):
    """Fixed transformations only; learned preprocessing happens inside each fit."""
    history = vote_learner.bounded_history(history)
    retrieval = np.asarray(retrieval, dtype=float)
    embeddings = np.asarray(embeddings, dtype=float)
    if (retrieval.ndim != 2 or len(retrieval) != len(history)
            or embeddings.shape != (len(history), 384)
            or np.isinf(retrieval).any() or not np.isfinite(embeddings).all()):
        raise ValueError("Misaligned or invalid retrieval/embedding features")
    values = [history, retrieval]
    if semantic:
        values.append(embeddings)
    return np.column_stack(values)


def fit(config, frame, history, retrieval, embeddings, names):
    if config not in CONFIGS[1:]:
        raise ValueError("Expected a predeclared enhanced learner")
    labels = target_labels(frame, TARGET)
    if len(np.unique(labels)) != 2 or retrieval.shape[1] != len(names):
        raise ValueError("Training requires both classes and a fixed feature schema")
    values = numeric_inputs(history, retrieval, embeddings, config["semantic"])
    transform = make_pipeline(SimpleImputer(strategy="constant", fill_value=0, add_indicator=True,
                                            keep_empty_features=True), StandardScaler())
    values = transform.fit_transform(values)
    if config["kind"] == "boost":
        learner = HistGradientBoostingClassifier(max_iter=180, learning_rate=.05, max_leaf_nodes=15,
                                                 min_samples_leaf=20, l2_regularization=1.0,
                                                 class_weight=None, early_stopping=False, random_state=41)
    else:
        learner = LogisticRegression(C=1., class_weight="balanced", solver="liblinear",
                                     max_iter=1500, random_state=41)
    return {"target": TARGET, "config": dict(config), "transform": transform,
            "feature_names": list(names), "learner": learner.fit(values, labels),
            "latest_fit_date": frame.meeting_date.max(), "fit_rows": len(frame)}


def predict_scores(state, history, retrieval, embeddings, names):
    if state.get("target") != TARGET or state.get("feature_names") != list(names):
        raise ValueError("Wrong target or retrieval feature schema")
    values = numeric_inputs(history, retrieval, embeddings, state["config"]["semantic"])
    return state["learner"].predict_proba(state["transform"].transform(values))[:, 1]


def selection_rows(frame, scores_by_model):
    """Only pre-2024 rows may choose a model, regardless of the caller."""
    if (frame.empty or not frame.meeting_date.between("2020-01-01", "2023-12-31").all()
            or set(scores_by_model) != {config["name"] for config in CONFIGS}):
        raise ValueError("Model selection requires the declared 2020–2023 candidate cohort")
    labels = target_labels(frame, TARGET)
    candidates = []
    for config in CONFIGS:
        values = scores_by_model[config["name"]]
        point = f1_experiment.best_f1(labels, values)
        yearly = []
        for year in (2020, 2021, 2022, 2023):
            mask = frame.meeting_date.str.startswith(str(year)).to_numpy()
            if mask.any():
                yearly.append({"year": year, **board_experiment.measure(labels[mask], np.asarray(values)[mask], point["threshold"])})
        candidates.append({"config": config, "threshold": point["threshold"],
                           "validation": point["metrics"], "validation_per_year": yearly})
    candidates.sort(key=lambda item: (item["validation"]["f1"], item["validation"]["precision"]), reverse=True)
    return candidates


def retrieve(frame, vectors, reference, reference_vectors):
    retriever = relevance_retrieval.HybridHistoryRetriever(
        dense_weight=RETRIEVAL["dense_weight"], max_per_text=RETRIEVAL["max_per_text"]).fit(reference, reference_vectors)
    result = retriever.retrieve(frame.drop(columns="nbim_vote", errors="ignore"), vectors,
                                k_global=RETRIEVAL["k_global"], k_company=RETRIEVAL["k_company"])
    values, names = relevance_retrieval.features_from_results(result)
    return values, names, result


def audit_retrieval(frame, results):
    if len(results) != len(frame):
        raise ValueError("Retrieval audit does not align with query cohort")
    count = empty = 0
    unique = set()
    for query, result in zip(frame.to_dict("records"), results):
        if any(str(result[key]) != str(query[key]) for key in KEY):
            raise ValueError("Retrieval identities changed")
        cutoff = np.datetime64(query["meeting_date"], "D") - np.timedelta64(5, "D")
        seen = set()
        for match in result["matches"]:
            identity = match["meeting_id"], match["item_no"]
            day = np.datetime64(match["meeting_date"], "D")
            if (day >= cutoff or match["meeting_id"] == query["meeting_id"] or identity in seen
                    or (match["company_id"] == query["company_id"] and match["meeting_date"] == query["meeting_date"])):
                raise ValueError("Historical context crosses cutoff, own meeting or duplicate identity")
            seen.add(identity)
            unique.add(identity)
            count += 1
        empty += not bool(seen)
    return {"queries": len(results), "selected_matches": count, "distinct_historical_items": len(unique),
            "empty_queries": empty, "temporal_violations": 0, "same_meeting_violations": 0,
            "history_date_policy": "historical meeting_date < current meeting_date - 5 days"}


def save_retrieval(path, results):
    # Deterministic gzip timestamp; keep original text and dates available for audit.
    with Path(path).open("xb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle:
        for result in results:
            handle.write((json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True) + "\n").encode())


def check_baseline(frame, cached):
    if cached[FIELDS].to_dict("records") != frame[FIELDS].to_dict("records"):
        raise ValueError("Baseline and enhanced models must use exactly the same cohort")


def run(output=OUTPUT, previous=PREVIOUS):
    start = time.monotonic()
    output, previous = Path(output), Path(previous)
    if output.exists():
        raise ValueError("Output exists; preserve the run and choose a new --output")
    old = f1_experiment.validate_previous(previous)
    fit_rows, calibration, provenance = board_experiment.load_temporal()
    archived_validation = f1_experiment.read_predictions(previous / "validation.csv")
    folds = forward_folds(fit_rows)
    checks = np.concatenate([check for _, _, check in folds])
    check_baseline(fit_rows.iloc[checks], archived_validation)
    sources = {name: digest(ROOT / name) for name in SOURCE_FILES}
    output.mkdir(parents=True)
    plan = {"created_at": now(), "objective": "maximize_f1", "target": TARGET,
            "configurations": CONFIGS, "retrieval": RETRIEVAL, "source_hashes": sources,
            "selection_period": "2020–2023", "calibration_period": "2024",
            "model_selection": "Maximum positive-class F1, then precision, then declared candidate order; pooled forward predictions only.",
            "threshold_selection": "F1 maximization, ties precision then higher threshold; final calibration on exposed 2024.",
            "calibration_ablation": "Score all four predeclared candidates after model selection is locked; none may replace the selected model using 2024 results.",
            "history_policy": "walk_forward_5d", "label_blind_ranking": True,
            "old_history_preserved": True, "historical_label_availability": "Meeting date plus five-day lag is a proxy, not verified publication timestamps.",
            "baseline_summary_sha256": digest(previous / "summary.json"),
            "baseline_artifacts": old["artifacts"], "api_calls": 0,
            "test_evaluated": False, "october_inputs_used": False,
            "prior_exposure": "New retrieval design follows known October failure modes. No October examples or outcomes are read by this runner. 2024 has already been exposed.",
            **{key: value for key, value in provenance.items() if key != "prior_exposure"}}
    immutable_json(output / "plan.json", plan)
    source_dir = output / "source"
    source_dir.mkdir()
    for name in SOURCE_FILES:
        shutil.copy2(ROOT / name, source_dir / name)
    print("Frozen three enhanced candidates plus archived baseline; only 2019–2024 development rows", flush=True)
    rows = pd.concat([fit_rows, calibration], ignore_index=True)
    vectors, embedding = embedding_matrix(rows)
    X, C = vectors[:len(fit_rows)], vectors[len(fit_rows):]
    with threadpool_limits(limits=1):
        H, old_names = vote_features.features(fit_rows.drop(columns="nbim_vote"), X, fit_rows, X, target=TARGET)
        R, new_names, fit_matches = retrieve(fit_rows, X, fit_rows, X)
        fit_audit = audit_retrieval(fit_rows, fit_matches)
        save_retrieval(output / "retrieval-fit.jsonl.gz", fit_matches)
        del fit_matches
        print(f"Training history ready: {len(fit_rows)} rows, {len(new_names)} new features", flush=True)
        scores_by_model = {BASELINE["name"]: archived_validation[BASELINE["name"]].to_numpy(dtype=float)}
        enhanced_scores = {config["name"]: np.full(len(fit_rows), np.nan) for config in CONFIGS[1:]}
        for year, train, check in folds:
            print(f"Forward validation {year}: train {len(train)}, validate {len(check)}", flush=True)
            for config in CONFIGS[1:]:
                state = fit(config, fit_rows.iloc[train], H[train], R[train], X[train], new_names)
                enhanced_scores[config["name"]][check] = predict_scores(state, H[check], R[check], X[check], new_names)
        scores_by_model.update({name: values[checks] for name, values in enhanced_scores.items()})
        candidates = selection_rows(fit_rows.iloc[checks], scores_by_model)
        selected = candidates[0]
        immutable_json(output / "selection.json", {"selected": selected, "candidates": candidates,
                       "calibration_used_to_choose_model": False, "created_at": now()})
        validation = fit_rows.iloc[checks][FIELDS].copy()
        validation["actual_disagreement"] = target_labels(validation, TARGET)
        for name, values in scores_by_model.items():
            validation[name] = values
        validation.to_csv(output / "validation.csv", index=False)
        print(f"Selection locked: {selected['config']['name']} with validation F1={selected['validation']['f1']:.6f}", flush=True)
        Q, actual_names = vote_features.features(calibration.drop(columns="nbim_vote"), C, rows, vectors, target=TARGET)
        S, actual_new_names, cal_matches = retrieve(calibration, C, rows, vectors)
        if actual_names != old_names or actual_new_names != new_names:
            raise ValueError("Feature schema changed after selection")
        cal_audit = audit_retrieval(calibration, cal_matches)
        save_retrieval(output / "retrieval-calibration.jsonl.gz", cal_matches)
        del cal_matches
        archived_calibration = f1_experiment.read_predictions(previous / "calibration.csv")
        check_baseline(calibration, archived_calibration)
        prediction_scores = {BASELINE["name"]: archived_calibration.score.to_numpy(dtype=float)}
        for config in CONFIGS[1:]:
            state = fit(config, fit_rows, H, R, X, new_names)
            model_path = output / (config["name"] + ".joblib")
            joblib.dump(state, model_path, compress=3)
            prediction_scores[config["name"]] = predict_scores(state, Q, S, C, new_names)
            print(f"Scored exposed 2024 with {config['name']}", flush=True)
    labels = target_labels(calibration, TARGET)
    comparisons = []
    validation_by_name = {item["config"]["name"]: item for item in candidates}
    all_predictions = calibration[FIELDS].copy()
    all_predictions["actual_disagreement"] = labels
    for config in CONFIGS:
        values = prediction_scores[config["name"]]
        point = f1_experiment.best_f1(labels, values)
        val_threshold = validation_by_name[config["name"]]["threshold"]
        comparisons.append({"config": config, "selected_on_validation": config == selected["config"],
                            "calibration": point, "validation_threshold": val_threshold,
                            "calibration_at_validation_threshold": board_experiment.measure(labels, values, val_threshold)})
        all_predictions[config["name"]] = values
    all_predictions.to_csv(output / "calibration-all.csv", index=False)
    selected_cal = next(item for item in comparisons if item["selected_on_validation"])
    selected_scores = prediction_scores[selected["config"]["name"]]
    threshold = selected_cal["calibration"]["threshold"]
    predicted = np.isfinite(selected_scores) & (selected_scores >= threshold)
    saved = calibration[FIELDS].copy()
    saved["actual_disagreement"] = labels
    saved["score"], saved["threshold"] = selected_scores, threshold
    saved["prediction"] = np.where(~np.isfinite(selected_scores), "UNKNOWN", np.where(predicted, "DISAGREE", "WITH_BOARD"))
    saved["error"] = np.select([predicted & ~labels, ~predicted & labels], ["FP", "FN"], "")
    saved.to_csv(output / "calibration.csv", index=False)
    if selected["config"]["kind"] == "baseline":
        shutil.copy2(previous / "learner.joblib", output / "learner.joblib")
    else:
        shutil.copy2(output / (selected["config"]["name"] + ".joblib"), output / "learner.joblib")
    np.savez_compressed(output / "calibration-inputs.npz", history=Q, retrieval=S, vectors=C)
    immutable_json(output / "feature_names.json", {"existing": old_names, "retrieval": new_names, "target": TARGET})
    immutable_json(output / "retrieval-audit.json", {"fit": fit_audit, "calibration": cal_audit,
                   "current_labels_in_query": False, "ranking_uses_labels": False,
                   "source_rationales_or_categories_used": False, "lexical_fitted_on_future": False,
                   "model_preprocessing_fit_on_training_only": True})
    if {name: digest(ROOT / name) for name in SOURCE_FILES} != sources:
        raise ValueError("Experiment source changed during the run")
    summary = {"experiment": "HYBRID_HISTORY_F1_ABLATION", "created_at": now(), "target": TARGET,
               "objective": "maximize_f1", "positive_class": "NBIM != mgmt_rec", "api_calls": 0,
               "evaluation_kind": "EXPOSED_2024_CALIBRATION", "fit_period": "2019–2023",
               "selection_period": "2020–2023", "calibration_period": "2024", "test_evaluated": False,
               "october_inputs_used": False, "october_test_unchanged": True,
               "fit": board_experiment.sizes(fit_rows), "calibration": board_experiment.sizes(calibration),
               "selected_config": selected["config"], "selected_threshold": threshold,
               "validation_threshold": selected["threshold"], "model_selection_validation": selected["validation"],
               "calibration_selected": selected_cal["calibration"]["metrics"],
               "calibration_at_validation_threshold": selected_cal["calibration_at_validation_threshold"],
               "candidates": candidates, "comparisons": comparisons,
               "retrieval": RETRIEVAL, "retrieval_audit": {"fit": fit_audit, "calibration": cal_audit},
               "embedding": embedding, "source_hashes": sources, "source_sha256": provenance["source_sha256"],
               "rules_used": False, "filings_used": False, "seconds": time.monotonic() - start,
               "caveats": ["Model and thresholds are selected on development data; their optimized scores are optimistic.",
                           "2024 is already exposed calibration, not an untouched final test.",
                           "All four 2024 ablations were predeclared; the winning model stays the one selected using 2020–2023.",
                           "The design follows known October weaknesses; no October inputs or outputs are read here.",
                           "The five-day historical availability lag is a conservative proxy, not verified publication metadata.",
                           "This local ablation tests historical retrieval only. Current filing/rule evidence is evaluated separately.",
                           "Fixed BGE embeddings are pretrained externally; this check cannot audit their original training corpus."],
               "artifacts": {str(path.relative_to(output)): digest(path) for path in output.rglob("*") if path.is_file()}}
    summary["record_id"] = fingerprint(summary)
    immutable_json(output / "summary.json", summary)
    return summary


def predict(output, meeting, item):
    """Replay a saved 2024 proposal using the selected model and its actual threshold."""
    output = Path(output)
    summary = json.loads((output / "summary.json").read_text())
    if summary.get("record_id") != fingerprint({key: value for key, value in summary.items() if key != "record_id"}):
        raise ValueError("Experiment summary changed")
    for name in ("calibration.csv", "calibration-inputs.npz", "feature_names.json", "learner.joblib"):
        f1_experiment.checked_path(output, name, summary["artifacts"][name])
    frame = f1_experiment.read_predictions(output / "calibration.csv")
    indices = np.flatnonzero(frame.meeting_id.eq(str(meeting)) & frame.item_no.eq(str(item)))
    if len(indices) != 1:
        raise ValueError("Select exactly one saved calibration proposal")
    query = frame.iloc[indices][[name for name in FIELDS if name != "nbim_vote"]]
    with np.load(output / "calibration-inputs.npz", allow_pickle=False) as inputs:
        history, retrieval, vectors = (inputs[name][indices] for name in ("history", "retrieval", "vectors"))
    state = joblib.load(output / "learner.joblib")
    if state.get("target") != TARGET:
        raise ValueError("Wrong saved model target")
    if summary["selected_config"]["kind"] == "baseline":
        score = float(vote_learner.predict(state, query, history, vectors)[0])
    else:
        names = json.loads((output / "feature_names.json").read_text())["retrieval"]
        score = float(predict_scores(state, history, retrieval, vectors, names)[0])
    return {"meeting_id": str(meeting), "item_no": str(item), "target": TARGET,
            "score": score, "threshold": summary["selected_threshold"],
            "prediction": "DISAGREE" if score >= summary["selected_threshold"] else "WITH_BOARD", "api_calls": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--output", type=Path, default=OUTPUT)
    predict_parser = sub.add_parser("predict")
    predict_parser.add_argument("--output", type=Path, default=OUTPUT)
    predict_parser.add_argument("--meeting", required=True)
    predict_parser.add_argument("--item", required=True)
    args = parser.parse_args()
    result = run(args.output) if args.command == "run" else predict(args.output, args.meeting, args.item)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
