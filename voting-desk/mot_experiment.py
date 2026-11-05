"""Bounded offline literal-MOT model experiment; never score the reserved test data.

Fit and select on 2019–2023 mixed-train rows with grouped five-fold CV. Report the
locked choice on 2024 mixed-train development rows. No source categories/rationales.
"""
import boot  # noqa: F401
import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import importlib.metadata
from pathlib import Path
import re

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import OneHotEncoder

ROOT = Path(__file__).resolve().parent
SPLIT = ROOT / "data/mixed-80-20"
OUTPUT = ROOT / "data/local-rag/mot-experiment-v1"
KEY = ["meeting_id", "item_no"]
GROUP = ["company_id", "meeting_date"]
INPUT = [*KEY, *GROUP, "company", "proposal_text", "mgmt_rec", "proponent", "nbim_vote"]
VARIANTS = ("word", "word_char", "word_history")
PERSON = re.compile(r"(?:elect|re-?elect|appoint)\s+(?:director\s+|statutory auditor\s+)?(.+?)(?:\s+as\b.*)?$", re.I)


def file_hash(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def name_in(text):
    match = PERSON.search(text.strip())
    return match.group(1).strip().lower() if match else ""


def normalized(frame):
    result = frame.copy()
    result["date"] = pd.to_datetime(result["meeting_date"], format="%Y-%m-%d", errors="raise")
    result["person"] = result["proposal_text"].map(name_in)
    result["text_key"] = result["proposal_text"].str.lower().str.replace(r"\s+", " ", regex=True).str.strip()
    result["mot"] = result["nbim_vote"].eq("MOT").astype(int)
    return result.sort_values(["date", *KEY], kind="stable").reset_index(drop=True)


def load_development(split=SPLIT):
    split = Path(split)
    manifest = json.loads((split / "manifest.json").read_text())
    for name in ("train.csv", "test.csv"):
        if file_hash(split / name) != manifest["files"][name]:
            raise ValueError(f"{name} no longer matches the reserved split manifest")
    # Read only identity fields from the reserved test partition, never its labels.
    reserved = pd.read_csv(split / "test.csv", dtype=str, keep_default_na=False, usecols=list(dict.fromkeys(KEY + GROUP)))
    allowed = pd.read_csv(split / "train.csv", dtype=str, keep_default_na=False, usecols=INPUT)
    allowed = allowed.loc[allowed["meeting_date"].between("2019-01-01", "2024-12-31")].copy()
    if allowed.duplicated(KEY).any():
        raise ValueError("Duplicate proposal identities in development data")
    if set(map(tuple, allowed[KEY].values)) & set(map(tuple, reserved[KEY].values)):
        raise ValueError("Reserved test proposals overlap development")
    if set(map(tuple, allowed[GROUP].values)) & set(map(tuple, reserved[GROUP].values)):
        raise ValueError("Reserved meeting groups overlap development")
    if not allowed["nbim_vote"].isin(["", "FOR", "MOT", "AVSTÅ"]).all():
        raise ValueError("Unsupported vote label")
    missing = int(allowed["nbim_vote"].eq("").sum())
    allowed = normalized(allowed.loc[allowed["nbim_vote"].ne("")])
    train = allowed.loc[allowed["date"] < "2024-01-01"].reset_index(drop=True)
    development = allowed.loc[allowed["date"] >= "2024-01-01"].reset_index(drop=True)
    if train.empty or development.empty:
        raise ValueError("Need both earlier training rows and 2024 development rows")
    return train, development, {"dataset_id": manifest["dataset_id"], "source_sha256": manifest["source_sha256"],
                                "split_train_sha256": manifest["files"]["train.csv"],
                                "split_test_sha256": manifest["files"]["test.csv"], "unscored_missing_vote": missing}


def history_features(frame, record):
    """Earlier labeled rows from this fold's training record only, strict five-day lag."""
    if record["nbim_vote"].eq("").any():
        raise ValueError("Historical record must contain known votes only")
    companies = {company: part.sort_values("date", kind="stable") for company, part in record.groupby("company_id")}
    result = np.zeros((len(frame), 7), dtype=np.float64)
    for position, row in enumerate(frame.itertuples(index=False)):
        past = companies.get(row.company_id)
        if past is None:
            continue
        past = past.loc[past["date"] < row.date - pd.Timedelta(days=5)]
        if past.empty:
            continue
        person = past.loc[past["person"].eq(row.person)] if row.person else past.iloc[:0]
        text = past.loc[past["text_key"].eq(row.text_key)]
        result[position] = [
            1.0, float(past["mot"].mean()), float(past["mot"].any()),
            float(person["mot"].iloc[-1]) if len(person) else 0.0, float(len(person) > 0),
            float(text["mot"].iloc[-1]) if len(text) else 0.0, float(len(text) > 0),
        ]
    return result


class MotScreen:
    def __init__(self, variant):
        if variant not in VARIANTS:
            raise ValueError("Unknown bounded variant")
        self.variant = variant

    def features(self, frame, record, fit=False):
        text = frame["proposal_text"]
        categories = frame[["mgmt_rec", "proponent"]]
        if fit:
            self.words = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=30000, sublinear_tf=True)
            self.categories = OneHotEncoder(handle_unknown="ignore", dtype=np.float64)
            blocks = [self.words.fit_transform(text), self.categories.fit_transform(categories)]
            if self.variant == "word_char":
                self.chars = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, max_features=30000, sublinear_tf=True)
                blocks.append(self.chars.fit_transform(text))
        else:
            blocks = [self.words.transform(text), self.categories.transform(categories)]
            if self.variant == "word_char":
                blocks.append(self.chars.transform(text))
        if self.variant == "word_history":
            blocks.append(csr_matrix(history_features(frame, record)))
        return hstack(blocks).tocsr()

    def fit(self, frame):
        features = self.features(frame, frame, fit=True)
        self.model = LogisticRegression(C=1.0, class_weight="balanced", solver="liblinear", max_iter=1000, random_state=2026)
        self.model.fit(features, frame["mot"])
        return self

    def score(self, frame, record):
        return self.model.predict_proba(self.features(frame, record))[:, 1]


def metrics(target, score, threshold=0.5):
    y = np.asarray(target, dtype=bool)
    score = np.asarray(score, dtype=float)
    pred = score >= threshold
    tp, fp, fn, tn = (int(np.sum(mask)) for mask in (pred & y, pred & ~y, ~pred & y, ~pred & ~y))
    return {"n": len(y), "mot": int(y.sum()), "predicted_mot": int(pred.sum()),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            "average_precision": float(average_precision_score(y, score)) if y.any() else None}


def select_threshold(target, score, minimum_precision=None):
    precision, recall, thresholds = precision_recall_curve(target, score)
    f1 = np.divide(2 * precision[:-1] * recall[:-1], precision[:-1] + recall[:-1],
                   out=np.zeros_like(thresholds), where=(precision[:-1] + recall[:-1]) > 0)
    eligible = np.ones(len(thresholds), dtype=bool) if minimum_precision is None else precision[:-1] >= minimum_precision
    if not eligible.any():
        return None
    # Equal F1 resolves toward the higher threshold, keeping fewer false positives.
    best = max(np.flatnonzero(eligible), key=lambda i: (f1[i], thresholds[i]))
    return float(thresholds[best])


def group_folds(train):
    groups = train["company_id"] + "|" + train["meeting_date"]
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=2026)
    folds = list(splitter.split(train, train["mot"], groups))
    for fit, check in folds:
        if set(groups.iloc[fit]) & set(groups.iloc[check]):
            raise AssertionError("Meeting group crosses a fold boundary")
    return folds


def load_screen(path):
    """Load component objects without depending on the CLI's __main__ namespace."""
    saved = joblib.load(path)
    model = MotScreen(saved["variant"])
    model.__dict__.update(saved["components"])
    return model, float(saved["threshold"])


def cached_reference(development, path=ROOT / "results/items_val.csv"):
    """Descriptive existing-pipeline reference; it used a different historical record."""
    if not Path(path).is_file():
        return None
    saved = pd.read_csv(path, dtype=str, keep_default_na=False, usecols=["meeting_id", "item", "draft"])
    saved = saved.rename(columns={"item": "item_no"})
    joined = development[KEY + ["nbim_vote"]].merge(saved, on=KEY, how="left", validate="one_to_one")
    return {**metrics(joined["nbim_vote"].eq("MOT"), joined["draft"].fillna("").eq("MOT").astype(float)),
            "missing_saved_drafts": int(joined["draft"].isna().sum()), "source_sha256": file_hash(path),
            "comparability": "Cached original pipeline used a larger original training/history record, including some now-reserved mixed-test rows. Descriptive reference only; not a controlled refit."}


def run(output=OUTPUT, split=SPLIT):
    output = Path(output)
    if output.exists():
        raise ValueError("Experiment output exists; choose a new --output")
    train, development, provenance = load_development(split)
    folds = group_folds(train)
    summary = {
        "experiment": "LITERAL_MOT_DEVELOPMENT_EXPERIMENT", "created_at": datetime.now(timezone.utc).isoformat(),
        **provenance, "code_sha256": file_hash(__file__), "positive_class": "nbim_vote == MOT",
        "versions": {name: importlib.metadata.version(name) for name in ("scikit-learn", "numpy", "pandas")},
        "fit_period": "2019-2023", "development_period": "2024", "reserved_test_used": False,
        "selection": "Five-fold company/date-grouped CV within 2019-2023 mixed-train; maximum pooled OOF F1; no 2024 selection",
        "caveat": "OOF metrics are selection statistics, not an unbiased test. 2024 is previously exposed development data. No 2025-2026 labels scored.",
        "unknown_vote_rows_excluded": provenance["unscored_missing_vote"],
        "inputs": ["proposal_text", "mgmt_rec", "proponent", "earlier training-only company/person/exact-text votes for word_history"],
        "configurations": {},
    }
    oof_records = []
    selected_model = None
    candidates = []
    for variant in VARIANTS:
        predictions = np.empty(len(train))
        assignments = np.empty(len(train), dtype=int)
        print(f"Cross-validating {variant} …", flush=True)
        for fold_id, (fit, check) in enumerate(folds):
            model = MotScreen(variant).fit(train.iloc[fit])
            predictions[check] = model.score(train.iloc[check], train.iloc[fit])
            assignments[check] = fold_id
        threshold = select_threshold(train["mot"], predictions)
        selected = metrics(train["mot"], predictions, threshold)
        at_precision = {}
        for floor in (0.5, 0.7, 0.8):
            cut = select_threshold(train["mot"], predictions, minimum_precision=floor)
            at_precision[str(floor)] = {"threshold": cut, "metrics": metrics(train["mot"], predictions, cut)} if cut is not None else None
        per_fold = [{"fold": i, **metrics(train.iloc[check]["mot"], predictions[check], threshold)} for i, (_, check) in enumerate(folds)]
        summary["configurations"][variant] = {
            "threshold": threshold, "oof": selected,
            "oof_by_fold": per_fold,
            "fold_variability": {key: {"mean": float(np.mean([f[key] for f in per_fold if f[key] is not None])),
                                        "std": float(np.std([f[key] for f in per_fold if f[key] is not None]))}
                                 for key in ("precision", "recall", "f1")},
            "oof_precision_tradeoffs": at_precision,
            "config": {"C": 1.0, "class_weight": "balanced", "solver": "liblinear", "word_ngrams": [1, 2], "max_word_features": 30000,
                       "char_ngrams": [3, 5] if variant == "word_char" else None,
                       "max_char_features": 30000 if variant == "word_char" else None, "history": variant == "word_history"},
        }
        candidates.append((selected["f1"], selected["precision"] or 0.0, variant))
        frame = train[KEY + GROUP + ["company", "proposal_text", "nbim_vote", "mgmt_rec"]].copy()
        frame["variant"], frame["fold"], frame["score"], frame["threshold"] = variant, assignments, predictions, threshold
        oof_records.append(frame)
    chosen = max(candidates)[2]
    threshold = summary["configurations"][chosen]["threshold"]
    summary["selected_variant"] = chosen
    summary["selected_threshold"] = threshold
    print(f"Locked {chosen} at {threshold:.6f}; evaluating 2024 development once …", flush=True)
    # Only the OOF-selected candidate is evaluated on the later development set.
    selected_model = MotScreen(chosen).fit(train)
    scores = selected_model.score(development, train)
    summary["development_selected"] = metrics(development["mot"], scores, threshold)
    summary["development_follow_board"] = metrics(development["mot"], development["mgmt_rec"].eq("MOT").astype(float))
    summary["training_follow_board"] = metrics(train["mot"], train["mgmt_rec"].eq("MOT").astype(float))
    summary["cached_claude_same_development"] = cached_reference(development)
    summary["sizes"] = {name: {"rows": len(frame), "mot": int(frame["mot"].sum()), "groups": len(frame[GROUP].drop_duplicates()),
                                        "meetings": int(frame["meeting_id"].nunique()), "companies": int(frame["company_id"].nunique())}
                        for name, frame in (("fit", train), ("development", development))}
    dev = development[KEY + GROUP + ["company", "proposal_text", "nbim_vote", "mgmt_rec"]].copy()
    dev["variant"], dev["score"], dev["threshold"] = chosen, scores, threshold
    dev["predicted_mot"] = scores >= threshold
    dev["error"] = np.select([dev["predicted_mot"] & dev["nbim_vote"].ne("MOT"), ~dev["predicted_mot"] & dev["nbim_vote"].eq("MOT")], ["FP", "FN"], "")
    summary["development_errors"] = dict(Counter(dev.loc[dev["error"].ne(""), "error"]))
    output.mkdir(parents=True)
    pd.concat(oof_records, ignore_index=True).to_csv(output / "oof.csv", index=False)
    dev.to_csv(output / "development.csv", index=False)
    train[KEY + GROUP].to_csv(output / "fit-keys.csv", index=False)
    development[KEY + GROUP].to_csv(output / "development-keys.csv", index=False)
    pd.concat([pd.DataFrame({"meeting_id": train.iloc[check]["meeting_id"], "item_no": train.iloc[check]["item_no"], "fold": i})
               for i, (_, check) in enumerate(folds)], ignore_index=True).to_csv(output / "fold-assignments.csv", index=False)
    joblib.dump({"variant": chosen, "components": selected_model.__dict__, "threshold": threshold,
                 "provenance": provenance}, output / "screen.joblib")
    summary["artifacts"] = {path.name: file_hash(path) for path in output.iterdir() if path.is_file()}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(output.resolve()), "selected": chosen, "oof": summary["configurations"][chosen]["oof"],
                      "development": summary["development_selected"], "follow_board": summary["development_follow_board"], "sizes": summary["sizes"]}, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--split", type=Path, default=SPLIT)
    args = parser.parse_args()
    run(args.output, args.split)
