#!/usr/bin/env python3
"""Is there an "Omori law" for surprise after an anomaly's onset?

    python3 bench/analysis/aftershock.py ESA-MissionN.zip CHANNEL... | --ucr FOLDER

Align every labelled event at its first labelled sample (lag 0). For lags
-200..+2000 samples, average the excess surprise (cost minus the channel's
median cost) over events. Fit the post-onset decay, lags 1..2000, two ways:
* power law: excess ~ k (lag + c)^-p, with c in {1, 3, 10, 30};
* exponential: excess ~ k exp(-lag / tau).
Both are fitted on the log of the positive mean excess. Report the exponent
p, the time constant tau and the residuals of each fit.
"""
import glob
import io
import os
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import anomaly_esaadb as A  # noqa: E402
from ucr_anomaly import costs as ucr_costs  # noqa: E402

PRE, POST = 200, 2000
lags = np.arange(-PRE, POST + 1)
acc, cnt = np.zeros(len(lags)), np.zeros(len(lags))


def add(cost, starts):
    med = np.median(cost)
    ex = cost - med
    for s0 in starts:
        lo, hi = s0 - PRE, s0 + POST + 1
        a, b = max(lo, 0), min(hi, len(ex))
        if b <= a:
            continue
        acc[a - lo:b - lo] += ex[a:b]
        cnt[a - lo:b - lo] += 1


if sys.argv[1] == "--ucr":
    name = "UCR"
    for f in sorted(glob.glob(os.path.join(sys.argv[2], "*.txt"))):
        tr, b, e = (int(g) for g in re.search(r"_(\d+)_(\d+)_(\d+)\.txt$", f).groups())
        add(ucr_costs(np.loadtxt(f).ravel()), [b - 1])
else:
    z = zipfile.ZipFile(sys.argv[1])
    root = name = next(n.split("/")[0] for n in z.namelist() if n.endswith("labels.csv"))
    lab = pd.read_csv(io.BytesIO(z.read(f"{root}/labels.csv")))
    typ = pd.read_csv(io.BytesIO(z.read(f"{root}/anomaly_types.csv")))
    lab["StartTime"] = pd.to_datetime(lab["StartTime"]).dt.tz_localize(None)
    lab = lab.merge(typ[["ID", "Category"]], on="ID")
    lab = lab[lab.Category.isin(["Anomaly", "Rare Event"])]
    for c in sys.argv[2:]:
        ch = f"channel_{c}"
        s = A.load(z, f"{root}/channels/{ch}.zip")
        ts = s.index.values.astype("datetime64[ns]")
        st = np.searchsorted(ts, lab[lab.Channel == ch]["StartTime"].values.astype("datetime64[ns]"))
        add(A.surprise(s), st)
m = acc / np.maximum(cnt, 1)
post = lags >= 1
x, y = lags[post].astype(float), m[post]
ok = y > 0
print(f"{name}: {int(cnt[PRE])} events aligned; mean excess at lag 0: {m[PRE]:.2f} bits, "
      f"lags -200..-1: {m[:PRE].mean():+.3f}, lags 1..10: {m[PRE + 1:PRE + 11].mean():+.3f}, "
      f"100..200: {m[PRE + 100:PRE + 201].mean():+.3f}, 1000..2000: {m[PRE + 1000:].mean():+.3f}")
best = None
for c in (1, 3, 10, 30):
    A_ = np.c_[np.ones(ok.sum()), -np.log(x[ok] + c)]
    w, res, *_ = np.linalg.lstsq(A_, np.log(y[ok]), rcond=None)
    r = float(np.mean((A_ @ w - np.log(y[ok])) ** 2))
    if best is None or r < best[0]:
        best = (r, c, w[1])
A_ = np.c_[np.ones(ok.sum()), -x[ok]]
w, *_ = np.linalg.lstsq(A_, np.log(y[ok]), rcond=None)
re_ = float(np.mean((A_ @ w - np.log(y[ok])) ** 2))
print(f"  power law: p = {best[2]:.2f} (c = {best[1]}), log-MSE {best[0]:.3f};  exponential: tau = {1 / w[1]:.0f} samples, "
      f"log-MSE {re_:.3f};  positive lags used: {ok.sum()}/{len(y)}")
