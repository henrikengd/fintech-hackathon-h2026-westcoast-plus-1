"""Small supervised classifiers on historical vector features; no API calls."""
import numpy as np
from scipy import sparse
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from vector_model import input_text
from vote_features import FEATURE_NAMES, feature_names
from vote_targets import target_labels, validate_target


CONFIGS = (
    [{"name": f"history-logistic-{c}", "kind": "logistic", "input": "history", "C": c} for c in (0.1, 1.0)]
    + [{"name": f"history-boost-{leaves}-{weight or 'plain'}", "kind": "boost", "input": "history",
        "leaves": leaves, "class_weight": weight} for leaves in (7, 15) for weight in (None, "balanced")]
    + [{"name": f"history-forest-{leaf}", "kind": "forest", "input": "history", "min_leaf": leaf} for leaf in (2, 10)]
    + [{"name": f"text-history-{c}", "kind": "logistic", "input": "text", "C": c} for c in (0.3, 3.0)]
    + [{"name": "semantic-history-boost", "kind": "boost", "input": "semantic", "leaves": 15, "class_weight": None},
       {"name": "semantic-history-logistic", "kind": "logistic", "input": "semantic", "C": 1.0}]
)


def texts(frame):
    # Identity is available before voting. No supplied categories, labels or rationales.
    return [input_text(row) + "\ncompany: " + str(row["company"])
            for row in frame.to_dict("records")]


def bounded_history(history):
    """Fixed saturation prevents growth of the archive from extrapolating indefinitely."""
    result = np.array(history, dtype=float, copy=True)
    if result.ndim != 2 or result.shape[1] != len(FEATURE_NAMES):
        raise ValueError("Expected the declared historical feature columns")
    for index, name in enumerate(FEATURE_NAMES):
        if name.endswith("count_log") or name.endswith("meetings_log"):
            result[:, index] = np.minimum(result[:, index], np.log1p(50))
        elif name.endswith("age_years"):
            result[:, index] = np.minimum(result[:, index], 3.0)
    return result


def fit(config, frame, history, embeddings, target="mot"):
    y = target_labels(frame, target)
    if len(np.unique(y)) != 2:
        raise ValueError("Training requires both positive and negative examples for the chosen target")
    state = {"config": dict(config), "history_transform": "capped-counts-50-ages-3-v1",
             "target": target, "feature_names": feature_names(target)}
    state["numeric"] = make_pipeline(SimpleImputer(strategy="constant", fill_value=0, add_indicator=True,
                                                   keep_empty_features=True), StandardScaler())
    numeric = state["numeric"].fit_transform(bounded_history(history))
    if config["input"] == "semantic":
        numeric = np.column_stack([numeric, embeddings])
    if config["input"] == "text":
        state["word"] = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=20000, sublinear_tf=True)
        state["char"] = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3,
                                         max_features=30000, sublinear_tf=True)
        documents = texts(frame)
        numeric = sparse.hstack([sparse.csr_matrix(numeric), state["word"].fit_transform(documents),
                                 state["char"].fit_transform(documents)], format="csr")
    if config["kind"] == "logistic":
        model = LogisticRegression(C=config["C"], class_weight="balanced", solver="liblinear",
                                   max_iter=1500, random_state=41)
    elif config["kind"] == "boost":
        model = HistGradientBoostingClassifier(max_iter=180, learning_rate=.05, max_leaf_nodes=config["leaves"],
                                               min_samples_leaf=20, l2_regularization=1.0,
                                               class_weight=config["class_weight"], early_stopping=False, random_state=41)
    elif config["kind"] == "forest":
        model = ExtraTreesClassifier(n_estimators=300, min_samples_leaf=config["min_leaf"],
                                     class_weight="balanced", max_features=.8, n_jobs=2, random_state=41)
    else:
        raise ValueError("Unknown learner")
    state["model"] = model.fit(numeric, y)
    return state


def predict(state, frame, history, embeddings):
    # Legacy saved learners omitted this key and always used literal MOT.
    validate_target(state.get("target", "mot"))
    transform = state.get("history_transform", "identity")
    if transform not in ("identity", "capped-counts-50-ages-3-v1"):
        raise ValueError("Unknown historical preprocessing version")
    numeric = state["numeric"].transform(bounded_history(history) if transform != "identity" else history)
    if state["config"]["input"] == "semantic":
        numeric = np.column_stack([numeric, embeddings])
    if state["config"]["input"] == "text":
        documents = texts(frame)
        numeric = sparse.hstack([sparse.csr_matrix(numeric), state["word"].transform(documents),
                                 state["char"].transform(documents)], format="csr")
    return state["model"].predict_proba(numeric)[:, 1]
