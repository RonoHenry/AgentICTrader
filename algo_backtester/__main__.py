"""python -m algo_backtester check-data | run | compare (see algo_backtester/cli.py)."""
import sys

from algo_backtester.cli import main

# The guard matters: Phase A starts one process per instrument, and on Windows
# each worker re-imports this module.
if __name__ == "__main__":
    sys.exit(main())
