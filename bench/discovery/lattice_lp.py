#!/usr/bin/env python3
"""Linear prediction on the noise-scale lattice (pre-registered in
bench/discovery/lattice_lp_preregistration.md).

For each TSB-AD-U-Eva series with sigma > 0 and the bound held (the 297 of the Kolmogorov test):
lattice indices li (delta = robust sigma of the normal prefix, as before). Candidate predictors, all
causal on past indices: plain (no prediction, the current protocol), fixed polynomial predictors of
order 1-3 (x1, 2x1-x2, 3x1-3x2+x3) and a least-squares AR(8) fitted on the prefix. The predictor is
chosen on the normal prefix only, by the flight profile's bytes on the prefix; then the whole series'
residuals (zigzag-mapped) are coded with the flight profile. 2 bytes of side information are added.

Usage: lattice_lp.py TSB-AD-U.zip
"""

import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bit_layers import robust_sigma  # noqa: E402
from esa_edge_link import flight  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "results" / "data"
SMOOTH = {"YAHOO", "CATSv2", "MGAB", "NEK"}  # gap > +0.5 bit/sample in the Kolmogorov map


def zigzag(r):
    return np.where(r >= 0, 2 * r, -2 * r - 1)


def residuals(li, kind, ar=None):
    x = li.astype(np.int64)
    p = np.zeros_like(x)
    if kind == "o1":
        p[1:] = x[:-1]
    elif kind == "o2":
        p[1] = x[0]
        p[2:] = 2 * x[1:-1] - x[:-2]
    elif kind == "o3":
        p[1] = x[0]
        p[2] = 2 * x[1] - x[0]
        p[3:] = 3 * x[2:-1] - 3 * x[1:-2] + x[:-3]
    elif kind == "ar":
        q = len(ar)
        p[:q] = x[:q]
        X = np.stack([x[q - 1 - j:len(x) - 1 - j] for j in range(q)], 1).astype(float)
        p[q:] = np.round(X @ ar).astype(np.int64)
    return x - p


def fit_ar(x, q=8):
    x = x.astype(float)
    if len(x) < 4 * q:
        return None
    X = np.stack([x[q - 1 - j:len(x) - 1 - j] for j in range(q)], 1)
    w, *_ = np.linalg.lstsq(X, x[q:], rcond=None)
    return w


def code_bytes(z):
    if z.min() < 0 or z.max() >= 65536:
        return None
    return flight(z.astype("<u2"))[0]


def main():
    z = zipfile.ZipFile(sys.argv[1])
    kl = pd.read_csv(DATA / "kolmogorov_limit.csv")
    rows = []
    for _, r in kl.iterrows():
        root = next(n.split("/")[0] for n in z.namelist() if n.endswith(r.file))
        x = pd.read_csv(io.BytesIO(z.read(f"{root}/{r.file}"))).dropna().iloc[:, 0].to_numpy(np.float64)
        tr = max(int(r.file.split(".")[0].split("_")[-3]), 2)
        sig = robust_sigma(x[:tr])
        k = np.round((x - x[0]) / (2 * sig)).astype(np.int64)
        li = k - k.min()
        plain = code_bytes(li)
        ar = fit_ar(li[:tr])
        cands = {"plain": li[:tr]}
        for kind in ("o1", "o2", "o3"):
            cands[kind] = zigzag(residuals(li[:tr], kind))
        if ar is not None:
            cands["ar"] = zigzag(residuals(li[:tr], "ar", ar))
        pref = {kd: code_bytes(v) for kd, v in cands.items()}
        pref = {kd: b for kd, b in pref.items() if b is not None}
        best = min(pref, key=pref.get)
        if best == "plain":
            lp = plain
        else:
            lp = code_bytes(zigzag(residuals(li, best, ar)))
            if lp is None:
                best, lp = "plain", plain
        lp += 2 + (8 * 8 if best == "ar" else 0)  # side information (predictor id; AR coefficients as float64)
        rows.append(dict(file=r.file, ds=r.ds, n=r.n, predicted=r.predicted, plain_bps=8 * plain / r.n,
                         lp_bps=8 * lp / r.n, choice=best))
    d = pd.DataFrame(rows)
    d.to_csv(DATA / "lattice_lp.csv", index=False)
    red = 1 - (d.lp_bps * d.n).sum() / (d.plain_bps * d.n).sum()
    sm = d[d.ds.isin(SMOOTH)]
    drop = float((sm.plain_bps - sm.lp_bps).median())
    below0, below1 = float((d.plain_bps < d.predicted).mean()), float((d.lp_bps < d.predicted).mean())
    print(f"{len(d)} series; predictor chosen: {d.choice.value_counts().to_dict()}")
    print(f"L1 pooled reduction vs the current protocol = {100 * red:.1f}% (needs >= 10%): {'HOLDS' if red >= 0.10 else 'REFUTED'}")
    print(f"L2 smooth domains ({len(sm)} series): median drop = {drop:.3f} bit/sample (needs >= 0.5): "
          f"{'HOLDS' if drop >= 0.5 else 'REFUTED'}")
    print(f"L3 share of series below the Kolmogorov-Gaussian rate: {below0:.0%} -> {below1:.0%} (needs >= 65%): "
          f"{'HOLDS' if below1 >= 0.65 else 'REFUTED'}")
    d["gap_plain"], d["gap_lp"] = d.plain_bps - d.predicted, d.lp_bps - d.predicted
    print(d.groupby("ds")[["plain_bps", "lp_bps", "predicted", "gap_plain", "gap_lp"]].median().round(3).to_string())


if __name__ == "__main__":
    main()
