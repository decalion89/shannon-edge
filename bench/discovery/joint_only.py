#!/usr/bin/env python3
"""Anomalies visible only in the relationship between channels (pre-registered in
bench/discovery/joint_only_preregistration.md).

For each labelled event, decide whether it is visible to a per-channel (local) test, only to a
cross-channel (joint) test, or to neither. Both tests use frozen KT context models trained on the
unlabelled training part, and an empirical null of same-length unlabelled training windows.

Usage: joint_only.py ESA-Mission1.zip ESA-Mission2.zip [--marginal]

--marginal is a post-hoc diagnostic added after the pre-registered run: each channel gets a second
local test, the frozen frequency cost of its levels, -log2 P(y_t) (Bonferroni over 2C local tests).
"""

import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import fisher_exact

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from anomaly_esaadb import load  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "results" / "data"
Q = 32
ALPHA = 0.01
NNULL = 19999
MARGINAL = "--marginal" in sys.argv  # post hoc (not pre-registered): local tests also check the level frequencies
SPECS = [("ESA-Mission1", range(41, 47), "2006-10-01"), ("ESA-Mission2", range(18, 29), "2001-07-01")]


def frozen_cost(y, ctx, nctx, fit):
    """-log2 P(y_t | ctx_t) under KT counts fitted on the samples where fit is True."""
    counts = np.zeros((nctx, Q))
    np.add.at(counts, (ctx[fit], y[fit]), 1)
    p = (counts + 0.5) / (counts.sum(1, keepdims=True) + 0.5 * Q)
    return -np.log2(p[ctx, y])


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def mission(zp, name, chans, val, rng):
    z = zipfile.ZipFile(zp)
    lab = pd.read_csv(io.BytesIO(z.read(f"{name}/labels.csv")))
    typ = pd.read_csv(io.BytesIO(z.read(f"{name}/anomaly_types.csv")))
    lab = lab[lab.Channel.isin([f"channel_{c}" for c in chans])].merge(typ, on="ID")
    lab = lab[lab.Category != "Communication Gap"]
    for c in ("StartTime", "EndTime"):
        lab[c] = pd.to_datetime(lab[c]).dt.tz_localize(None)
    V = []
    for ch in chans:
        s = load(z, f"{name}/channels/channel_{ch}.zip")
        s = s[~s.index.duplicated(keep="last")].sort_index()
        V.append(s)
    idx = V[0].index.tz_localize(None) if V[0].index.tz is not None else V[0].index
    n = len(idx)
    labelled = np.zeros(n, bool)
    lab["i0"] = np.searchsorted(idx, lab.StartTime.to_numpy())
    lab["i1"] = np.maximum(np.searchsorted(idx, lab.EndTime.to_numpy(), side="right") - 1, lab.i0)
    for a, b in zip(lab.i0, lab.i1):
        labelled[a:b + 1] = True
    train = idx < pd.Timestamp(val)
    normal = train & ~labelled
    fit = normal.copy()
    fit[0] = False
    C = len(chans)
    q = []
    for s in V:
        v = s.to_numpy(np.float64)
        lo, hi = np.quantile(v[normal], 0.005), np.quantile(v[normal], 0.995)
        q.append(np.clip(((v - lo) / (hi - lo + 1e-12) * Q).astype(np.int64), 0, Q - 1))
    prev = [np.r_[x[0], x[:-1]] for x in q]
    local = [frozen_cost(q[j], prev[j], Q, fit) for j in range(C)]
    marg = [frozen_cost(q[j], np.zeros(n, np.int64), 1, fit) for j in range(C)] if MARGINAL else []
    okc = np.r_[0, np.cumsum(normal)]
    ev = lab.groupby("ID").agg(i0=("i0", "min"), i1=("i1", "max"), cls=("Class", "first"),
                               cat=("Category", "first"), loc=("Locality", "first"))
    nulls = {}
    for eid, e in ev.iterrows():
        a, b = int(e.i0), int(e.i1) + 1
        ell = b - a
        starts = np.nonzero(okc[ell:] - okc[:-ell] == ell)[0] if ell < n else np.array([], int)
        if len(starts) >= 100:
            nulls[eid] = (a, b, ell, rng.choice(starts, NNULL, replace=len(starts) < NNULL))
    pl = {eid: [] for eid in nulls}
    pj = {eid: [] for eid in nulls}

    def score(cost, out):
        cs = np.r_[0.0, np.cumsum(cost)]
        for eid, (a, b, ell, ns) in nulls.items():
            obs = (cs[b] - cs[a]) / ell
            nul = (cs[ns + ell] - cs[ns]) / ell
            out[eid].append((1 + np.sum(nul >= obs)) / (1 + NNULL))

    for j in range(C):
        score(local[j], pl)
    for j in range(len(marg)):
        score(marg[j], pl)
    for i in range(C):
        for j in range(C):
            if i != j:
                score(frozen_cost(q[j], prev[j] * Q + q[i], Q * Q, fit) - local[j], pj)
    rows = []
    for eid, e in ev.iterrows():
        base = dict(mission=name, ID=eid, length=int(e.i1 - e.i0 + 1), cls=e["cls"], cat=e["cat"], loc=e["loc"])
        if eid not in nulls:
            rows.append(dict(base, verdict="untestable"))
            continue
        vis_l = min(pl[eid]) <= ALPHA / len(pl[eid])
        vis_j = min(pj[eid]) <= ALPHA / (C * (C - 1))
        verdict = "local" if vis_l else ("joint-only" if vis_j else "invisible")
        rows.append(dict(base, verdict=verdict, min_p_local=min(pl[eid]), min_p_joint=min(pj[eid])))
    return pd.DataFrame(rows)


def main():
    rng = np.random.default_rng(0)
    d = pd.concat([mission(zp, name, ch, val, rng) for zp, (name, ch, val) in zip(sys.argv[1:3], SPECS)]).reset_index(drop=True)
    d.to_csv(DATA / ("joint_only_esa_marginal.csv" if MARGINAL else "joint_only_esa.csv"), index=False)
    ok = True
    for m, g in d.groupby("mission"):
        t = g[g.verdict != "untestable"]
        k, nn = int((t.verdict == "joint-only").sum()), len(t)
        lo, hi = wilson(k, nn)
        ok &= lo >= 0.05
        print(f"{m}: {len(g)} events, {nn} testable; local {int((t.verdict == 'local').sum())}, joint-only {k}, "
              f"invisible {int((t.verdict == 'invisible').sum())}; joint-only share {k / max(nn, 1):.3f} "
              f"(95% CI {lo:.3f}-{hi:.3f})")
    print(f"J1 (Wilson lower bound >= 0.05 on both missions): {'HOLDS' if ok else 'REFUTED'}")
    t = d[(d.verdict != "untestable") & d["loc"].isin(["Local", "Global"])]
    tab = [[int(((t["loc"] == L) & (t.verdict == "joint-only")).sum()), int(((t["loc"] == L) & (t.verdict != "joint-only")).sum())]
           for L in ("Local", "Global")]
    p = fisher_exact(tab, alternative="greater").pvalue
    sh = [r[0] / max(sum(r), 1) for r in tab]
    print(f"J2 joint-only share Local {sh[0]:.3f} ({tab[0][0]}/{sum(tab[0])}) vs Global {sh[1]:.3f} ({tab[1][0]}/{sum(tab[1])}), "
          f"one-sided Fisher p = {p:.4g}: {'HOLDS' if (p < 0.05) else 'REFUTED'}")
    print("\nBy mission and class:")
    print(pd.crosstab([d.mission, d.cls], d.verdict).to_string())
    print("\nBy mission and locality:")
    print(pd.crosstab([d.mission, d["loc"]], d.verdict).to_string())


if __name__ == "__main__":
    main()
