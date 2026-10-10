"""python -m algo_research snapshot | build | explore | run | ledger (see algo_research/cli.py)."""
import sys

from algo_research.cli import main

if __name__ == "__main__":   # Windows spawns worker processes by importing this module
    sys.exit(main())
