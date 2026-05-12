"""
analytics-svc — KPI rollup CLI for manual backfill.

Usage:
    python -m app.cli.rollup_cli --backfill 2026-01-01..2026-02-01
    python -m app.cli.rollup_cli --day 2026-05-10
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="KPI rollup CLI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--backfill",
        metavar="FROM..TO",
        help="Backfill range e.g. 2026-01-01..2026-02-01",
    )
    group.add_argument(
        "--day",
        metavar="YYYY-MM-DD",
        help="Run rollup for a single day",
    )
    args = parser.parse_args()

    from app.tasks.rollup import rollup_day

    if args.day:
        day = date.fromisoformat(args.day)
        logging.info("Running rollup for %s", day)
        result = rollup_day(day)
        failed = {k: v for k, v in result.items() if not v.startswith("ok")}
        if failed:
            logging.error("Failures: %s", failed)
            sys.exit(1)
        logging.info("All metrics OK for %s", day)
    elif args.backfill:
        from_str, to_str = args.backfill.split("..")
        from_date = date.fromisoformat(from_str)
        to_date = date.fromisoformat(to_str)
        logging.info("Backfilling %s .. %s", from_date, to_date)
        from app.tasks.rollup import backfill
        # Call the underlying function directly (bypass Celery)
        results = backfill.__wrapped__(from_str, to_str)
        total_ok = sum(1 for day_res in results.values() for v in day_res.values() if v.startswith("ok"))
        total_fail = sum(1 for day_res in results.values() for v in day_res.values() if not v.startswith("ok"))
        logging.info("Backfill complete: %d ok, %d failed", total_ok, total_fail)
        if total_fail > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
