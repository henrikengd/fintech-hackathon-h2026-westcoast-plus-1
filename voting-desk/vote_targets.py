"""Explicit binary voting targets without fabricating or overwriting actual votes.

``mot`` means NBIM voted MOT. ``against_board`` means NBIM's known vote differs
from the board's known recommendation, including differences involving AVSTÅ.
Missing or unrecognized votes never become positive examples through inequality.
"""
import pandas as pd

VOTES = ("FOR", "MOT", "AVSTÅ")
TARGETS = ("mot", "against_board")


def validate_target(target):
    if target not in TARGETS:
        raise ValueError("Target must be 'mot' or 'against_board'")
    return target


def known_target(frame, target="mot"):
    """Index-aligned eligibility mask; missing required columns are a schema error."""
    validate_target(target)
    required = ["nbim_vote"] + (["mgmt_rec"] if target == "against_board" else [])
    if not isinstance(frame, pd.DataFrame) or not set(required).issubset(frame.columns):
        raise ValueError("Target data is missing required vote columns")
    if frame.columns.duplicated().any():
        raise ValueError("Target data has duplicate columns")
    known = frame["nbim_vote"].isin(VOTES)
    if target == "against_board":
        known = known & frame["mgmt_rec"].isin(VOTES)
    return known.astype(bool)


def target_labels(frame, target="mot"):
    """Return boolean labels; the caller must explicitly exclude unknown rows first."""
    if not known_target(frame, target).all():
        raise ValueError("Target labels require known votes; filter with known_target first")
    labels = frame["nbim_vote"].eq("MOT") if target == "mot" else frame["nbim_vote"].ne(frame["mgmt_rec"])
    return labels.to_numpy(dtype=bool)
