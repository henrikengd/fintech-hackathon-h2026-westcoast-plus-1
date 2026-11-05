"""Install the shared experiment snapshot and replay its saved inputs."""
import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import tempfile
from zipfile import ZipFile

from model_setups import CLAUDE, LOCAL


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data/local-rag"
KIT = ROOT / "model-kit"


def install():
    manifest = json.loads((KIT / "manifest.json").read_text(encoding="utf-8"))
    files = manifest["files"]
    archive = KIT / "experiments-v1.zip"
    if sha256(archive.read_bytes()).hexdigest() != manifest["archive_sha256"]:
        raise ValueError("Model kit archive checksum differs from its manifest")
    DATA.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive) as bundle, tempfile.TemporaryDirectory(dir=DATA) as staging:
        if len(bundle.namelist()) != len(files) or set(bundle.namelist()) != files.keys():
            raise ValueError("Archive entries differ from the model kit manifest")
        pending = []
        for name, expected in files.items():
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or "\\" in name:
                raise ValueError(f"Unsafe artifact path: {name}")
            target = DATA.joinpath(*relative.parts)
            if not target.resolve().is_relative_to(DATA.resolve()):
                raise ValueError(f"Artifact path leaves the destination: {name}")
            content = bundle.read(name)
            if sha256(content).hexdigest() != expected:
                raise ValueError(f"Artifact checksum differs: {name}")
            if target.exists():
                if not target.is_file() or sha256(target.read_bytes()).hexdigest() != expected:
                    raise ValueError(f"Existing artifact differs: {target}. Use a fresh clone.")
                continue
            temporary = Path(staging) / str(len(pending))
            temporary.write_bytes(content)
            pending.append((temporary, target))
        for temporary, target in pending:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Publish complete files exclusively. A concurrent install can be retried.
            target.hardlink_to(temporary)
    return {"installed": len(pending), "verified": len(files)}


def replay_local(meeting, item, setup=None):
    import joblib
    import numpy as np

    import f1_experiment
    import relevance_experiment as experiment

    output = experiment.OUTPUT
    summary = f1_experiment.read_json(output / "summary.json")
    if summary["record_id"] != experiment.fingerprint({k: v for k, v in summary.items() if k != "record_id"}):
        raise ValueError("Experiment summary changed")

    def verified(name):
        return f1_experiment.checked_path(output, name, summary["artifacts"][name])

    predictions = f1_experiment.read_predictions(verified("calibration.csv"))
    selected = np.flatnonzero(predictions.meeting_id.eq(meeting) & predictions.item_no.eq(item))
    if len(selected) != 1:
        raise ValueError("Select one of the saved 2024 proposals")
    names = f1_experiment.read_json(verified("feature_names.json"))["retrieval"]
    results = []
    with np.load(verified("calibration-inputs.npz"), allow_pickle=False) as inputs:
        history, retrieval, vectors = (inputs[name][selected] for name in ("history", "retrieval", "vectors"))
        for comparison in summary["comparisons"]:
            config = comparison["config"]
            name = config["name"]
            setup_id, setup_name = LOCAL[name]
            if setup is not None and setup_id != setup:
                continue
            threshold = comparison["calibration"]["threshold"]
            if config["kind"] == "baseline":
                baseline = f1_experiment.predict(f1_experiment.OUTPUT, meeting, item)
                score = baseline["score"]
            else:
                state = joblib.load(verified(f"{name}.joblib"))
                score = float(experiment.predict_scores(state, history, retrieval, vectors, names)[0])
            results.append({"setup_id": setup_id, "setup_name": setup_name,
                            "model": name, "score": score, "threshold": threshold,
                            "prediction": "DISAGREE" if score >= threshold else "WITH_BOARD"})
    if not results:
        raise ValueError(f"Setup {setup} is missing from the installed comparison")
    return {"meeting_id": meeting, "item_no": item, "api_calls": 0, "variants": results}


def claude_meeting(variant, meeting):
    import anthropic
    import relevance_claude as experiment

    output = experiment.OUTPUT
    plan = experiment.load_plan(output, current=True)
    key = f"{variant}__{meeting}"
    if key not in plan["requests"]:
        raise ValueError("This meeting and variant are not in the frozen plan")
    bundle = experiment.read(output / "bundles" / f"{key}.json")
    with anthropic.Anthropic(max_retries=0, timeout=180.0) as client:
        return experiment.generate(bundle, plan["settings"], client)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("install", help="Verify and install the versioned snapshot")
    replay = subcommands.add_parser("replay", help="Replay one or all local variants for a saved proposal")
    replay.add_argument("--meeting", required=True)
    replay.add_argument("--item", required=True)
    replay.add_argument("--setup", choices=[setup_id for setup_id, _ in LOCAL.values()])
    claude = subcommands.add_parser("claude", help="Make one paid request for a frozen meeting")
    claude.add_argument("--meeting", required=True)
    live_setups = {CLAUDE[variant][0]: variant for variant in ("hybrid_history", "hybrid_evidence")}
    claude_choice = claude.add_mutually_exclusive_group(required=True)
    claude_choice.add_argument("--setup", choices=live_setups)
    claude_choice.add_argument("--variant", choices=live_setups.values())
    args = parser.parse_args()
    try:
        if args.command == "install":
            result = install()
        else:
            import boot  # noqa: F401

            if args.command == "replay":
                result = replay_local(args.meeting, args.item, args.setup)
            else:
                variant = live_setups[args.setup] if args.setup else args.variant
                setup_id, setup_name = CLAUDE[variant]
                result = {"setup_id": setup_id, "setup_name": setup_name,
                          **claude_meeting(variant, args.meeting)}
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
