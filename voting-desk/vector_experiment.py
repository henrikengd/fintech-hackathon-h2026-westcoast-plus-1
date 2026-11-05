"""Offline historical-vector voting benchmark with forward validation and a recall target."""
import boot  # noqa: F401
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from hashlib import sha256
import inspect
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

import local_rag
from mot_experiment import cached_reference
from vector_model import VectorVoteModel, input_text


ROOT = Path(__file__).resolve().parent
SPLIT = ROOT / "data/mixed-80-20"
OUTPUT = ROOT / "data/local-rag/vector-experiment-v1"
CACHE = ROOT / "data/local-rag/vector-embeddings"
KEY = ["meeting_id", "item_no"]
GROUP = ["company_id", "meeting_date"]
FIELDS = [*KEY, *GROUP, "company", "proposal_text", "mgmt_rec", "proponent", "nbim_vote"]
CONFIGS = [{"k": k, "company_weight": weight} for k in (8, 32, 128) for weight in (1.0, 4.0)]
YEARS = (2020, 2021, 2022, 2023)


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def identity(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)


def load_development(split=SPLIT):
    """Access labels only after restricting rows to 2019–2024 in the train partition."""
    split = Path(split)
    manifest = json.loads((split / "manifest.json").read_text())
    for filename in ("train.csv", "test.csv"):
        if digest(split / filename) != manifest["files"][filename]:
            raise ValueError("Saved partition hash mismatch")
    if digest(split / manifest["source"]["path"]) != manifest["source_sha256"]:
        raise ValueError("Original source hash mismatch")
    reserved = pd.read_csv(split / "test.csv", dtype=str, keep_default_na=False, usecols=KEY + GROUP)
    rows = []
    with (split / "train.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if "2019-01-01" <= row["meeting_date"] <= "2024-12-31":
                rows.append({field: row[field] for field in FIELDS})
    frame = pd.DataFrame(rows, columns=FIELDS)
    if frame.empty or frame.duplicated(KEY).any() or frame[KEY + GROUP].eq("").any().any():
        raise ValueError("Invalid or duplicate development identities")
    for fields in (KEY, GROUP, ["meeting_id"]):
        if set(map(tuple, frame[fields].values)) & set(map(tuple, reserved[fields].values)):
            raise ValueError("Reserved test meeting overlaps development")
    if not frame.nbim_vote.isin(["", "FOR", "MOT", "AVSTÅ"]).all():
        raise ValueError("Unexpected label")
    unknown = int(frame.nbim_vote.eq("").sum())
    frame = frame.loc[frame.nbim_vote.ne("")].sort_values(["meeting_date", *KEY], kind="stable").reset_index(drop=True)
    pd.to_datetime(frame.meeting_date, format="%Y-%m-%d", errors="raise")
    fit = frame.loc[frame.meeting_date < "2024-01-01"].reset_index(drop=True)
    dev = frame.loc[frame.meeting_date >= "2024-01-01"].reset_index(drop=True)
    if fit.empty or dev.empty:
        raise ValueError("Both fit and development rows are required")
    return fit, dev, {"dataset_id": manifest["dataset_id"], "source_sha256": manifest["source_sha256"],
                      "split_train_sha256": manifest["files"]["train.csv"], "split_test_sha256": manifest["files"]["test.csv"],
                      "unknown_labels_excluded": unknown}


def embedding_matrix(frame, cache=CACHE):
    texts = [input_text(row) for row in frame.to_dict("records")]
    meta = {"model": local_rag.MODEL, "assets": local_rag.model_fingerprint(),
            "inputs_sha256": identity(texts), "encoder_source": identity(inspect.getsource(input_text)),
            "encoding": "symmetric passage_embed on allowlisted ballot inputs"}
    key = identity(meta)
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    path, manifest = cache / f"{key}.npz", cache / f"{key}.json"
    if path.exists() or manifest.exists():
        saved = json.loads(manifest.read_text())
        if saved["identity"] != meta or digest(path) != saved["vectors_sha256"]:
            raise ValueError("Embedding cache mismatch")
        with np.load(path, allow_pickle=False) as data:
            vectors = data["vectors"]
    else:
        unique = list(dict.fromkeys(texts))
        print(f"Embedding {len(unique)} unique ballot texts locally; {len(texts)} total rows", flush=True)
        model = local_rag.load_model(download=False)
        values = local_rag.unit_vectors(list(model.passage_embed(unique, batch_size=64)))
        by_text = {text: i for i, text in enumerate(unique)}
        vectors = values[[by_text[text] for text in texts]]
        np.savez_compressed(path, vectors=vectors)
        write_json(manifest, {"identity": meta, "vectors_sha256": digest(path), "unique_texts": len(unique)})
    if len(vectors) != len(frame) or vectors.shape[1] != 384:
        raise ValueError("Embedding dimensions or row order disagree")
    return local_rag.unit_vectors(vectors), {"cache_id": key, "vectors_sha256": digest(path), "model": local_rag.MODEL,
                                           "model_assets": meta["assets"], "input_sha256": meta["inputs_sha256"]}


def metrics(labels, scores, threshold):
    y = np.asarray(labels, dtype=bool)
    scores = np.asarray([np.nan if s is None else s for s in scores], dtype=float)
    covered = np.isfinite(scores)
    pred = covered & (scores >= threshold)
    tp, fp, fn, tn = [int(mask.sum()) for mask in (pred & y, pred & ~y, ~pred & y, ~pred & ~y)]
    n = len(y)
    return {"n": n, "mot": int(y.sum()), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            "false_positive_rate": fp / (fp + tn) if fp + tn else None,
            "predicted_mot": int(pred.sum()), "predicted_mot_share": float(pred.mean()) if n else None,
            "covered": int(covered.sum()), "uncovered": int((~covered).sum()),
            "recommendation_coverage": float(covered.mean()) if n else None}


def select_threshold(labels, scores, target_recall=0.85):
    """Maximize precision subject to recall; missing scores stay in the FN denominator."""
    if not 0 < target_recall <= 1:
        raise ValueError("Recall target must be in (0,1]")
    y = np.asarray(labels, dtype=bool)
    scores = np.asarray([np.nan if s is None else s for s in scores], dtype=float)
    finite = np.isfinite(scores)
    if not y.any() or not finite.any():
        return None
    order = np.argsort(-scores[finite], kind="stable")
    ranked, truth = scores[finite][order], y[finite][order]
    ends = np.r_[np.flatnonzero(ranked[:-1] != ranked[1:]), len(ranked) - 1]
    tp = np.cumsum(truth)[ends]
    precision, recall = tp / (ends + 1), tp / y.sum()
    choices = [i for i in range(len(ends)) if recall[i] >= target_recall]
    if not choices:
        return None
    best = max(choices, key=lambda i: (precision[i], recall[i], ranked[ends[i]]))
    return float(ranked[ends[best]])


def forward_folds(frame):
    dates = frame.meeting_date
    folds = []
    for year in YEARS:
        fit = np.flatnonzero(dates < f"{year}-01-01")
        check = np.flatnonzero(dates.str.startswith(f"{year}-"))
        if not len(fit) or not len(check):
            raise ValueError(f"Missing temporal fold {year}")
        if dates.iloc[fit].max() >= dates.iloc[check].min():
            raise ValueError("Temporal fold overlaps")
        folds.append((year, fit, check))
    return folds


def sizes(frame):
    return {"rows": len(frame), "mot": int(frame.nbim_vote.eq("MOT").sum()),
            "meetings": int(frame.meeting_id.nunique()), "companies": int(frame.company_id.nunique())}


def old_text_reference(dev):
    path = ROOT / "data/local-rag/mot-experiment-v1/development.csv"
    if not path.exists():
        return None
    old = pd.read_csv(path, dtype=str, keep_default_na=False)
    if set(map(tuple, old[KEY].values)) != set(map(tuple, dev[KEY].values)):
        raise ValueError("Text model comparison uses a different cohort")
    joined = dev[KEY + ["nbim_vote"]].merge(old[KEY + ["score", "threshold"]], on=KEY, validate="one_to_one")
    if joined.threshold.nunique() != 1:
        raise ValueError("Text comparison has inconsistent thresholds")
    return {**metrics(joined.nbim_vote.eq("MOT"), joined.score.astype(float), float(joined.threshold.iloc[0])),
            "note": "Earlier local text model selected for F1, not the new recall target", "artifact_sha256": digest(path)}


def run(output=OUTPUT, split=SPLIT, target_recall=0.85):
    started = time.monotonic()
    output = Path(output)
    if output.exists():
        raise ValueError("Output exists; choose a new --output to retain previous experiments")
    fit, dev, provenance = load_development(split)
    all_vectors, embedding = embedding_matrix(pd.concat([fit, dev], ignore_index=True))
    fit_vectors, dev_vectors = all_vectors[:len(fit)], all_vectors[len(fit):]
    folds = forward_folds(fit)
    validation = fit.loc[fit.meeting_date >= "2020-01-01"].copy()
    configs, exports, candidates = [], [], []
    for config in CONFIGS:
        print(f"Forward validation: {config}", flush=True)
        scores = np.full(len(fit), np.nan)
        for year, training, checking in folds:
            model = VectorVoteModel().fit(fit.iloc[training], fit_vectors[training])
            results = model.predict(fit.iloc[checking], fit_vectors[checking], **config, neighbor_limit=0)
            scores[checking] = [np.nan if x["score"] is None else x["score"] for x in results]
        chosen_scores = scores[validation.index]
        threshold = select_threshold(validation.nbim_vote.eq("MOT"), chosen_scores, target_recall)
        diagnostic_threshold = threshold if threshold is not None else 0.0
        result = {"config": config, "threshold": threshold, "target_feasible": threshold is not None,
                  "metrics": metrics(validation.nbim_vote.eq("MOT"), chosen_scores, diagnostic_threshold),
                  "per_year": [{"year": year, **metrics(fit.iloc[check].nbim_vote.eq("MOT"), scores[check], diagnostic_threshold)}
                               for year, _, check in folds]}
        configs.append(result)
        if threshold is not None:
            candidates.append((result["metrics"]["precision"], result["metrics"]["recall"], -config["k"], -config["company_weight"], len(configs) - 1))
        rows = validation[KEY + GROUP + ["nbim_vote"]].copy()
        rows["score"], rows["k"], rows["company_weight"] = chosen_scores, config["k"], config["company_weight"]
        exports.append(rows)
    if not candidates:
        raise ValueError("No candidate reaches the recall target; no development threshold selected")
    selected = configs[max(candidates)[-1]]
    output.mkdir(parents=True)
    write_json(output / "selection.json", {"target_recall": target_recall, "configurations": configs,
                                           "selected": selected, "provenance": provenance})
    config, threshold = selected["config"], selected["threshold"]
    print(f"Locked {config} at threshold {threshold:.6f}; scoring 2024 once", flush=True)
    model = VectorVoteModel().fit(fit, fit_vectors)
    results = model.predict(dev, dev_vectors, **config, neighbor_limit=5)
    scores = [x["score"] for x in results]
    measured = metrics(dev.nbim_vote.eq("MOT"), scores, threshold)
    rows = dev[FIELDS].copy()
    rows["score"], rows["threshold"] = scores, threshold
    rows["prediction"] = ["UNKNOWN" if x is None else "MOT" if x >= threshold else "NOT_MOT" for x in scores]
    rows["error"] = np.select([rows.prediction.eq("MOT") & rows.nbim_vote.ne("MOT"), rows.prediction.ne("MOT") & rows.nbim_vote.eq("MOT")], ["FP", "FN"], "")
    rows.to_csv(output / "development.csv", index=False)
    pd.concat(exports, ignore_index=True).to_csv(output / "validation.csv", index=False)
    examples = [{**{name: row[name] for name in FIELDS if name != "nbim_vote"}, **result,
                 "prediction": "UNKNOWN" if result["score"] is None else "MOT" if result["score"] >= threshold else "NOT_MOT"}
                for row, result in zip(dev.to_dict("records"), results)]
    write_json(output / "neighbors.json", {"note": "At most five displayed neighbours; all selected k neighbours contribute. Historical votes do not establish guideline compliance.", "items": examples})
    model.save(output / "model")
    np.savez_compressed(output / "development-vectors.npz", vectors=dev_vectors)
    summary = {"experiment": "LOCAL_VECTOR_MOT_FORWARD_VALIDATION", "created_at": datetime.now(timezone.utc).isoformat(),
               **provenance, "embedding_model": local_rag.MODEL, "embedding_dimension": int(fit_vectors.shape[1]),
               "embedding": embedding, "api_calls": 0, "target_recall": target_recall, "selected_config": config,
               "selected_threshold": threshold, "validation_selected": selected["metrics"], "validation_per_year": selected["per_year"],
               "configurations": configs, "development_selected": measured,
               "development_follow_board": metrics(dev.nbim_vote.eq("MOT"), dev.mgmt_rec.eq("MOT").astype(float), 0.5),
               "cached_claude_same_development": cached_reference(dev), "local_text_same_development": old_text_reference(dev),
               "all_mot_baseline": metrics(dev.nbim_vote.eq("MOT"), np.ones(len(dev)), 0.5),
               "target_achieved_development": measured["recall"] >= target_recall,
               "sizes": {"fit": sizes(fit), "validation": sizes(validation), "development": sizes(dev)},
               "fit_period": "2019–2023", "development_period": "2024", "reserved_test_used": False,
               "selection": "Maximum pooled forward-validation precision subject to recall >= target; folds 2020–2023 use only earlier years; threshold locked before 2024 scoring",
               "caveat": "Validation scores are selection statistics. 2024 is previously exposed development data. Neither is a new independent final test. The frozen pretrained encoder may encode information acquired after historical dates.",
               "score_meaning": "Weighted historical MOT share, not calibrated probability or a deciding guideline",
               "negative_class": "NOT_MOT combines FOR and AVSTÅ; this model does not distinguish them",
               "threshold_zero": threshold == 0.0, "elapsed_seconds": round(time.monotonic() - started, 3),
               "code_sha256": {name: digest(ROOT / name) for name in ("vector_model.py", "vector_experiment.py")}}
    summary["artifacts"] = {str(p.relative_to(output)): digest(p) for p in output.rglob("*") if p.is_file()}
    write_json(output / "summary.json", summary)
    print(json.dumps({"output": str(output.resolve()), "selected": config, "threshold": threshold,
                      "validation": selected["metrics"], "development": measured}, indent=2), flush=True)
    return summary


def predict(output, meeting, item):
    output = Path(output)
    summary = json.loads((output / "summary.json").read_text())
    for name, expected in summary["artifacts"].items():
        if digest(output / name) != expected:
            raise ValueError("Saved experiment artifact changed")
    rows = pd.read_csv(output / "development.csv", dtype=str, keep_default_na=False)
    selected = np.flatnonzero(rows.meeting_id.eq(str(meeting)) & rows.item_no.eq(str(item)))
    if len(selected) != 1:
        raise ValueError("Select one proposal from this experiment's development.csv")
    i = selected[0]
    with np.load(output / "development-vectors.npz", allow_pickle=False) as data:
        vectors = data["vectors"][[i]]
    model = VectorVoteModel.load(output / "model")
    result = model.predict(rows.iloc[[i]].drop(columns="nbim_vote"), vectors, **summary["selected_config"], neighbor_limit=5)[0]
    score = result["score"]
    return {"meeting_id": str(meeting), "item_no": str(item), "proposal": rows.iloc[i].proposal_text,
            **result, "prediction": "UNKNOWN" if score is None else "MOT" if score >= summary["selected_threshold"] else "NOT_MOT",
            "threshold": summary["selected_threshold"], "api_calls": 0,
            "note": "Score is not calibrated confidence; neighbours describe historical behaviour, not guideline justification"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "predict", "embed"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--split", type=Path, default=SPLIT)
    parser.add_argument("--target-recall", type=float, default=.85)
    parser.add_argument("--meeting")
    parser.add_argument("--item")
    args = parser.parse_args(argv)
    if args.command == "run":
        run(args.output, args.split, args.target_recall)
    elif args.command == "embed":
        fit, dev, _ = load_development(args.split)
        values, meta = embedding_matrix(pd.concat([fit, dev], ignore_index=True))
        print(json.dumps({"rows": len(values), "dimension": values.shape[1], "cache_id": meta["cache_id"]}))
    else:
        print(json.dumps(predict(args.output, args.meeting, args.item), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
