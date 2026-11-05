"""Prepare a mixed-year 80/20 experiment from the pooled NBIM vote source."""
import boot  # noqa: F401
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import random
import tempfile

import pandas as pd


ROOT = Path(__file__).parent
SOURCE = ROOT / "data" / "real_votes.csv"
OUTPUT = ROOT / "data" / "mixed-80-20"
GROUP = ["company_id", "meeting_date"]
KEY = ["meeting_id", "item_no"]
REQUIRED = {
    *GROUP, *KEY, "company", "country", "market", "proposal_text", "proponent",
    "mgmt_rec", "nbim_vote", "proposal_type", "rationale_section", "injection_flag",
}


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def split_source(source=SOURCE, seed=2026):
    """Shuffle company/date groups within year and presence-of-MOT strata."""
    votes = pd.read_csv(source, dtype=str, keep_default_na=False)
    missing = REQUIRED - set(votes.columns)
    if missing:
        raise ValueError(f"Missing source columns: {', '.join(sorted(missing))}")
    if votes.empty or votes[KEY + GROUP].eq("").any().any():
        raise ValueError("Source must contain rows with meeting, item, company and date identifiers")
    if votes.duplicated(KEY).any():
        raise ValueError("Duplicate meeting_id/item_no keys in source")
    if votes.groupby("meeting_id")[GROUP].nunique().gt(1).any().any():
        raise ValueError("A meeting_id maps to more than one company or date")
    if not votes["injection_flag"].eq("0").all():
        raise ValueError("Injected or unclassified source rows need a separate resistance dataset")
    for column in ("mgmt_rec", "nbim_vote"):
        if not votes[column].isin(["", "FOR", "MOT", "AVSTÅ"]).all():
            raise ValueError(f"Unsupported normalized vote in {column}")
    years = pd.to_datetime(votes["meeting_date"], format="%Y-%m-%d", errors="raise").dt.year
    if "year" in votes and not votes["year"].eq(years.astype(str)).all():
        raise ValueError("Source year disagrees with meeting_date")
    if not votes["meeting_date"].eq(pd.to_datetime(votes["meeting_date"]).dt.strftime("%Y-%m-%d")).all():
        raise ValueError("Dates must use YYYY-MM-DD")

    groups = votes.assign(split_year=years, has_mot=votes["nbim_vote"].eq("MOT")).groupby(
        GROUP, sort=True
    ).agg(split_year=("split_year", "first"), has_mot=("has_mot", "any"))
    randomizer = random.Random(seed)
    test_groups = set()
    for stratum, bucket in groups.groupby(["split_year", "has_mot"], sort=True):
        keys = list(bucket.index)
        if len(keys) < 2:
            raise ValueError(f"Need at least two company/date groups in year/MOT stratum {stratum}")
        randomizer.shuffle(keys)
        test_count = max(1, min(len(keys) - 1, round(len(keys) * 0.20)))
        test_groups.update(keys[:test_count])

    votes["split"] = ["test" if key in test_groups else "train" for key in votes[GROUP].itertuples(index=False, name=None)]
    votes = votes.sort_values(["meeting_date", "company_id", *KEY], kind="stable")
    return {name: votes.loc[votes["split"].eq(name)].reset_index(drop=True) for name in ("train", "test")}


def counts(votes):
    """Report the rows retained, including those without a usable target label."""
    known = votes["nbim_vote"].ne("") & votes["mgmt_rec"].ne("")
    return {
        "rows": len(votes),
        "meetings": int(votes["meeting_id"].nunique()),
        "company_date_groups": len(votes[GROUP].drop_duplicates()),
        "known_votes": int(votes["nbim_vote"].ne("").sum()),
        "mot_votes": int(votes["nbim_vote"].eq("MOT").sum()),
        "scored_against_board": int(known.sum()),
        "against_board": int((known & votes["nbim_vote"].ne(votes["mgmt_rec"])).sum()),
    }


def load_split(output=OUTPUT):
    """Load assigned train/test frames with the derived fields used by Voting Desk.

    Pass the returned training frame as the record for BOTH precedent features
    and Claude prompts. The test frame holds evaluation labels only.
    """
    import desk

    output = Path(output).resolve()
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    source = output / manifest["source"]["path"]
    if digest(source) != manifest["source"]["sha256"]:
        raise ValueError("Source changed after dataset preparation")
    frames = {}
    for name in ("train", "test"):
        path = output / f"{name}.csv"
        if digest(path) != manifest["files"][f"{name}.csv"]:
            raise ValueError(f"{name}.csv hash does not match the manifest")
        raw = pd.read_csv(path, dtype=str, keep_default_na=False)
        if not raw["split"].eq(name).all() or counts(raw) != manifest["splits"][name]:
            raise ValueError(f"Invalid {name} partition")
        # The frozen loader derives time-based splits. Apply the saved assignment last.
        frames[name] = desk.load_votes(path).assign(split=name)
    train_groups = set(frames["train"][GROUP].itertuples(index=False, name=None))
    test_groups = set(frames["test"][GROUP].itertuples(index=False, name=None))
    if train_groups & test_groups:
        raise ValueError("Company/date groups overlap between train and test")
    keys = pd.concat([frame[KEY] for frame in frames.values()], ignore_index=True)
    source_keys = pd.read_csv(source, dtype=str, keep_default_na=False, usecols=KEY)
    if keys.duplicated().any() or set(keys.itertuples(index=False, name=None)) != set(source_keys[KEY].itertuples(index=False, name=None)):
        raise ValueError("Partitions do not cover the source exactly once")
    return frames


def build_dataset(source=SOURCE, output=OUTPUT, seed=2026):
    """Write a complete dataset atomically; reject replacement by a different split."""
    source, output = Path(source).resolve(), Path(output).resolve()
    if source.is_relative_to(output):
        raise ValueError("Output directory must be separate from the source")
    source_hash = digest(source)
    frames = split_source(source, seed)
    if digest(source) != source_hash:
        raise ValueError("Source changed while preparing the dataset")
    settings = {"version": 1, "source_sha256": source_hash, "seed": seed, "test_fraction": 0.20}
    dataset_id = sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:16]
    manifest = {
        **settings,
        "dataset_id": dataset_id,
        "evaluation_kind": "MIXED_YEAR_EXPLORATORY",
        "model_evaluated": False,
        "source": {"path": os.path.relpath(source, output), "sha256": source_hash},
        "observation_key": KEY,
        "group_by": GROUP,
        "stratify_by": ["meeting_year", "group_contains_mot"],
        "history_record": "training rows only, retaining the five-day as-of cutoff",
        "prior_exposure": "Source rows have been used in previous training, validation and testing",
        "interpretation": "Mixed-year interpolation; does not estimate performance on later years",
        "splits": {name: counts(frame) for name, frame in frames.items()},
        "by_year": {
            name: {year: counts(group) for year, group in frame.groupby(frame["meeting_date"].str[:4])}
            for name, frame in frames.items()
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".mixed-split-", dir=output.parent) as temporary:
        staged = Path(temporary) / "dataset"
        staged.mkdir()
        for name, frame in frames.items():
            frame.to_csv(staged / f"{name}.csv", index=False, lineterminator="\n")
        manifest["files"] = {f"{name}.csv": digest(staged / f"{name}.csv") for name in frames}
        (staged / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            staged.rename(output)
        except OSError:
            if not output.is_dir():
                raise
            try:
                saved = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise ValueError("Output directory already exists without a valid dataset manifest; choose a new --output") from error
            if saved != manifest:
                raise ValueError("Output already contains a different dataset; choose a new --output") from None
    load_split(output)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(argv)
    try:
        manifest = build_dataset(args.source, args.output, args.seed)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Cannot prepare dataset: {error}\n")
    total = sum(part["rows"] for part in manifest["splits"].values())
    print(f"Dataset {manifest['dataset_id']} — mixed-year exploratory split")
    for name, part in manifest["splits"].items():
        print(f"{name}: {part['rows']} rows ({part['rows'] / total:.2%}), {part['meetings']} meetings, {part['mot_votes']} MOT")
    print(f"Saved to {args.output.resolve()}")
    print("Model evaluation pending. Historical metrics describe the original time-based split.")


if __name__ == "__main__":
    main()
