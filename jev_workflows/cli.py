from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .assessment import JevAssessmentModel
from .contracts import AssessmentInput, AssessmentModel
from .jev import JevClient, JevError


DEFAULT_MAX_BYTES = 1_000_000


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
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument(
        "--boolean-threshold",
        type=float,
        default=0.5,
        help="Probability threshold for Boolean decisions (default: 0.5)",
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
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
        model = model_factory(args) if model_factory else _jev_model(args)
        result = model.assess(assessment)
        print(
            json.dumps(
                result.to_dict(),
                indent=2 if args.pretty else None,
                sort_keys=args.pretty,
            )
        )
        return 0
    except (
        JevError,
        OSError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _jev_model(args: argparse.Namespace) -> JevAssessmentModel:
    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        raise ValueError("TYPESAFE_API_KEY is not set")
    client = JevClient(
        api_key,
        base_url=os.environ.get("TYPESAFE_BASE_URL", "https://api.typesafe.ai"),
        timeout=args.timeout,
    )
    return JevAssessmentModel(
        client,
        model=args.model,
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
