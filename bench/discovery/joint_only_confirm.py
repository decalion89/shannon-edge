#!/usr/bin/env python3
"""Confirmation of the joint-only share on fresh events (pre-registered in
bench/discovery/joint_only_confirm_preregistration.md).

ESA Mission 1, channels of (subsystem_6, group 4) and (subsystem_3, group 18). Evaluated: only
event IDs that do not touch channels 41-46 (used in the exploratory run). Local tests per channel:
first-order transition, second-order transition and level frequency (3C tests). Joint tests: the
excess of -log2 P(y_t | y_{t-1}, x_t) over the first-order local cost, for every ordered pair.

Usage: joint_only_confirm.py ESA-Mission1.zip
"""

import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import fisher_exact

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from anomaly_esaadb import load  # noqa: E402
from joint_only import Q, frozen_cost, wilson  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "results" / "data"
CHANS = [14, 21, 29, 30, 38, 70, 71, 72, 73, 74, 75, 76]
USED = range(41, 47)
VAL = "2006-10-01"
ALPHA = 0.01
NNULL = 19999


def main():
    rng = np.random.default_rng(0)
    name = "ESA-Mission1"
    z = zipfile.ZipFile(sys.argv[1])
    lab = pd.read_csv(io.BytesIO(z.read(f"{name}/labels.csv")))
    typ = pd.read_csv(io.BytesIO(z.read(f"{name}/anomaly_types.csv")))
    lab = lab.merge(typ, on="ID")
    lab = lab[lab.Category != "Communication Gap"]
    used_ids = set(lab[lab.Channel.isin([f"channel_{c}" for c in USED])].ID)
    lab = lab[lab.Channel.isin([f"channel_{c}" for c in CHANS])].copy()
    for c in ("StartTime", "EndTime"):
        lab[c] = pd.to_datetime(lab[c]).dt.tz_localize(None)
    V = []
    for ch in CHANS:
        s = load(z, f"{name}/channels/channel_{ch}.zip")
        V.append(s[~s.index.duplicated(keep="last")].sort_index())
    # Amendment (before any result): the two groups are sampled at 90 s and ~30 s with different offsets.
    # Every channel is aligned onto channel 14's 90 s timestamps by its last value at or before each one.
    grid = V[0].index
    V = [s.reindex(grid, method="ffill").bfill() for s in V]
    idx = V[0].index.tz_localize(None) if V[0].index.tz is not None else V[0].index
    n = len(idx)
    lab["i0"] = np.searchsorted(idx, lab.StartTime.to_numpy())
    lab["i1"] = np.maximum(np.searchsorted(idx, lab.EndTime.to_numpy(), side="right") - 1, lab.i0)
    labelled = np.zeros(n, bool)
    for a, b in zip(lab.i0, lab.i1):
        labelled[a:b + 1] = True
    normal = (idx < pd.Timestamp(VAL)) & ~labelled
    fit = normal.copy()
    fit[:2] = False
    C = len(CHANS)
    q = []
    for s in V:
        v = pd.to_numeric(s, errors="coerce").to_numpy(np.float64)
        v = np.where(np.isfinite(v), v, np.nanmedian(v[normal]))
        lo, hi = np.quantile(v[normal], 0.005), np.quantile(v[normal], 0.995)
        q.append(np.clip(((v - lo) / (hi - lo + 1e-12) * Q).astype(np.int64), 0, Q - 1))
    p1 = [np.r_[x[0], x[:-1]] for x in q]
    p2 = [np.r_[x[0], x[0], x[:-2]] for x in q]
    fresh = lab[~lab.ID.isin(used_ids)]
    ev = fresh.groupby("ID").agg(i0=("i0", "min"), i1=("i1", "max"), cls=("Class", "first"),
                                 cat=("Category", "first"), loc=("Locality", "first"))
    okc = np.r_[0, np.cumsum(normal)]
    nulls = {}
    for eid, e in ev.iterrows():
        a, b = int(e.i0), int(e.i1) + 1
        ell = b - a
        starts = np.nonzero(okc[ell:] - okc[:-ell] == ell)[0] if ell < n else np.array([], int)
        if len(starts) >= 100:
            nulls[eid] = (a, b, ell, rng.choice(starts, NNULL, replace=len(starts) < NNULL))
    pl = {e: [] for e in nulls}
    pj = {e: [] for e in nulls}

    def score(cost, out):
        cs = np.r_[0.0, np.cumsum(cost)]
        for eid, (a, b, ell, ns) in nulls.items():
            obs = (cs[b] - cs[a]) / ell
            nul = (cs[ns + ell] - cs[ns]) / ell
            out[eid].append((1 + np.sum(nul >= obs)) / (1 + NNULL))

    local = []
    for j in range(C):
        l1 = frozen_cost(q[j], p1[j], Q, fit)
        local.append(l1)
        score(l1, pl)
        score(frozen_cost(q[j], p2[j] * Q + p1[j], Q * Q, fit), pl)
        score(frozen_cost(q[j], np.zeros(n, np.int64), 1, fit), pl)
    for i in range(C):
        for j in range(C):
            if i != j:
                score(frozen_cost(q[j], p1[j] * Q + q[i], Q * Q, fit) - local[j], pj)
    rows = []
    for eid, e in ev.iterrows():
        base = dict(ID=eid, length=int(e.i1 - e.i0 + 1), cls=e["cls"], cat=e["cat"], loc=e["loc"])
        if eid not in nulls:
            rows.append(dict(base, verdict="untestable"))
            continue
        vl, vj = min(pl[eid]), min(pj[eid])
        verdict = "local" if vl <= ALPHA / (3 * C) else ("joint-only" if vj <= ALPHA / (C * (C - 1)) else "invisible")
        rows.append(dict(base, verdict=verdict, min_p_local=vl, min_p_joint=vj))
    d = pd.DataFrame(rows)
    d.to_csv(DATA / "joint_only_confirm_m1.csv", index=False)
    t = d[d.verdict != "untestable"]
    k, nn = int((t.verdict == "joint-only").sum()), len(t)
    lo, hi = wilson(k, nn)
    print(f"{len(d)} fresh events, {nn} testable: local {int((t.verdict == 'local').sum())}, joint-only {k}, "
          f"invisible {int((t.verdict == 'invisible').sum())}")
    print(f"K1 joint-only share {k / max(nn, 1):.3f} (95% Wilson CI {lo:.3f}-{hi:.3f}; lower bound >= 0.05): "
          f"{'HOLDS' if lo >= 0.05 else 'REFUTED'}")
    tab = [[int(((t["loc"] == L) & (t.verdict == "joint-only")).sum()), int(((t["loc"] == L) & (t.verdict != "joint-only")).sum())]
           for L in ("Local", "Global")]
    p = fisher_exact(tab, alternative="greater").pvalue
    print(f"K2 joint-only share Local {tab[0][0]}/{sum(tab[0])} vs Global {tab[1][0]}/{sum(tab[1])}, one-sided Fisher "
          f"p = {p:.4g} (< 0.05): {'HOLDS' if p < 0.05 else 'REFUTED'}")
    clear = int(((t.verdict == "joint-only") & (t.min_p_local > 0.05)).sum())
    print(f"Robustness: joint-only events whose every local p > 0.05: {clear} of {k}")
    print(pd.crosstab(d["loc"], d.verdict).to_string())
    print(pd.crosstab(d["cls"], d.verdict).to_string())


if __name__ == "__main__":
    main()
