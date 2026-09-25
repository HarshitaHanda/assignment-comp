from __future__ import annotations

import argparse

from .research import run as run_research
from .summary import run as run_summary
from .verify import run as run_verify


def main() -> None:
    parser = argparse.ArgumentParser(description="Run research, verification, and summary.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--sample-size", type=int, default=15)
    parser.add_argument("--skip-verify", action="store_true")
    args = parser.parse_args()

    run_research(limit=args.limit, start=args.start)
    if not args.skip_verify:
        run_verify(sample_size=args.sample_size)
    run_summary()


if __name__ == "__main__":
    main()
