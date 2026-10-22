"""
The chart pages' own scripts, driven under node with the browser stubbed (algo-backtester update 2026-10-16).

There is no headless browser in this environment, so each check in tests/js/ loads the real static files
into node with just enough DOM and Lightweight Charts to run them, and drives them as a person would:

- load_engine.js: the Noculus page's scripts load in the page's order without throwing (a throw there is a
  blank page: 2026-10-17, a stale server 404ed noculus.js and engine.js died at its first line);
- noculus_ui.js: arm the tools, click a candle, place and close a trade, place a drawn position beside the
  engine's trade, reveal, compare, and an open session's positions panel;
- drawings_ui.js: the magnet off / weak / strong, Shift keeping a line level, Shift still measuring alone;
- reconnect_ui.js: the server restarts under an open page, and the same session comes back at the same clock;
- fractal_ui.js: the trader's Fractal + POI indicator asked for at the clock, painted, set up in its dialog;
- live_ui.js: a live session started, opened at the last closed minute, followed as it moves on, left where the
  trader stepped back to, and live again after a restart (Requirement 27).

Skipped when node is not installed.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).parent / "js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


@pytest.mark.parametrize("script", ["load_engine.js", "noculus_ui.js", "drawings_ui.js", "reconnect_ui.js",
                                    "fractal_ui.js", "live_ui.js"])
def test_the_page_scripts(script):
    run = subprocess.run([NODE, str(JS / script)], capture_output=True, text=True, timeout=120, cwd=JS)
    assert run.returncode == 0, f"{script} failed:\n{run.stdout[-3000:]}\n{run.stderr[-3000:]}"
    if script != "load_engine.js":
        assert " 0 failed" in run.stdout, run.stdout[-3000:]
