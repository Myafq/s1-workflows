from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .assessment import DecisionAssessmentModel
from .clef import ClefClient
from .contracts import AssessmentInput, AssessmentModel, DecisionModelError
from .jev import JevClient
from .runner import AssessmentRunner


DEFAULT_CHUNK_BYTES = 48_000
DEFAULT_MAX_BYTES = 10_000_000


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fast structured risk assessment for a pull request or diff."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Diff file or JSON input file; '-' reads stdin (default)",
    )
    parser.add_argument(
        "--json-input",
        action="store_true",
        help="Parse input as an AssessmentInput JSON object instead of a raw diff",
    )
    parser.add_argument(
        "--git-range",
        help="Read a local git diff for a revision range, e.g. origin/main...HEAD",
    )
    parser.add_argument("--title", help="Pull-request title")
    parser.add_argument("--description", help="Pull-request description")
    parser.add_argument("--repository", help="Repository identifier")
    parser.add_argument("--base", dest="base_revision", help="Base revision")
    parser.add_argument("--head", dest="head_revision", help="Head revision")
    parser.add_argument(
        "--provider",
        choices=("typesafe", "cloudflare"),
        default="typesafe",
        help="Decision-model provider (default: typesafe)",
    )
    parser.add_argument(
        "--model",
        help="Model name (default: jev-latest, or clef for Cloudflare)",
    )
    parser.add_argument(
        "--boolean-threshold",
        type=float,
        default=0.5,
        help="Probability threshold for Boolean decisions (default: 0.5)",
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--chunk-bytes",
        type=int,
        default=DEFAULT_CHUNK_BYTES,
        help="Initial maximum bytes per model call (default: 48000)",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help="Maximum total diff bytes accepted (default: 10000000)",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    model_factory: Callable[[argparse.Namespace], AssessmentModel] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    if not 0 <= args.boolean_threshold <= 1:
        print("error: --boolean-threshold must be between 0 and 1", file=sys.stderr)
        return 2
    if args.max_bytes <= 0:
        print("error: --max-bytes must be positive", file=sys.stderr)
        return 2
    if args.chunk_bytes < 1024:
        print("error: --chunk-bytes must be at least 1024", file=sys.stderr)
        return 2
    if args.git_range and (args.input != "-" or args.json_input):
        print(
            "error: --git-range cannot be combined with an input file or --json-input",
            file=sys.stderr,
        )
        return 2

    try:
        assessment = _load_input(args)
        serialized_bytes = len(assessment.diff.encode("utf-8"))
        if serialized_bytes > args.max_bytes:
            raise ValueError(
                f"diff is {serialized_bytes} bytes; limit is {args.max_bytes} "
                "(change --max-bytes to override)"
            )
        model = model_factory(args) if model_factory else _assessment_model(args)
        result = AssessmentRunner(model, chunk_bytes=args.chunk_bytes).assess(assessment)
        print(
            json.dumps(
                result.to_dict(),
                indent=2 if args.pretty else None,
                sort_keys=args.pretty,
            )
        )
        return 0
    except (
        DecisionModelError,
        OSError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _assessment_model(args: argparse.Namespace) -> DecisionAssessmentModel:
    if args.provider == "cloudflare":
        return _clef_model(args)
    return _jev_model(args)


def _jev_model(args: argparse.Namespace) -> DecisionAssessmentModel:
    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        raise ValueError("TYPESAFE_API_KEY is not set")
    client = JevClient(
        api_key,
        base_url=os.environ.get("TYPESAFE_BASE_URL", "https://api.typesafe.ai"),
        timeout=args.timeout,
    )
    return DecisionAssessmentModel(
        client,
        model=args.model or "jev-latest",
        provider="typesafe",
        boolean_threshold=args.boolean_threshold,
    )


def _clef_model(args: argparse.Namespace) -> DecisionAssessmentModel:
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN") or os.environ.get(
        "CLOUDFLARE_AUTH_TOKEN"
    )
    if not api_token:
        raise ValueError(
            "CLOUDFLARE_API_TOKEN or CLOUDFLARE_AUTH_TOKEN is not set"
        )
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not account_id:
        raise ValueError("CLOUDFLARE_ACCOUNT_ID is not set")
    client = ClefClient(
        api_token,
        account_id,
        base_url=os.environ.get(
            "CLOUDFLARE_BASE_URL", "https://api.cloudflare.com/client/v4"
        ),
        timeout=args.timeout,
    )
    return DecisionAssessmentModel(
        client,
        model=args.model or "clef",
        provider="cloudflare",
        boolean_threshold=args.boolean_threshold,
    )


def _load_input(args: argparse.Namespace) -> AssessmentInput:
    if args.git_range:
        completed = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--no-color", args.git_range],
            check=True,
            capture_output=True,
            text=True,
        )
        diff = completed.stdout
    else:
        raw = (
            sys.stdin.read()
            if args.input == "-"
            else Path(args.input).read_text(encoding="utf-8")
        )
        if args.json_input:
            decoded = json.loads(raw)
            if not isinstance(decoded, dict):
                raise ValueError("JSON input must be an object")
            assessment = AssessmentInput.from_dict(decoded)
            return _with_cli_metadata(assessment, args)
        diff = raw

    return AssessmentInput(
        diff=diff,
        title=args.title,
        description=args.description,
        repository=args.repository,
        base_revision=args.base_revision,
        head_revision=args.head_revision,
    )


def _with_cli_metadata(value: AssessmentInput, args: argparse.Namespace) -> AssessmentInput:
    return AssessmentInput(
        diff=value.diff,
        title=args.title if args.title is not None else value.title,
        description=(
            args.description if args.description is not None else value.description
        ),
        repository=args.repository if args.repository is not None else value.repository,
        base_revision=(
            args.base_revision
            if args.base_revision is not None
            else value.base_revision
        ),
        head_revision=(
            args.head_revision
            if args.head_revision is not None
            else value.head_revision
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
