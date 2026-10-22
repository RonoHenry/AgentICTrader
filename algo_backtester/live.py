"""A live Noculus session's candles (algo-backtester update 2026-10-22, Requirement 27).

The trader ran the fixed engine on the live market and asked to watch it on Noculus. A session there replays the
research snapshot; a live one reads the broker's MT5 terminal instead, through ``LiveSource``: the same shape as
``watch.SnapshotSource`` (M1 for the backtester to build every timeframe from), topped up with each newly closed
minute. ``Terminal`` reads the terminal as the live runner does: the broker profile's symbols and server clock, and
the credentials from ``.env`` (MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH).

Only closed candles are served: the forming one waits for its close, so nothing a session shows can change.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Sequence

import pandas as pd

from algo_backtester.data import StoredBar
from liquidity_engine.models import Timeframe

__all__ = ["HISTORY", "LiveSource", "Rates", "Terminal", "stored_bars"]

#: The M1 a live source reads on first use: the W1 warm-up of the trader's windows (30 weeks), Model A's 100 days
#: and the indicator's, with room.
HISTORY = timedelta(days=240)
COLUMNS = ["time", "open", "high", "low", "close", "volume", "spread"]
_MINUTES = {Timeframe.M1: 1, Timeframe.M3: 3, Timeframe.M5: 5, Timeframe.M15: 15, Timeframe.M30: 30, Timeframe.H1: 60,
            Timeframe.H3: 180, Timeframe.H4: 240, Timeframe.H6: 360, Timeframe.H8: 480, Timeframe.H12: 720,
            Timeframe.D1: 1440, Timeframe.W1: 10080}
#: copy_rates_range refuses a request that spans too many bars, so ranges are read in chunks of about this many.
_BARS_PER_CHUNK = 40_000

#: (instrument, timeframe, start, end) -> the bars opening in [start, end), as a frame of COLUMNS (UTC times,
#: the spread in price).
Rates = Callable[[str, Timeframe, datetime, datetime], pd.DataFrame]


def stored_bars(frame: pd.DataFrame, instrument: str, tf: Timeframe) -> list[StoredBar]:
    """A frame of COLUMNS as the backtester's bars."""
    spread = frame["spread"] if "spread" in frame else pd.Series([None] * len(frame))
    volume = frame["volume"] if "volume" in frame else pd.Series([None] * len(frame))
    return [StoredBar(t.to_pydatetime(), o, h, lo, c, None if pd.isna(v) else int(v), None if pd.isna(s) else float(s),
                      tf, instrument)
            for t, o, h, lo, c, v, s in zip(frame["time"], frame["open"], frame["high"], frame["low"], frame["close"],
                                            volume, spread)]


class LiveSource:
    """A CandleSource over a live feed, shaped as ``SnapshotSource``: each instrument's M1 of the last ``history``,
    read on first use and topped up by ``refresh``; other timeframes straight from the feed, for a warm-up the M1
    doesn't reach. ``now`` is the clock (UTC)."""

    def __init__(self, rates: Rates, instruments: Sequence[str], history: timedelta = HISTORY,
                 now: Optional[Callable[[], datetime]] = None) -> None:
        self.rates, self.instruments, self.history = rates, tuple(i.upper() for i in instruments), history
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._m1: dict[str, pd.DataFrame] = {}
        self._lock = threading.RLock()

    def held(self) -> list[str]:
        return list(self.instruments)

    def refresh(self, instrument: str) -> int:
        """Read the M1 candles closed since the last one held; how many were new."""
        with self._lock:
            now = pd.Timestamp(self.now())
            held = self._m1.get(instrument)
            last = None if held is None or held.empty else held["time"].iloc[-1]
            since = now - pd.Timedelta(self.history) if last is None else last + pd.Timedelta(minutes=1)
            new = _closed(self.rates(instrument, Timeframe.M1, since.to_pydatetime(), now.to_pydatetime()),
                          Timeframe.M1, now)
            if last is not None:
                new = new[new["time"] > last]
            if held is None or new.empty:
                self._m1[instrument] = new.reset_index(drop=True) if held is None else held
            else:                                    # a new frame: a reader holding the old one is unaffected
                self._m1[instrument] = pd.concat([held, new], ignore_index=True)
            return len(new)

    def _frame(self, instrument: str) -> pd.DataFrame:
        with self._lock:
            if instrument not in self._m1:
                self.refresh(instrument)
            return self._m1[instrument]

    def bars(self, instrument: str, tf: Timeframe, start: datetime, end: datetime) -> list[StoredBar]:
        if tf == Timeframe.M1:
            f = self._frame(instrument)
            f = f[(f["time"] >= pd.Timestamp(start)) & (f["time"] < pd.Timestamp(end))]
        else:
            f = _closed(self.rates(instrument, tf, start, end), tf, pd.Timestamp(self.now()))
        return stored_bars(f, instrument, tf)

    def last_time(self, instrument: str, tf: Timeframe) -> Optional[datetime]:
        f = self._frame(instrument)
        return None if f.empty or tf != Timeframe.M1 else f["time"].iloc[-1].to_pydatetime()


def _closed(frame: pd.DataFrame, tf: Timeframe, now: pd.Timestamp) -> pd.DataFrame:
    """The bars of ``frame`` closed by ``now``, in time order, one per time."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=COLUMNS).astype({"time": "datetime64[ns, UTC]"})
    frame = frame.assign(time=pd.to_datetime(frame["time"], utc=True))
    frame = frame[frame["time"] + pd.Timedelta(minutes=_MINUTES[tf]) <= now]
    return frame.drop_duplicates("time", keep="last").sort_values("time").reset_index(drop=True)


class Terminal:
    """The broker's MT5 terminal as ``Rates``: the profile's symbols and server clock. It connects on first use;
    the MetaTrader5 package is one connection per process, so its calls are taken one at a time."""

    def __init__(self, profile) -> None:
        self.profile, self.clock = profile, profile.clock()
        self._mt5 = None
        self._lock = threading.Lock()

    def _connect(self):
        if self._mt5 is None:
            import MetaTrader5 as mt5
            from decouple import config

            credentials = {"login": config("MT5_LOGIN", cast=int), "password": config("MT5_PASSWORD"),
                           "server": config("MT5_SERVER")}
            if config("MT5_PATH", default=""):
                credentials["path"] = config("MT5_PATH")
            if not mt5.initialize(**credentials):
                raise LookupError(f"the MT5 terminal did not connect: {mt5.last_error()}")
            self._mt5 = mt5
        return self._mt5

    def __call__(self, instrument: str, tf: Timeframe, start: datetime, end: datetime) -> pd.DataFrame:
        with self._lock:
            mt5 = self._connect()
            symbol = self.profile.symbol(instrument)
            info = mt5.symbol_info(symbol) if mt5.symbol_select(symbol, True) else None
            if info is None:
                return pd.DataFrame(columns=COLUMNS)              # the broker doesn't carry it
            code = getattr(mt5, f"TIMEFRAME_{tf.value}")
            step = timedelta(days=min(180, max(1, _BARS_PER_CHUNK * _MINUTES[tf] // 1440)))
            rows, cursor = [], start
            while cursor < end:
                upto = min(cursor + step, end)
                rates = mt5.copy_rates_range(symbol, code, self.clock.to_server(cursor), self.clock.to_server(upto))
                for r in () if rates is None else rates:
                    t = self.clock.to_utc(r["time"])
                    if cursor <= t < upto:                        # the terminal can return a stray bar outside it
                        rows.append((t, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
                                     int(r["tick_volume"]), float(r["spread"]) * info.point))
                cursor = upto
            return pd.DataFrame(rows, columns=COLUMNS)
