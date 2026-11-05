"""Local, chronological kNN vote decisions over externally supplied BGE embeddings.

This module does not embed text, download models or call an API. Its score is the
weighted share of historical MOT votes, not a calibrated confidence probability.
The caller supplies only its permitted training/fold reference rows to ``fit``.
"""
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd

MODEL = "BAAI/bge-small-en-v1.5"
DIMENSION = 384
TEMPERATURE = 0.10
KEY = ["meeting_id", "item_no"]
GROUP = ["company_id", "meeting_date"]
INPUT_FIELDS = ["proposal_text", "mgmt_rec", "proponent"]
META_FIELDS = [*KEY, *GROUP, "company", *INPUT_FIELDS]
VOTES = ("FOR", "MOT", "AVSTÅ")
FILES = ("metadata.json", "labels.json", "embeddings.npy")


def _text(value):
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    if not isinstance(value, str):
        raise ValueError("Metadata text fields must contain strings or missing values")
    return value.strip()


def input_text(row):
    """Embedding input has no company, vote, rationale or label-derived category."""
    return "\n".join(f"{key}: {_text(row.get(key))}" for key in INPUT_FIELDS)


def _metadata(frame):
    if not isinstance(frame, pd.DataFrame) or not set(META_FIELDS).issubset(frame.columns):
        raise ValueError("Frame is missing required reference/query metadata columns")
    if frame.columns.duplicated().any():
        raise ValueError("Frame has duplicate columns")
    meta = frame[META_FIELDS].copy().reset_index(drop=True)
    for name in META_FIELDS:
        if name != "meeting_date":
            meta[name] = meta[name].map(_text)
    if meta[KEY + ["company_id"]].eq("").any().any():
        raise ValueError("Proposal and company identities must be nonempty")
    try:
        dates = pd.to_datetime(meta["meeting_date"], format="%Y-%m-%d", errors="raise")
        if dates.isna().any() or dates.dt.tz is not None:
            raise ValueError("Meeting dates must be known timezone-free dates")
        meta["meeting_date"] = dates.dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("Meeting dates must be known timezone-free dates") from error
    if meta.duplicated(KEY).any():
        raise ValueError("Duplicate proposal identities")
    return meta


def _vectors(embeddings, rows):
    try:
        values = np.asarray(embeddings, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError("Embeddings must be a numeric matrix") from error
    if values.shape != (rows, DIMENSION) or not np.isfinite(values).all():
        raise ValueError(f"Embeddings must be a finite ({rows}, {DIMENSION}) matrix")
    # Scaling first avoids overflow in the norm for large but finite input values.
    scales = np.max(np.abs(values), axis=1, keepdims=True)
    if (scales == 0).any():
        raise ValueError("Embedding vectors must have nonzero length")
    values = values / scales
    return (values / np.linalg.norm(values, axis=1, keepdims=True)).astype(np.float32)


def _hash(path):
    return sha256(Path(path).read_bytes()).hexdigest()


class VectorVoteModel:
    """Cosine top-k with strictly earlier training history and label-blind weights.

    Exact cosine ties prefer the same company, then the most recent eligible date,
    then (meeting_id, item_no). No similarity rounding or labels enter this ranking.
    """

    def fit(self, frame, embeddings):
        meta = _metadata(frame)
        if meta.empty or "nbim_vote" not in frame:
            raise ValueError("Fit requires nonempty references with known NBIM votes")
        labels = frame["nbim_vote"].reset_index(drop=True)
        if not labels.isin(VOTES).all():
            raise ValueError("Reference votes must be known FOR, MOT or AVSTÅ; exclude unknown rows explicitly")
        vectors = _vectors(embeddings, len(meta))
        # Stable canonical ordering makes exact cosine ties independent of input order.
        order = meta.sort_values(KEY, kind="stable").index.to_numpy()
        self.metadata = meta.iloc[order].reset_index(drop=True)
        self.labels = labels.iloc[order].to_numpy(dtype=str)
        self.embeddings = vectors[order]
        self.dates = self.metadata["meeting_date"].to_numpy(dtype="datetime64[D]")
        self.date_days = self.dates.astype(np.int64)
        return self

    def _check_fitted(self):
        if not hasattr(self, "embeddings"):
            raise ValueError("Fit or load the model before use")

    def predict(self, frame, embeddings, k=32, company_weight=1.0, neighbor_limit=5):
        self._check_fitted()
        if isinstance(k, bool) or not isinstance(k, (int, np.integer)) or k < 1:
            raise ValueError("k must be a positive integer")
        if isinstance(neighbor_limit, bool) or not isinstance(neighbor_limit, (int, np.integer)) or neighbor_limit < 0:
            raise ValueError("neighbor_limit must be a nonnegative integer")
        if isinstance(company_weight, bool) or not np.isscalar(company_weight):
            raise ValueError("company_weight must be a positive finite number")
        try:
            company_weight = float(company_weight)
        except (ValueError, TypeError) as error:
            raise ValueError("company_weight must be a positive finite number") from error
        if not np.isfinite(company_weight) or company_weight <= 0:
            raise ValueError("company_weight must be a positive finite number")
        query = _metadata(frame)
        vectors = _vectors(embeddings, len(query))
        records = self.metadata.to_dict("records")
        reference_meetings = self.metadata["meeting_id"].to_numpy()
        reference_companies = self.metadata["company_id"].to_numpy()
        results = []
        for start in range(0, len(query), 256):
            similarities = np.clip(vectors[start:start + 256] @ self.embeddings.T, -1.0, 1.0)
            for offset, row in enumerate(query.iloc[start:start + 256].to_dict("records")):
                day = np.datetime64(row["meeting_date"], "D")
                same_company = reference_companies == row["company_id"]
                eligible = ((self.dates < day - np.timedelta64(5, "D"))
                            & (reference_meetings != row["meeting_id"])
                            & ~(same_company & (self.dates == day)))
                candidates = np.flatnonzero(eligible)
                scores = similarities[offset]
                order = np.lexsort((candidates, -self.date_days[candidates], ~same_company[candidates], -scores[candidates]))
                selected = candidates[order[:k]]
                weights = np.exp((scores[selected].astype(np.float64) - 1.0) / TEMPERATURE)
                weights[same_company[selected]] *= company_weight
                weights = np.maximum(weights, np.finfo(np.float64).tiny)
                neighbors = []
                for index, weight in zip(selected[:neighbor_limit], weights[:neighbor_limit]):
                    neighbors.append({**{name: records[index][name] for name in
                                         ("meeting_id", "item_no", "company", "meeting_date", "proposal_text")},
                                      "nbim_vote": str(self.labels[index]),
                                      "similarity": float(scores[index]), "weight": float(weight)})
                # Scale by the largest weight to avoid overflow with large company weights.
                if len(weights):
                    weights /= weights.max()
                    score = float(np.sum(weights * (self.labels[selected] == "MOT")) / weights.sum())
                else:
                    score = None
                counts = {vote: int(np.sum(self.labels[selected] == vote)) for vote in VOTES}
                results.append({"score": score, "history_count": int(len(candidates)),
                                "neighbor_count": len(selected), "neighbor_vote_counts": counts,
                                "conflicting_votes": sum(value > 0 for value in counts.values()) > 1,
                                "neighbors": neighbors})
        return results

    def save(self, path):
        """Write a new directory; an incomplete artifact has no valid manifest."""
        self._check_fitted()
        path = Path(path)
        path.mkdir(parents=True, exist_ok=False)
        (path / "metadata.json").write_text(json.dumps(self.metadata.to_dict("records"), ensure_ascii=False) + "\n")
        (path / "labels.json").write_text(json.dumps(self.labels.tolist(), ensure_ascii=False) + "\n")
        np.save(path / "embeddings.npy", self.embeddings, allow_pickle=False)
        manifest = {"version": 1, "embedding_model": MODEL, "dimension": DIMENSION,
                    "rows": len(self.metadata), "temperature": TEMPERATURE, "input_fields": INPUT_FIELDS,
                    "tie_policy": "same_company_then_date_desc_then_meeting_item",
                    "metadata_fields": META_FIELDS, "files": {name: _hash(path / name) for name in FILES}}
        (path / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        return manifest

    @classmethod
    def load(cls, path):
        path = Path(path)
        manifest = json.loads((path / "manifest.json").read_text())
        expected = {"version": 1, "embedding_model": MODEL, "dimension": DIMENSION,
                    "tie_policy": "same_company_then_date_desc_then_meeting_item",
                    "temperature": TEMPERATURE, "input_fields": INPUT_FIELDS, "metadata_fields": META_FIELDS}
        if any(manifest.get(key) != value for key, value in expected.items()) or set(manifest.get("files", {})) != set(FILES):
            raise ValueError("Unsupported vector model artifact configuration")
        if any(_hash(path / name) != manifest["files"][name] for name in FILES):
            raise ValueError("Vector model metadata, labels or embeddings do not match the manifest")
        rows = json.loads((path / "metadata.json").read_text())
        if any(set(row) != set(META_FIELDS) for row in rows):
            raise ValueError("Artifact contains unexpected metadata fields")
        metadata = pd.DataFrame(rows, columns=META_FIELDS)
        labels = json.loads((path / "labels.json").read_text())
        if len(metadata) != manifest["rows"] or len(labels) != len(metadata):
            raise ValueError("Artifact row counts differ")
        metadata["nbim_vote"] = labels
        embeddings = np.load(path / "embeddings.npy", allow_pickle=False)
        model = cls().fit(metadata, embeddings)
        # Preserve exact stored cosine inputs after validating shape, values and norms.
        if not np.allclose(np.linalg.norm(embeddings, axis=1), 1.0, rtol=1e-6, atol=1e-6):
            raise ValueError("Saved embeddings are not unit vectors")
        order = metadata.sort_values(KEY, kind="stable").index.to_numpy()
        model.embeddings = embeddings[order].astype(np.float32)
        return model
