"""Command line entry point for indexing, serving and evaluation."""

import argparse
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from importlib import import_module
from os import getenv
from pathlib import Path
import sys

from dotenv import load_dotenv


class CliError(ValueError):
    """An error whose message is safe to display to the user."""


_HANDLERS = {
    "serve": ("mcp_server", "serve"),
    "index": ("retrieval", "build_index"),
    "evaluate": ("evaluation", "evaluate"),
}


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("port must be an integer") from None
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def _budget(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError("budget must be a decimal number in USD") from None
    if not amount.is_finite() or not 0 <= amount <= 204:
        raise argparse.ArgumentTypeError("budget must be between 0 and 204 USD")
    return amount


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m voting_assistant",
        description="Source-backed voting assistance for shareholder meetings",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    index_path = Path(getenv("VOTING_INDEX_PATH") or "data/index.json")

    serve = commands.add_parser("serve", help="serve policy search over MCP")
    serve.add_argument("--index", type=Path, default=index_path)
    serve.add_argument("--host", default=getenv("MCP_HOST") or "127.0.0.1")
    serve.add_argument("--port", type=_port, default=getenv("MCP_PORT") or "8000")

    index = commands.add_parser("index", help="build a policy index from a manifest")
    index.add_argument("--manifest", required=True, type=Path)
    index.add_argument("--output", type=Path, default=index_path)

    evaluate = commands.add_parser("evaluate", help="assess and score a meeting set")
    evaluate.add_argument("--manifest", required=True, type=Path)
    evaluate.add_argument("--output", required=True, type=Path)
    evaluate.add_argument("--max-cost-usd", required=True, type=_budget)
    evaluate.add_argument("--index", type=Path, default=index_path)
    evaluate.add_argument("--resume", action="store_true", help="reuse compatible completed work")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv(Path.cwd() / ".env", override=False)
    args = build_parser().parse_args(argv)
    module_name, handler_name = _HANDLERS[args.command]
    path = f"voting_assistant.{module_name}"
    try:
        module = import_module(path)
    except ModuleNotFoundError as error:
        if error.name != path:
            raise
        print(f"{args.command}: command is not implemented yet", file=sys.stderr)
        return 1
    try:
        result = getattr(module, handler_name)(args)
    except CliError as error:
        print(f"{args.command}: {error}", file=sys.stderr)
        return 1
    return 0 if result is None else result
