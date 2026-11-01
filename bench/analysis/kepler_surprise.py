#!/usr/bin/env python3
"""Planet transits as anomalies: the flight profile's surprise on Kepler
light curves (NASA, public domain; MAST long-cadence PDCSAP flux).

    python3 bench/analysis/kepler_surprise.py LC.fits [--period P --t0 BKJD --halfdur D]

Flux is normalised by its median and quantised in units of the star's
point-to-point noise (robust: 1.4826 * MAD of differences / sqrt 2). That is
the natural integer code for a noisy brightness. Rank codes, used elsewhere,
are meaningless here because almost every float value is distinct. Then:
* with an ephemeris: mean and peak surprise in transit against overall;
* without one: transits are found as points 0.5% below the median, and the
  peak surprise around each transit's onset is listed in time order (does
  the model get used to them?).
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from astropy.io import fits

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import anomaly_esaadb as A  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("fits")
ap.add_argument("--period", type=float)
ap.add_argument("--t0", type=float)
ap.add_argument("--halfdur", type=float, default=0.14)
a = ap.parse_args()
h = fits.open(a.fits)
d = h[1].data
t, f = d["TIME"], d["PDCSAP_FLUX"]
ok = np.isfinite(t) & np.isfinite(f)
t, f = t[ok], f[ok] / np.median(f[ok])
noise = 1.4826 * np.median(np.abs(np.diff(f))) / np.sqrt(2)
q = np.round((f - 1) / noise).astype(np.int64)
q -= q.min()
c = A.surprise(pd.Series(q.astype(np.float32)))
print(f"{h[0].header.get('OBJECT')} Q{h[0].header.get('QUARTER')}: {len(f)} points, noise {noise * 1e6:.0f} ppm, "
      f"median surprise {np.median(c):.2f}, 99.9th pct {np.percentile(c, 99.9):.1f} bits")
if a.period:
    ph = ((t - a.t0) / a.period + 0.5) % 1 - 0.5
    intr = np.abs(ph * a.period) < a.halfdur
    print(f"  in transit ({intr.sum()} points): flux {(f[intr].mean() - 1) * 1e6:+.0f} ppm, surprise mean "
          f"{c[intr].mean():.2f} vs {c.mean():.2f}, peak {c[intr].max():.1f}")
    top = np.argsort(-c)[:10]
    print("  top-10 surprise times:", np.round(t[top], 2).tolist())
else:
    dip = f < 0.995
    st = np.nonzero(dip & ~np.r_[False, dip[:-1]])[0]
    st = [s for i, s in enumerate(st) if i == 0 or t[s] - t[st[i - 1]] > 1.0]
    print(f"  {len(st)} transits; peak surprise at each onset (+-2 points), in order:",
          [round(float(c[max(0, s - 2):s + 3].max()), 1) for s in st])
