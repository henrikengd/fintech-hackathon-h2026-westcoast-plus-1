"""Offline learned vector/history model, selected for BOTH MOT precision and recall.

The candidate list and selection criterion are saved before validation. Thresholds
are locked on forward predictions before scoring the exposed 2024
development cohort. Reserved 20% labels and old 2025–2026 holdout are never used.
"""
import boot  # noqa: F401
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time

import joblib
import numpy as np
import pandas as pd
import sklearn
from threadpoolctl import threadpool_limits

import vote_features
import vote_learner
from vector_experiment import (ROOT, SPLIT, KEY, FIELDS, digest, write_json, load_development,
                               embedding_matrix, forward_folds, metrics, sizes, old_text_reference, cached_reference)
from vector_model import VectorVoteModel

OUTPUT = ROOT / "data/local-rag/vote-learning-v2"
TARGET = .85


def threshold_options(labels, scores, target=TARGET):
    """Choose fixed operating points on validation only, retaining ties/missing rows.

    Balanced maximizes min(precision, recall), then F1, then precision. The two
    constrained alternatives maximize recall subject to P>target and precision
    subject to R>target. None means the requested constraint is not achievable.
    """
    if not 0 < target < 1:
        raise ValueError("Target must be in (0,1)")
    y = np.asarray(labels, dtype=bool)
    scores = np.asarray(scores, dtype=float)
    if y.shape != scores.shape or not y.any() or not np.isfinite(scores).any():
        raise ValueError("Threshold selection requires aligned scores and MOT labels")
    finite = np.isfinite(scores)
    order = np.argsort(-scores[finite], kind="stable")
    ranked, truth = scores[finite][order], y[finite][order]
    ends = np.r_[np.flatnonzero(ranked[:-1] != ranked[1:]), len(ranked) - 1]
    tp = np.cumsum(truth)[ends]
    precision, recall = tp / (ends + 1), tp / y.sum()
    f1 = np.divide(2 * precision * recall, precision + recall, out=np.zeros_like(precision), where=precision + recall > 0)
    indices = range(len(ends))
    balanced = max(indices, key=lambda i: (min(precision[i], recall[i]), f1[i], precision[i], ranked[ends[i]]))
    high_p = [i for i in indices if precision[i] > target]
    high_r = [i for i in indices if recall[i] > target]
    selected = {"balanced": balanced,
                "precision": max(high_p, key=lambda i: (recall[i], precision[i], ranked[ends[i]])) if high_p else None,
                "recall": max(high_r, key=lambda i: (precision[i], recall[i], ranked[ends[i]])) if high_r else None}
    return {name: {"threshold": float(ranked[ends[i]]), "validation": metrics(y, scores, float(ranked[ends[i]]))}
            if i is not None else {"threshold": None, "validation": None} for name, i in selected.items()}


def selection_key(result):
    m = result["operating_points"]["balanced"]["validation"]
    return (min(m["precision"], m["recall"]), m["f1"], m["precision"])


def old_vector_reference(dev):
    path = ROOT / "data/local-rag/vector-experiment-v1/development.csv"
    if not path.exists():
        return None
    old = pd.read_csv(path, dtype=str, keep_default_na=False)
    joined = dev[KEY + ["nbim_vote"]].merge(old[KEY + ["score", "threshold"]], on=KEY, validate="one_to_one")
    if len(joined) != len(dev) or len(old) != len(dev) or joined.threshold.nunique() != 1:
        raise ValueError("Vector reference cohort mismatch")
    return {**metrics(joined.nbim_vote.eq("MOT"), joined.score.astype(float), float(joined.threshold.iloc[0])),
            "artifact_sha256": digest(path)}


def learning_folds(frame, warmup_year=2019):
    """Warmup rows remain reference history but do not train the classifier."""
    eligible = np.ones(len(frame), dtype=bool) if warmup_year is None else frame.meeting_date.gt(f"{warmup_year}-12-31").to_numpy()
    folds = []
    for year, reference, check in forward_folds(frame):
        training = reference[eligible[reference]]
        if len(training):
            folds.append((year, training, reference, check))
    if not folds:
        raise ValueError("No supervised years remain after warmup")
    return np.flatnonzero(eligible), folds


def run(output=OUTPUT, split=SPLIT, warmup_year=2019):
    started = time.monotonic()
    output = Path(output)
    if output.exists():
        raise ValueError("Output exists; retain old experiments and choose a new --output")
    fit, dev, provenance = load_development(split)
    all_vectors, embedding = embedding_matrix(pd.concat([fit, dev], ignore_index=True))
    X, D = all_vectors[:len(fit)], all_vectors[len(fit):]
    output.mkdir(parents=True)
    source_files = ("vote_experiment.py", "vote_learner.py", "vote_features.py", "vector_experiment.py", "vector_model.py")
    sources = {name: digest(ROOT / name) for name in source_files}
    source_dir = output / "source"
    source_dir.mkdir()
    for name in source_files:
        shutil.copy2(ROOT / name, source_dir / name)
    learning_rows, folds = learning_folds(fit, warmup_year)
    write_json(output / "plan.json", {"created_at": datetime.now(timezone.utc).isoformat(), "target_precision": TARGET,
                                     "target_recall": TARGET, "strictly_greater": True, "configurations": vote_learner.CONFIGS,
                                     "selection": "max min(precision,recall), tie F1 then precision; fixed config order final tie",
                                     "fold_years": [year for year, _, _, _ in folds], "warmup_year": warmup_year,
                                     "source_hashes": sources, **provenance})
    print("Computing 59 historical/vector features with strict as-of reference filtering", flush=True)
    H, names = vote_features.features(fit, X, fit, X)
    checking = np.concatenate([check for _, _, _, check in folds])
    labels = fit.nbim_vote.eq("MOT").to_numpy()
    predictions = {config["name"]: np.full(len(fit), np.nan) for config in vote_learner.CONFIGS}
    for year, train, reference, check in folds:
        print(f"Year {year}: {len(train)} fit / {len(check)} validation", flush=True)
        V, actual_names = vote_features.features(fit.iloc[check], X[check], fit.iloc[reference], X[reference])
        if names != actual_names:
            raise ValueError("Feature order changed")
        for config in vote_learner.CONFIGS:
            model = vote_learner.fit(config, fit.iloc[train], H[train], X[train])
            predictions[config["name"]][check] = vote_learner.predict(model, fit.iloc[check], V, X[check])
    candidates = [{"config": config, "operating_points": threshold_options(labels[checking], predictions[config["name"]][checking])}
                  for config in vote_learner.CONFIGS]
    selected = max(candidates, key=selection_key)
    config = selected["config"]
    threshold = selected["operating_points"]["balanced"]["threshold"]
    write_json(output / "selection.json", {"selected": selected, "configurations": candidates, **provenance})
    rows = fit.iloc[checking][FIELDS].copy()
    for name, scores in predictions.items():
        rows[name] = scores[checking]
    rows.to_csv(output / "validation.csv", index=False)
    print(f"Locked {config['name']} threshold={threshold:.6f}; evaluating 2024", flush=True)
    model = vote_learner.fit(config, fit.iloc[learning_rows], H[learning_rows], X[learning_rows])
    Q, actual_names = vote_features.features(dev, D, fit, X)
    if actual_names != names:
        raise ValueError("Feature order changed")
    scores = vote_learner.predict(model, dev, Q, D)
    points = [{"name": name, **point, "development": metrics(dev.nbim_vote.eq("MOT"), scores, point["threshold"])
               if point["threshold"] is not None else None} for name, point in selected["operating_points"].items()]
    development = dev[FIELDS].copy()
    development["score"], development["threshold"] = scores, threshold
    development["prediction"] = np.where(scores >= threshold, "MOT", "NOT_MOT")
    development["error"] = np.select([development.prediction.eq("MOT") & development.nbim_vote.ne("MOT"),
                                       development.prediction.ne("MOT") & development.nbim_vote.eq("MOT")], ["FP", "FN"], "")
    development["family"] = dev.proposal_text.map(vote_features.proposal_family)
    development.to_csv(output / "development.csv", index=False)
    np.savez_compressed(output / "development-inputs.npz", history=Q, vectors=D)
    # Pickle contains only our own locally generated sklearn estimators; never load untrusted files.
    joblib.dump(model, output / "learner.joblib", compress=3)
    VectorVoteModel().fit(fit, X).save(output / "reference")
    write_json(output / "feature_names.json", {"names": names})
    per_year = [{"year": year, **metrics(labels[check], predictions[config["name"]][check], threshold)}
                for year, _, _, check in folds]
    summary = {"experiment": "LOCAL_LEARNED_VECTOR_HISTORY_MOT", "created_at": datetime.now(timezone.utc).isoformat(),
               **provenance, "api_calls": 0, "target_precision": TARGET, "target_recall": TARGET,
               "target_rule": "Both strictly greater than 0.85", "selected_config": config, "selected_threshold": threshold,
               "feature_count": len(names), "embedding": embedding, "source_hashes": sources,
               "history_transform": model.get("history_transform", "identity"),
               "sklearn_version": sklearn.__version__, "fit_period": "2019–2023" if warmup_year is None else f"{warmup_year + 1}–2023",
               "reference_period": "2019–2023", "warmup_year": warmup_year, "development_period": "2024",
               "fit": sizes(fit.iloc[learning_rows]), "reference": sizes(fit), "development": sizes(dev),
               "validation_selected": selected["operating_points"]["balanced"]["validation"], "validation_per_year": per_year,
               "development_selected": points[0]["development"], "operating_points": points,
               "development_follow_board": metrics(dev.nbim_vote.eq("MOT"), dev.mgmt_rec.eq("MOT").astype(float), .5),
               "local_vector_same_development": old_vector_reference(dev), "local_text_same_development": old_text_reference(dev),
               "cached_claude_same_development": cached_reference(dev), "elapsed_seconds": time.monotonic() - started,
               "caveats": ["2024 is previously exposed development data, not an independent final test.",
                           "Thresholds and model use forward validation after warmup; validation scores are selection-biased.",
                           "Pretrained BGE encoder has no verified historical training cutoff.",
                           "Historical votes and lexical matches do not establish a current guideline violation.",
                           "MOT vs NOT_MOT only; scores are not calibrated confidence.",
                           "The mixed 20% test labels and old 2025–2026 holdout are excluded."],
               "artifacts": {str(path.relative_to(output)): digest(path) for path in output.rglob("*") if path.is_file()}}
    write_json(output / "summary.json", summary)
    print(json.dumps({"model": config["name"], "validation": summary["validation_selected"],
                      "development": summary["development_selected"], "elapsed_seconds": summary["elapsed_seconds"]}, indent=2), flush=True)
    return summary


def predict(output, meeting, item):
    """Recompute one saved development prediction without reading its label as input."""
    output = Path(output)
    summary = json.loads((output / "summary.json").read_text())
    for relative, expected in summary["artifacts"].items():
        path = (output / relative).resolve()
        if not path.is_relative_to(output.resolve()) or digest(path) != expected:
            raise ValueError("Saved artifact changed or unsafe path")
    frame = pd.read_csv(output / "development.csv", dtype=str, keep_default_na=False)
    selected = np.flatnonzero(frame.meeting_id.eq(str(meeting)) & frame.item_no.eq(str(item)))
    if len(selected) != 1:
        raise ValueError("Select one proposal by meeting and item")
    with np.load(output / "development-inputs.npz", allow_pickle=False) as data:
        H, X = data["history"][selected], data["vectors"][selected]
    model = joblib.load(output / "learner.joblib")
    # The first warmup run predates the explicit state field. Its archived source
    # and warmup protocol identify the exact transform used during training.
    if "history_transform" not in model and "warmup_year" in summary:
        if summary.get("source_hashes", {}).get("vote_learner.py") != "f7c7abeaa21f6ede5f40633d618c5f593f9ce2c81ef3bbb01125e893d3ae1581":
            raise ValueError("Unversioned historical preprocessing; use the archived source")
        model["history_transform"] = "capped-counts-50-ages-3-v1"
    query = frame.iloc[selected].drop(columns=["nbim_vote", "prediction", "score", "threshold", "error"])
    score = float(vote_learner.predict(model, query, H, X)[0])
    threshold = summary["selected_threshold"]
    return {"meeting_id": str(meeting), "item_no": str(item), "score": score, "threshold": threshold,
            "prediction": "MOT" if score >= threshold else "NOT_MOT", "api_calls": 0,
            "note": "Uncalibrated local MOT classifier; not a guideline-backed voting recommendation"}


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
            print(json.dumps(predict(args.output, args.meeting, args.item), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
