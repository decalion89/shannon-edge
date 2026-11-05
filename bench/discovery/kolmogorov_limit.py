#!/usr/bin/env python3
"""Does Kolmogorov's 1956 reverse water-filling predict the measured cost of noise-scale telemetry?
(pre-registered in bench/discovery/kolmogorov_limit_preregistration.md)

For each TSB-AD-U-Eva series with sigma > 0 and the error bound held (bit_layers run):
* measured rate: 8 * structure_B / n bits per sample (flight profile on the 1-sigma lattice indices);
* predicted rate: the Gaussian rate-distortion function of a stationary process with the spectrum S(f)
  of the series' normal prefix, at the mean-squared error of the lattice, D = delta^2 / 3:
      R = mean_f max(0, 1/2 log2(S(f) / theta)),  with  mean_f min(theta, S(f)) = D
  (Kolmogorov 1956; Berger 1971, Theorem 4.5.3). S(f) by Welch's method (segments of 256, Hann,
  linear detrend) on the normal prefix, normalised so that its mean equals the prefix variance.

Usage: kolmogorov_limit.py TSB-AD-U.zip
"""

import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import welch
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bit_layers import robust_sigma  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "results" / "data"


def waterfill_rate(S, D):
    """Reverse water-filling: mean over frequencies of max(0, 0.5 log2(S/theta)) with mean(min(theta,S)) = D."""
    S = np.maximum(S, 1e-300)
    if D >= S.mean():
        return 0.0
    lo, hi = 0.0, S.max()
    for _ in range(200):
        th = 0.5 * (lo + hi)
        if np.minimum(th, S).mean() < D:
            lo = th
        else:
            hi = th
    th = 0.5 * (lo + hi)
    return float(np.mean(np.maximum(0.0, 0.5 * np.log2(S / th))))


def main():
    z = zipfile.ZipFile(sys.argv[1])
    bl = pd.read_csv(DATA / "bit_layers_tsbad.csv")
    u = bl[(bl.collection == "U") & (bl.channels_bound_held == 1)].copy()
    rows = []
    for _, r in u.iterrows():
        root = next(n.split("/")[0] for n in z.namelist() if n.endswith(r.file))
        df = pd.read_csv(io.BytesIO(z.read(f"{root}/{r.file}"))).dropna()
        x = df.iloc[:, 0].to_numpy(np.float64)
        tr = int(r.file.split(".")[0].split("_")[-3])
        p = x[: max(tr, 2)]
        sig = robust_sigma(p)
        nper = min(256, len(p))
        f, S = welch(p, nperseg=nper, window="hann", detrend="linear", return_onesided=False, scaling="density")
        S = S * (np.var(p) / S.mean()) if S.mean() > 0 else S
        D = sig ** 2 / 3.0
        pred = waterfill_rate(S, D)
        meas = 8.0 * r.structure_B / r.n
        rows.append(dict(file=r.file, ds=r.file.split("_")[1], n=r.n, prefix=len(p), sigma=sig, predicted=pred,
                         measured=meas))
    d = pd.DataFrame(rows)
    d.to_csv(DATA / "kolmogorov_limit.csv", index=False)
    rho, p = spearmanr(d.predicted, d.measured)
    gap = d.measured - d.predicted
    print(f"{len(d)} series")
    print(f"K1 Spearman rho(predicted, measured) = {rho:.3f} (p = {p:.2g}; needs >= 0.70): "
          f"{'HOLDS' if rho >= 0.70 else 'REFUTED'}")
    med = float(gap.median())
    print(f"K2 median (measured - predicted) = {med:+.3f} bits/sample (needs within [-0.5, +0.5]): "
          f"{'HOLDS' if abs(med) <= 0.5 else 'REFUTED'}")
    print(f"   medians: predicted {d.predicted.median():.3f}, measured {d.measured.median():.3f} bits/sample; "
          f"IQR of the gap {gap.quantile(0.25):+.3f} .. {gap.quantile(0.75):+.3f}")
    print(f"   share of series where the protocol is BELOW the Gaussian limit: {(gap < 0).mean():.0%}")
    print(d.assign(gap=gap).groupby("ds").agg(n=("file", "size"), predicted=("predicted", "median"),
                                              measured=("measured", "median"), gap=("gap", "median")).round(3).to_string())


if __name__ == "__main__":
    main()
