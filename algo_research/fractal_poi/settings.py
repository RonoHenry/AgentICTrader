"""The indicator's inputs, as its settings dialog has them, with its own defaults (algo-backtester Requirement 21.4).

Only the inputs that change what the indicator computes or draws are here. Colours, line styles and sizes are
the indicator's defaults, painted in the page's theme.

The inputs fall into two kinds:
- **Computing** inputs change the state the indicator carries from candle to candle: the Fractal mode, how many
  HTF candles it keeps, the liquidity levels it tracks (their purges share one registry), and the FVG timeframe.
  A change rereads the window.
- **Drawing** inputs (``DRAW_ONLY``) only choose what is drawn at the clock: the layers, the bias filter, the
  history count, the SD levels. A change redraws at once.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

from algo_research.fractal_poi.frames import MODES, in_seconds

__all__ = ["DRAW_ONLY", "FractalSettings"]

_SIZES = ("Small", "Normal", "Big")
_POSITIONS = ("Both", "Top", "Bottom")


@dataclass(frozen=True)
class FractalSettings:
    # General
    sweep_history: int = 10
    sweep_visible_only: bool = True
    fractal_mode: str = "Automatic"
    custom_htf: str = "60"
    bias: str = "Neutral"
    # HTF candles
    hide_candles: bool = False
    hide_setups: bool = False
    max_display: int = 4
    candle_size: str = "Small"
    offset: int = 10
    trace_show: bool = False
    vt_show: bool = True
    hl_show: bool = True
    prev_eq_show: bool = True
    drawings_type: str = "Both"
    # HTF2 candles
    htf2_show: bool = False
    htf2_count: int = 4
    htf2_gap: int = 6
    htf2_mode: str = "Automatic"
    htf2_custom: str = "1D"
    htf2_label_show: bool = True
    htf2_label_position: str = "Top"
    htf2_timer_show: bool = True
    # Labels
    htf_label_show: bool = True
    label_position: str = "Top"
    htf_timer_show: bool = True
    daily_name: bool = True
    dow_position: str = "Bottom"
    # Model
    sweep_show: bool = True
    sweep_live: bool = True
    show_c2_lbl: bool = True
    show_c3_lbl: bool = True
    show_c4_lbl: bool = True
    cisd_show: bool = True
    ic_cisd_show: bool = True
    entry_zone_show: bool = True
    early_cisd_show: bool = True
    # Standard deviation projections
    proj_show: bool = False
    proj_label_show: bool = True
    proj_type: str = "Wick"
    proj_deviations: str = "0,1,-1,-2,-2.5"
    # Formation liquidity
    liq_show: bool = True
    # Liquidity suite
    lq_mark_relevant: bool = False
    lq_atr_len: int = 25
    lq_atr_mult: float = 0.5
    lq_show_sessions: bool = True
    lq_hide_above_tf: str = "30"
    lq_draw_style: str = "Both"
    lq_box_transp: int = 92
    lq_max_sessions: int = 3
    lq_use_asia: bool = True
    lq_asia_session: str = "2000-0000"
    lq_use_london: bool = True
    lq_london_session: str = "0200-0500"
    lq_use_ny: bool = True
    lq_ny_session: str = "0930-1100"
    lq_session_labels: bool = True
    lq_use_true_open: bool = True
    lq_tdo_show_label: bool = True
    lq_show_pd: bool = True
    lq_show_pw: bool = True
    lq_show_pm: bool = False
    lq_show_htf1: bool = True
    lq_htf1_mode: str = "Auto"
    lq_htf1_manual: str = "60"
    lq_show_htf2: bool = False
    lq_htf2_manual: str = "240"
    lq_show_htf3: bool = False
    lq_htf3_manual: str = "1D"
    lq_max_bsl_lines: int = 5
    lq_del_purged: bool = False
    lq_purge_cross: bool = True
    lq_max_purged: int = 20
    lq_show_swings: bool = False
    lq_swing_window: int = 3
    lq_swing_len: int = 5
    lq_swing_atr_len: int = 10
    lq_swing_max_levels: int = 5
    lq_swing_label: str = "r"
    # SMT divergence
    smt_show: bool = True
    smt_label_show: bool = True
    smt_mode: str = "Automatic"
    smt_sym2_enable: bool = True
    smt_sym1: str = ""
    smt_sym1_inverse: bool = False
    smt_sym2: str = ""
    smt_sym2_inverse: bool = False
    # Fair value gaps
    fvg_show: bool = True
    fvg_auto_mode: bool = True
    fvg_manual_htf: str = "1D"
    fvg_show_bull: bool = True
    fvg_show_bear: bool = True
    fvg_show_midline: bool = False
    fvg_show_labels: bool = True
    fvg_show_boxes: bool = True
    fvg_max_fvgs: int = 3
    # Dashboard and the log
    dash_show: bool = True
    events_show: bool = True

    def __post_init__(self) -> None:
        choices = {"fractal_mode": MODES, "bias": ("Neutral", "Bullish", "Bearish"), "candle_size": _SIZES,
                   "drawings_type": ("Both", "On Chart", "HTF candle"), "htf2_mode": ("Automatic", "Custom"),
                   "htf2_label_position": _POSITIONS, "label_position": _POSITIONS, "dow_position": _POSITIONS,
                   "proj_type": ("Body", "Wick"), "lq_draw_style": ("Box", "Lines", "Both"),
                   "lq_htf1_mode": ("Auto", "Manual"), "smt_mode": ("Automatic", "Manual"),
                   "lq_swing_label": ("Hide", "r", "Rel. High", "Rel. Low")}
        for name, allowed in choices.items():
            if getattr(self, name) not in allowed:
                raise ValueError(f"{name}: one of {', '.join(allowed)}")
        for name in ("custom_htf", "htf2_custom", "lq_hide_above_tf", "lq_htf1_manual", "lq_htf2_manual",
                     "lq_htf3_manual", "fvg_manual_htf"):
            if in_seconds(getattr(self, name)) is None:
                raise ValueError(f"{name}: a timeframe such as 15, 60, 240, 1D or 1W")
        lows = {"max_display": 4, "offset": 1, "sweep_history": 0, "htf2_count": 1, "htf2_gap": 0, "lq_max_sessions": 1,
                "lq_max_bsl_lines": 1, "lq_max_purged": 1, "lq_swing_window": 1, "lq_swing_len": 1, "lq_atr_len": 1,
                "lq_swing_atr_len": 1, "lq_swing_max_levels": 1, "fvg_max_fvgs": 1}
        for name, low in lows.items():
            if int(getattr(self, name)) < low:
                raise ValueError(f"{name}: at least {low}")
        if self.htf2_count > 10 or self.lq_max_sessions > 20 or self.lq_max_bsl_lines > 20 or self.lq_max_purged > 100 \
                or self.fvg_max_fvgs > 100 or self.lq_swing_max_levels > 50 or self.lq_swing_window > 10:
            raise ValueError("a count above the indicator's own maximum")
        if not 0 <= self.lq_box_transp <= 100 or self.lq_atr_mult <= 0:
            raise ValueError("lq_box_transp: 0 to 100; lq_atr_mult: above 0")
        for name in ("lq_asia_session", "lq_london_session", "lq_ny_session"):
            _session(getattr(self, name))
        self.deviations()

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "FractalSettings":
        """The page's settings over the defaults. Unknown names are refused, so a typo can't pass for a choice."""
        raw = dict(raw or {})
        known = {f.name: f for f in fields(cls)}
        unknown = sorted(set(raw) - set(known))
        if unknown:
            raise ValueError(f"unknown settings: {', '.join(unknown)}")
        out = {}
        for name, value in raw.items():
            kind = known[name].type
            if kind == "bool":
                out[name] = value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "on")
            elif kind == "int":
                out[name] = int(value)
            elif kind == "float":
                out[name] = float(value)
            else:
                out[name] = str(value)
        return cls(**out)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def compute_key(self) -> tuple:
        """The computing inputs: two settings with the same key read the window alike."""
        return tuple((k, v) for k, v in asdict(self).items() if k not in DRAW_ONLY)

    @property
    def width(self) -> int:
        return {"Small": 2, "Normal": 4, "Big": 6}[self.candle_size]

    def deviations(self) -> list[float]:
        out = []
        for part in self.proj_deviations.split(","):
            part = part.strip()
            if part:
                try:
                    out.append(float(part))
                except ValueError as exc:
                    raise ValueError(f"proj_deviations: numbers separated by commas, not {part!r}") from exc
        return out

    def sessions(self) -> list[tuple[str, tuple[int, int], str, str, str]]:
        """The suite's sessions in the indicator's order: name, (start, end) in minutes of the New York day,
        colour, and the high and low labels."""
        out = []
        for use, name, spec, color, hi, lo in ((self.lq_use_asia, "Asia", self.lq_asia_session, "#eeb56b", "A.H", "A.L"),
                                                (self.lq_use_london, "London", self.lq_london_session, "#524078", "L.H", "L.L"),
                                                (self.lq_use_ny, "New York", self.lq_ny_session, "#0b7866", "NY.H", "NY.L")):
            if use:
                out.append((name, _session(spec), color, hi, lo))
        return out


def _session(spec: str) -> tuple[int, int]:
    """Pine's "HHMM-HHMM" session as minutes of the day; an end of 0000 is midnight."""
    try:
        a, b = spec.split("-")
        start, end = int(a[:2]) * 60 + int(a[2:]), int(b[:2]) * 60 + int(b[2:])
    except (ValueError, IndexError) as exc:
        raise ValueError(f"session: HHMM-HHMM, not {spec!r}") from exc
    if not (len(a) == len(b) == 4 and 0 <= start < 1440 and 0 <= end < 1440):
        raise ValueError(f"session: HHMM-HHMM, not {spec!r}")
    return start, end


#: Inputs that only choose what is drawn at the clock.
DRAW_ONLY = frozenset({
    "sweep_history", "sweep_visible_only", "bias", "hide_candles", "hide_setups", "candle_size", "offset", "trace_show",
    "vt_show", "hl_show", "prev_eq_show", "drawings_type", "htf2_gap", "htf2_label_show", "htf2_label_position",
    "htf2_timer_show", "htf_label_show", "label_position", "htf_timer_show", "daily_name", "dow_position",
    "sweep_live", "show_c2_lbl", "show_c3_lbl", "show_c4_lbl", "cisd_show", "ic_cisd_show", "entry_zone_show",
    "early_cisd_show", "proj_show", "proj_label_show", "proj_deviations", "liq_show", "lq_mark_relevant",
    "lq_draw_style", "lq_box_transp", "lq_session_labels", "lq_use_true_open", "lq_tdo_show_label", "lq_purge_cross",
    "lq_swing_label", "smt_show", "smt_label_show", "fvg_show", "fvg_show_midline", "fvg_show_labels",
    "fvg_show_boxes", "dash_show", "events_show",
})
