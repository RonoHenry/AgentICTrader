"""The 2018-2024 search: H-AB, the eye (docs/research/SEARCH_2018_2024.md).

A convolutional network reads the picture of the last 20 daily candles, as Jiang, Kelly and Xiu (2023, Journal of
Finance) read stock charts: 64 x 60 black-and-white pixels, three per day (the open tick, the high-low bar, the close
tick), the 20-day average of closes as a line, scaled to the window. Trained on every second trading day before
2018-07 of all 41 markets (``search_state3.usable``), to say whether the close five days on is higher; it calls each
development week from the picture of the 20 days before it, at its training probabilities' thirds, and is judged on
the nine's weeks of 2018-07 to 2022 by H-Y's rule.

    python -m algo_research.search_eye --window develop
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd

from algo_research.search_d1 import MARKETS, OUT
from algo_research.search_state import FIT_UNTIL, JUDGE, judge
from algo_research.universe import load_broad

__all__ = ["DAYS", "HEIGHT", "WIDTH", "images", "pictures"]

DAYS, HEIGHT = 20, 64
WIDTH = 3 * DAYS
HORIZON, STEP = 5, 2
SEEDS, EPOCHS, PATIENCE, BATCH, LR = (0, 1, 2), 8, 2, 256, 3e-4


# ── the pictures ───────────────────────────────────────────────────────────

def images(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray, ma: np.ndarray) -> np.ndarray:
    """(n, DAYS) arrays of each window's opens, highs, lows, closes and 20-day averages -> (n, HEIGHT, WIDTH) uint8
    pictures: white (255) on black, the top row the window's highest price."""
    n = len(o)
    top = np.maximum(h.max(1), np.nanmax(ma, 1))[:, None]
    bottom = np.minimum(l.min(1), np.nanmin(ma, 1))[:, None]
    span = np.where(top - bottom > 0, top - bottom, 1.0)
    row = lambda p: np.clip(np.rint((top - p) / span * (HEIGHT - 1)), 0, HEIGHT - 1).astype(np.int64)  # noqa: E731
    ro, rh, rl, rc = row(o), row(h), row(l), row(c)
    img = np.zeros((n, HEIGHT, WIDTH), np.uint8)
    idx = np.repeat(np.arange(n), DAYS)
    cols = np.tile(3 * np.arange(DAYS), n)
    img[idx, ro.ravel(), cols] = 255                                   # the open tick
    img[idx, rc.ravel(), cols + 2] = 255                               # the close tick
    rows = np.arange(HEIGHT)[None, None, :]
    bar = (rows >= rh[:, :, None]) & (rows <= rl[:, :, None])          # the high-low bar, (n, DAYS, HEIGHT)
    img[:, :, 3 * np.arange(DAYS) + 1] |= np.where(bar, 255, 0).astype(np.uint8).transpose(0, 2, 1)
    # the average, a line through the bars' centres
    x = np.clip((np.arange(WIDTH) - 1) / 3, 0, DAYS - 1)
    i0 = np.floor(x).astype(int)
    i1 = np.minimum(i0 + 1, DAYS - 1)
    f = x - i0
    line = ma[:, i0] * (1 - f) + ma[:, i1] * f
    ok = np.isfinite(line)
    rm = row(np.where(ok, line, top))
    nn, jj = np.nonzero(ok)
    img[nn, rm[nn, jj], jj] = 255
    return img


def pictures(days: pd.DataFrame, ends: np.ndarray) -> np.ndarray:
    """The pictures of the DAYS days ending at each row index of ``ends`` (inclusive)."""
    o, h, l, c = (days[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    ma = pd.Series(c).rolling(DAYS, min_periods=DAYS).mean().to_numpy()
    win = ends[:, None] + np.arange(-DAYS + 1, 1)[None, :]
    return images(o[win], h[win], l[win], c[win], ma[win])


def samples(market: str, days: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Training samples before FIT_UNTIL: every STEP-th day with a full window and average, its picture, whether the
    close HORIZON days on is higher (ties left out), and its date."""
    c = days["close"].to_numpy(float)
    dates = days["date"].to_numpy("datetime64[ns]")
    first = 2 * DAYS - 2
    ends = np.arange(first, len(days) - HORIZON, STEP)
    ends = ends[dates[ends + HORIZON] < np.datetime64(FIT_UNTIL, "ns")]
    move = c[ends + HORIZON] - c[ends]
    ends, move = ends[move != 0], move[move != 0]
    return pictures(days, ends), (move > 0).astype(np.float32), dates[ends]


def week_pictures(market: str, days: pd.DataFrame, weeks: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Each week's picture: the DAYS days before its Monday; and which weeks had one."""
    dates = days["date"].to_numpy("datetime64[ns]")
    last = np.searchsorted(dates, pd.to_datetime(weeks).to_numpy("datetime64[ns]"), side="left") - 1
    ok = last >= 2 * DAYS - 2
    return pictures(days, last[ok]), ok


# ── the network ────────────────────────────────────────────────────────────

def _network():
    import torch
    from torch import nn

    def block(cin, cout, **kw):
        return nn.Sequential(nn.Conv2d(cin, cout, (5, 3), **kw), nn.BatchNorm2d(cout), nn.LeakyReLU(0.01),
                             nn.MaxPool2d((2, 1)))

    class Eye(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.f = nn.Sequential(block(1, 16, stride=(3, 1), dilation=(2, 1), padding=(12, 1)),
                                   block(16, 32, padding=(2, 1)), block(32, 64, padding=(2, 1)))
            with torch.no_grad():
                n = self.f(torch.zeros(1, 1, HEIGHT, WIDTH)).numel()
            self.head = nn.Sequential(nn.Flatten(), nn.Dropout(0.5), nn.Linear(n, 1))

        def forward(self, x):
            return self.head(self.f(x)).squeeze(1)

    return Eye()


def _weights(markets: np.ndarray, y: np.ndarray) -> np.ndarray:
    w = np.ones(len(y), np.float32)
    for m in np.unique(markets):
        for side in (0, 1):
            idx = (markets == m) & (y == side)
            w[idx] = (markets == m).sum() / (2 * max(idx.sum(), 1))
    return w


def _predict(model, x: np.ndarray) -> np.ndarray:
    import torch
    model.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(x), 2048):
            xb = torch.from_numpy(x[i:i + 2048]).float().div_(255).unsqueeze(1)
            out.append(torch.sigmoid(model(xb)).numpy())
    return np.concatenate(out) if out else np.zeros(0)


def train(x: np.ndarray, y: np.ndarray, w: np.ndarray, dates: np.ndarray, seed: int, log=print):
    """One seed's network: Adam, early stopping on the last fifth of the samples in time."""
    import torch
    from torch import nn

    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    cut = np.quantile(dates.astype("int64"), 0.8)
    tr, va = np.nonzero(dates.astype("int64") < cut)[0], np.nonzero(dates.astype("int64") >= cut)[0]
    model = _network()
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    loss_fn = nn.BCEWithLogitsLoss(reduction="none")

    def val_loss() -> float:
        model.eval()
        tot = 0.0
        with torch.no_grad():
            for i in range(0, len(va), 2048):
                b = va[i:i + 2048]
                xb = torch.from_numpy(x[b]).float().div_(255).unsqueeze(1)
                tot += float((loss_fn(model(xb), torch.from_numpy(y[b])) * torch.from_numpy(w[b])).sum())
        return tot / float(w[va].sum())

    best, best_state, bad = np.inf, None, 0
    for epoch in range(EPOCHS):
        model.train()
        order = rng.permutation(tr)
        t0 = time.time()
        for i in range(0, len(order), BATCH):
            b = order[i:i + BATCH]
            xb = torch.from_numpy(x[b]).float().div_(255).unsqueeze(1)
            loss = (loss_fn(model(xb), torch.from_numpy(y[b])) * torch.from_numpy(w[b])).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
        v = val_loss()
        log(f"  seed {seed} epoch {epoch + 1}: validation loss {v:.5f} ({time.time() - t0:.0f} s)")
        if v < best - 1e-5:
            best, best_state, bad = v, {k: t.clone() for k, t in model.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= PATIENCE:
                break
    model.load_state_dict(best_state)
    return model


# ── the run ────────────────────────────────────────────────────────────────

def _row(name: str, r: dict, n_markets: int) -> str:
    if not r.get("calls"):
        return f"| {name} | 0 | | | | | | |"
    p = lambda x: f"{100 * x:+.1f}"                                          # noqa: E731
    return (f"| {name} | {r['calls']:,} | {r['hit']:.1%} | {r['base']:.1%} | {p(r['excess'])} | "
            f"[{p(r['lo'])}, {p(r['hi'])}] | {r['positive']}/{n_markets} | {'yes' if r.get('passes') else 'no'} |")


def main() -> None:
    import torch

    from algo_research.search_state import fit_and_call
    from algo_research.search_state3 import FEATURES as AA, tables, usable

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=["develop"], required=True)
    parser.add_argument("--threads", type=int, default=6)
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    t = tables()
    dev = t[(t["week"] >= JUDGE[0]) & (t["week"] < JUDGE[1])].reset_index(drop=True)
    fit_weeks = t[t["week"] < FIT_UNTIL].reset_index(drop=True)
    xs, ys, ds, ms = [], [], [], []
    week_x = {}
    for m in usable():
        days = load_broad(m)
        x, y, d = samples(m, days)
        xs.append(x), ys.append(y), ds.append(d), ms.append(np.full(len(y), m))
        for name, rows in (("dev", dev), ("fit", fit_weeks)):
            r = rows[rows["market"] == m]
            img, ok = week_pictures(m, days, r["week"])
            week_x[(name, m)] = (r.index.to_numpy()[ok], img)
        print(f"{m}: {len(y):,} training pictures", flush=True)
    x, y, dates, markets = np.concatenate(xs), np.concatenate(ys), np.concatenate(ds), np.concatenate(ms)
    del xs
    w = _weights(markets, y)
    print(f"{len(y):,} training pictures, {y.mean():.1%} up; validation from "
          f"{pd.Timestamp(np.quantile(dates.astype('int64'), 0.8)).date()}", flush=True)
    models = [train(x, y, w, dates, s, log=lambda s: print(s, flush=True)) for s in SEEDS]
    p_train = np.mean([_predict(mo, x) for mo in models], axis=0)
    lo, hi = np.quantile(p_train, [1 / 3, 2 / 3])

    def score(rows: pd.DataFrame, name: str) -> pd.DataFrame:
        p = np.full(len(rows), np.nan)
        for m in rows["market"].unique():
            idx, img = week_x[(name, m)]
            if len(idx):
                p[idx] = np.mean([_predict(mo, img) for mo in models], axis=0)
        out = rows.assign(p_eye=p)
        out = out[np.isfinite(out["p_eye"])].reset_index(drop=True)
        return out.assign(call=np.where(out["p_eye"] >= hi, 1, np.where(out["p_eye"] <= lo, -1, 0)))

    dev_s = score(dev, "dev")
    fit_s = score(fit_weeks, "fit")
    nine = dev_s[dev_s["market"].isin(MARKETS)]
    other = dev_s[~dev_s["market"].isin(MARKETS)]
    n_other = other["market"].nunique()
    r = judge(nine)
    lines = ["", "| Model | Calls | Hit | Drift | Excess (pts) | 95% weeks | Markets > 0 | H-Y's rule |",
             "|---|---|---|---|---|---|---|---|",
             _row("**H-AB: the eye, the nine's development weeks**", r, 9),
             _row("the eye on the other markets' development weeks", judge(other), n_other),
             _row("the eye on its fit weeks (in sample)", judge(fit_s[fit_s["up"] != 0]), fit_s["market"].nunique())]
    # the blend: H-AA's probability and the eye's, averaged, cut at the blend's thirds on the fit weeks
    f_aa, d_aa, _ = fit_and_call(t[t["week"] < FIT_UNTIL], dev, "gbm", AA)
    key = ["market", "week"]
    fb = fit_s[key + ["p_eye"]].merge(f_aa[key + ["p"]], on=key)
    blo, bhi = np.quantile((fb["p_eye"] + fb["p"]) / 2, [1 / 3, 2 / 3])
    db = dev_s.drop(columns=["call"]).merge(d_aa[key + ["p"]], on=key)
    pb = (db["p_eye"] + db["p"]) / 2
    db = db.assign(call=np.where(pb >= bhi, 1, np.where(pb <= blo, -1, 0)))
    lines.append(_row("the eye blended with H-AA, the nine", judge(db[db["market"].isin(MARKETS)]), 9))
    corr = float(np.corrcoef(db["p_eye"], db["p"])[0, 1])
    lines += ["", f"H-AB passes: {'yes' if r.get('passes') else 'no'}",
              "Excess per market, the eye: " + ", ".join(f"{m} {100 * v:+.1f} ({n})"
                                                         for m, (v, n) in r["per_market"].items()),
              f"Training pictures' probabilities: thirds at {lo:.4f} / {hi:.4f}; the eye's and H-AA's probabilities "
              f"correlate {corr:+.2f} on the development weeks"]
    dev_s.to_parquet(OUT / "eye_develop.parquet")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
