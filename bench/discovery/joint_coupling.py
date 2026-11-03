#!/usr/bin/env python3
"""Does the coupling between sensors break during real anomalies? (pre-registered in
bench/discovery/joint_coupling_preregistration.md)

Marginal-free statistic: inside a window, each channel is quantised by its own ranks (8 equal-count
levels), so the levels of every channel are uniform by construction. The coupling of the ordered
pair x -> y is the information x_t adds about y_t beyond y_{t-1}, measured as
  I = H(y_t | y_{t-1}, x_shifted) - H(y_t | y_{t-1}, x_t)    (plug-in, bits per sample)
where x_shifted is x circularly shifted by half the window: the same values, their pairing broken.
An event breaks the coupling when its I is lower than in normal training windows of the same length.

Usage: joint_coupling.py ESA-Mission1.zip ESA-Mission2.zip
"""

import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import fisher_exact, rankdata

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from anomaly_esaadb import load  # noqa: E402
from joint_only import wilson  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "results" / "data"
Q = 8
MINLEN, MAXLEN = 64, 2000
NNULL = 1999
ALPHA = 0.01
SETS = [  # (name, mission, channels, validation date, exclude event IDs touching these channels)
    ("M1-light", "ESA-Mission1", list(range(41, 47)), "2006-10-01", None),
    ("M1-groups", "ESA-Mission1", [14, 21, 29, 30, 38, 70, 71, 72, 73, 74, 75, 76], "2006-10-01", list(range(41, 47))),
    ("M2-light", "ESA-Mission2", list(range(18, 29)), "2001-07-01", None),
]


def rank_levels(W):
    """Rows of W -> equal-count levels 0..Q-1 by within-row ranks (ties share a level)."""
    r = rankdata(W, axis=1, method="average")
    return np.minimum(((r - 1) * Q / W.shape[1]).astype(np.int64), Q - 1)


def cond_entropy(y, ctx, nctx):
    """Per-row plug-in H(y | ctx) in bits; y, ctx: (rows, len)."""
    rows, n = y.shape
    key = (np.arange(rows)[:, None] * nctx + ctx) * Q + y
    nyc = np.bincount(key.ravel(), minlength=rows * nctx * Q).reshape(rows, nctx, Q).astype(float)
    nc = nyc.sum(2, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(nyc > 0, nyc * np.log2(nc / nyc), 0.0)
    return t.sum((1, 2)) / n


def coupling(Lx, Ly, Dx, Dy):
    """I for rows of level matrices; NaN where either channel has < 4 distinct values."""
    n = Lx.shape[1]
    yt, yp = Ly[:, 1:], Ly[:, :-1]
    xa = Lx[:, 1:]
    xs = np.roll(Lx, n // 2, axis=1)[:, 1:]
    I = cond_entropy(yt, yp * Q + xs, Q * Q) - cond_entropy(yt, yp * Q + xa, Q * Q)
    return np.where((Dx >= 4) & (Dy >= 4), I, np.nan)


def windows(v, starts, ell):
    return v[starts[:, None] + np.arange(ell)]


def distinct(W):
    s = np.sort(W, axis=1)
    return 1 + (np.diff(s, axis=1) != 0).sum(1)


def load_set(z, mission, chans, val, excl):
    lab = pd.read_csv(io.BytesIO(z.read(f"{mission}/labels.csv")))
    typ = pd.read_csv(io.BytesIO(z.read(f"{mission}/anomaly_types.csv")))
    lab = lab.merge(typ, on="ID")
    lab = lab[lab.Category != "Communication Gap"]
    excl_ids = set(lab[lab.Channel.isin([f"channel_{c}" for c in excl])].ID) if excl else set()
    lab = lab[lab.Channel.isin([f"channel_{c}" for c in chans])].copy()
    for c in ("StartTime", "EndTime"):
        lab[c] = pd.to_datetime(lab[c]).dt.tz_localize(None)
    V = []
    for ch in chans:
        s = load(z, f"{mission}/channels/channel_{ch}.zip")
        V.append(s[~s.index.duplicated(keep="last")].sort_index())
    grid = V[0].index
    V = [s.reindex(grid, method="ffill").bfill() for s in V]
    idx = grid.tz_localize(None) if grid.tz is not None else grid
    X = np.stack([pd.to_numeric(s, errors="coerce").to_numpy(np.float64) for s in V])
    X = np.where(np.isfinite(X), X, 0.0)
    lab["i0"] = np.searchsorted(idx, lab.StartTime.to_numpy())
    lab["i1"] = np.maximum(np.searchsorted(idx, lab.EndTime.to_numpy(), side="right") - 1, lab.i0)
    labelled = np.zeros(len(idx), bool)
    for a, b in zip(lab.i0, lab.i1):
        labelled[a:b + 1] = True
    train = idx < pd.Timestamp(val)
    ev = lab[~lab.ID.isin(excl_ids)].groupby("ID").agg(i0=("i0", "min"), i1=("i1", "max"),
                                                       loc=("Locality", "first"), cls=("Class", "first"))
    return X, train & ~labelled, ~train & ~labelled, ev


def valid_starts(mask, ell):
    c = np.r_[0, np.cumsum(mask)]
    return np.nonzero(c[ell:] - c[:-ell] == ell)[0]


def top_pairs(X, normal, rng):
    """The C ordered pairs with the highest median coupling over 200 normal training windows (length 512)."""
    C = len(X)
    st = rng.choice(valid_starts(normal, 512), 200)
    L = [rank_levels(windows(X[j], st, 512)) for j in range(C)]
    D = [distinct(windows(X[j], st, 512)) for j in range(C)]
    score = {(i, j): np.nanmedian(coupling(L[i], L[j], D[i], D[j])) for i in range(C) for j in range(C) if i != j}
    return sorted(score, key=lambda k: -np.nan_to_num(score[k], nan=-1))[:C]


def test_window(X, pairs, a, ell, nst):
    """Min Bonferroni-corrected verdict for one window [a, a+ell) against null starts nst (same length)."""
    m = min(ell, MAXLEN)
    off = (ell - m) // 2
    st = np.r_[a + off, nst + off]
    C = len(X)
    L, D = {}, {}
    for j in {k for p in pairs for k in p}:
        W = windows(X[j], st, m)
        L[j], D[j] = rank_levels(W), distinct(W)
    ps = []
    for i, j in pairs:
        I = coupling(L[i], L[j], D[i], D[j])
        obs, nul = I[0], I[1:]
        nul = nul[np.isfinite(nul)]
        if not np.isfinite(obs) or len(nul) < 200:
            continue
        ps.append((1 + np.sum(nul <= obs)) / (1 + len(nul)))
    if not ps:
        return None, None
    pmin = min(ps)
    return pmin, bool(pmin <= ALPHA / len(ps))


def main():
    rng = np.random.default_rng(0)
    zips = {"ESA-Mission1": zipfile.ZipFile(sys.argv[1]), "ESA-Mission2": zipfile.ZipFile(sys.argv[2])}
    rows = []
    for name, mission, chans, val, excl in SETS:
        X, normal, later, ev = load_set(zips[mission], mission, chans, val, excl)
        pairs = top_pairs(X, normal, rng)
        print(f"{name}: {len(ev)} events; pairs {[(chans[i], chans[j]) for i, j in pairs]}", flush=True)
        for eid, e in ev.iterrows():
            a, ell = int(e.i0), int(e.i1 - e.i0 + 1)
            base = dict(set=name, ID=eid, length=ell, loc=e["loc"], cls=e["cls"])
            if ell < MINLEN:
                rows.append(dict(base, kind="event", verdict="untestable"))
                continue
            m = min(ell, MAXLEN)
            vs, vl = valid_starts(normal, ell), valid_starts(later, ell)  # not cached: OOM on Mission 2
            if len(vs) < 200:
                rows.append(dict(base, kind="event", verdict="untestable"))
                continue
            nst = rng.choice(vs, NNULL, replace=len(vs) < NNULL)
            p, br = test_window(X, pairs, a, ell, nst)
            rows.append(dict(base, kind="event", verdict="untestable" if p is None else ("broken" if br else "intact"),
                             pmin=p))
            if len(vl):
                c0 = int(rng.choice(vl))
                p, br = test_window(X, pairs, c0, ell, nst)
                rows.append(dict(base, kind="control", verdict="untestable" if p is None else ("broken" if br else "intact"),
                                 pmin=p))
    d = pd.DataFrame(rows)
    d.to_csv(DATA / "joint_coupling.csv", index=False)
    t = d[d.verdict != "untestable"]
    print()
    for s, g in t.groupby("set"):
        for k in ("event", "control"):
            h = g[g.kind == k]
            print(f"{s} {k}s: {int((h.verdict == 'broken').sum())}/{len(h)} broken")
    ev_, co = t[t.kind == "event"], t[t.kind == "control"]
    kb, nb = int((ev_.verdict == "broken").sum()), len(ev_)
    kc, nc = int((co.verdict == "broken").sum()), len(co)
    pf = fisher_exact([[kb, nb - kb], [kc, nc - kc]], alternative="greater").pvalue
    diff = kb / max(nb, 1) - kc / max(nc, 1)
    lo, hi = wilson(kb, nb)
    print(f"\nPooled: events {kb}/{nb} broken ({kb / max(nb, 1):.3f}, 95% CI {lo:.3f}-{hi:.3f}); controls {kc}/{nc} "
          f"({kc / max(nc, 1):.3f})")
    print(f"R1 events > controls by >= 0.05 with one-sided Fisher p < 0.01: difference {diff:.3f}, p = {pf:.3g}: "
          f"{'HOLDS' if (diff >= 0.05 and pf < 0.01) else 'REFUTED'}")
    print("\nEvents by locality:")
    print(pd.crosstab(ev_["loc"], ev_.verdict).to_string())


if __name__ == "__main__":
    main()
