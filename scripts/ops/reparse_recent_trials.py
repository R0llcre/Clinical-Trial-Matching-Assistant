#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys


def _project_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _configure_import_path() -> None:
    worker_dir = _project_root() / "apps" / "worker"
    sys.path.insert(0, str(worker_dir))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Re-parse recently fetched trials with rule_v1 or llm_v1.",
    )
    parser.add_argument(
        "--parser-version",
        default="llm_v1",
        choices=("rule_v1", "llm_v1"),
        help="Parser version to apply for re-parse (default: llm_v1).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum number of recent trials to re-parse (default: 200).",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=168,
        help="Only select trials fetched in last N hours (default: 168).",
    )
    parser.add_argument(
        "--condition",
        default="",
        help="Optional condition keyword filter over title/conditions.",
    )
    parser.add_argument(
        "--status",
        default="",
        help="Optional trial status filter, e.g. RECRUITING.",
    )
    return parser


def main() -> int:
    _configure_import_path()
    from tasks import reparse_recent_trials  # pylint: disable=import-error

    args = _build_parser().parse_args()
    summary = reparse_recent_trials(
        parser_version=args.parser_version,
        limit=max(1, args.limit),
        lookback_hours=max(1, args.lookback_hours),
        condition=args.condition.strip() or None,
        status=args.status.strip() or None,
    )
    print(json.dumps(summary, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
