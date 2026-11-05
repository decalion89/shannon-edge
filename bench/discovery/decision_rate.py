#!/usr/bin/env python3
"""Predict the decision's bandwidth need from the normal prefix alone (pre-registered in
bench/discovery/decision_rate_preregistration.md). Computes the four prefix features for every
TSB-AD-U tuning and evaluation series, fits OLS on tuning, and reports the test once.

Usage: decision_rate.py TSB-AD-U.zip TSB-AD-checkout
"""

import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tsbad_dimension import quantised_cost  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "results" / "data"
QS = (5, 10, 20, 30, 50)


def features(z, name, L):
    root = next(n.split("/")[0] for n in z.namelist() if n.endswith(name))
    df = pd.read_csv(io.BytesIO(z.read(f"{root}/{name}"))).dropna()
    x = df.iloc[:, 0].to_numpy(float)
    tr = int(name.split(".")[0].split("_")[-3])
    p = x[: max(tr, 2)]
    lo, hi = float(p.min()), float(p.max())
    c = quantised_cost(p, lo, hi, 8)
    f1 = float(c.mean())
    L = max(int(L), 1)
    w = pd.Series(c).rolling(L).mean().dropna().to_numpy()
    f2 = float(np.quantile(w, 0.99) - np.quantile(w, 0.50)) if len(w) else 0.0
    f3 = float((np.diff(p) == 0).mean()) if len(p) > 1 else 0.0
    return dict(f1=f1, f2=f2, f3=f3, f4=float(np.log2(L)), loglen=float(np.log2(len(x))))


def table(split, z):
    d = pd.read_csv(DATA / f"tsbad_cascade_{split}.csv").drop_duplicates("file")
    d = d[d.subpca >= 0.05].copy()
    d["AUR"] = np.mean([np.clip(d[f"cascade_{q}"] / d.subpca, 0, 1.5) for q in QS], axis=0)
    fs = [features(z, f, L) for f, L in zip(d.file, d.L)]
    return pd.concat([d.reset_index(drop=True), pd.DataFrame(fs)], axis=1)


def main():
    zp = sys.argv[1]
    z = zipfile.ZipFile(zp)
    tun, ev = table("tuning", z), table("eval", z)
    cols = ["f1", "f2", "f3", "f4"]
    X = np.column_stack([np.ones(len(tun))] + [tun[c] for c in cols])
    w = np.linalg.lstsq(X, tun.AUR, rcond=None)[0]
    print(f"tuning: {len(tun)} series; fit AUR = " + " + ".join(f"{v:.3f}*{n}" for v, n in zip(w, ["1"] + cols)))
    pred = np.column_stack([np.ones(len(ev))] + [ev[c] for c in cols]) @ w
    rho, p = spearmanr(pred, ev.AUR)
    p1 = p / 2 if rho > 0 else 1 - p / 2
    rb, pb = spearmanr(ev.loglen, ev.AUR)
    print(f"evaluation: {len(ev)} series (subpca >= 0.05)")
    print(f"  model:    Spearman rho = {rho:.3f}, one-sided p = {p1:.3g}  (success needs rho >= 0.30, p < 0.01)")
    print(f"  baseline: log2(length) rho = {rb:.3f}")
    print(f"  VERDICT: {'SUPPORTED' if (rho >= 0.30 and p1 < 0.01 and rho > rb) else 'REFUTED'}")
    for c in cols:
        r, _ = spearmanr(ev[c], ev.AUR)
        print(f"  single feature {c}: rho = {r:.3f}")
    out = DATA / "decision_rate_eval.csv"
    ev.assign(pred=pred)[["file", "AUR", "pred"] + cols + ["loglen"]].to_csv(out, index=False)
    tun[["file", "AUR"] + cols + ["loglen"]].to_csv(DATA / "decision_rate_tuning.csv", index=False)


if __name__ == "__main__":
    main()
