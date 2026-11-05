#!/usr/bin/env python3
"""Information concentration of anomalies beyond spacecraft.

    python3 bench/analysis/info_concentration_ucr_ecg.py UCR_FOLDER MITDB_DIR

For each anomaly region:
* concentration = (share of the series' online bits inside the region) /
  (share of samples), with the flight profile, as for ESA;
* onset share = fraction of the region's *excess* bits (cost minus the
  series' median cost, floored at 0) carried by its 3 costliest samples.
UCR: the single labelled anomaly of each of the 250 series, in the test
part. MIT-BIH: every non-normal beat (AAMI classes), first lead, paced
records excluded, ±0.2 s around the annotation.
"""
import glob
import os
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ucr_anomaly import costs as ucr_costs  # noqa: E402


def onset_share(c, med):
    ex = np.maximum(c - med, 0)
    tot = ex.sum()
    return float(np.sort(ex)[-3:].sum() / tot) if tot > 0 else np.nan


conc, ons = [], []
for f in sorted(glob.glob(os.path.join(sys.argv[1], "*.txt"))):
    tr, b, e = (int(g) for g in re.search(r"_(\d+)_(\d+)_(\d+)\.txt$", f).groups())
    x = np.loadtxt(f).ravel()
    c = ucr_costs(x)[tr:]
    a0, a1 = b - 1 - tr, e - tr
    if a1 <= a0 or a0 < 0:
        continue
    region = c[a0:a1]
    conc.append((region.sum() / c.sum()) / (len(region) / len(c)))
    ons.append(onset_share(region, np.median(c)))
conc, ons = np.array(conc), np.array([o for o in ons if o == o])
print(f"UCR ({len(conc)} series): concentration median {np.median(conc):.2f}x "
      f"(IQR {np.percentile(conc, 25):.2f}-{np.percentile(conc, 75):.2f}); "
      f"share > 2x: {np.mean(conc > 2):.2f}; onset share (3 samples) median {np.median(ons):.2f}")

import wfdb  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ecg_kraft import AAMI, NORMAL, PACED, costs  # noqa: E402

d = Path(sys.argv[2])
tot_bits = tot_n = in_bits = in_n = 0.0
ons2 = []
for rec in [r for r in (d / "RECORDS").read_text().split() if r not in PACED]:
    r = wfdb.rdrecord(str(d / rec), physical=False)
    a = wfdb.rdann(str(d / rec), "atr")
    x = r.d_signal[:, 0].astype(np.int64)
    c, _ = costs(x)
    med = np.median(c)
    m = np.zeros(len(c), bool)
    w = int(0.2 * r.fs)
    for s, sym in zip(a.sample, a.symbol):
        if sym in AAMI and sym not in NORMAL:
            lo, hi = max(0, s - w), min(len(c), s + w)
            m[lo:hi] = True
            ons2.append(onset_share(c[lo:hi], med))
    tot_bits += c.sum(); tot_n += len(c); in_bits += c[m].sum(); in_n += m.sum()
ons2 = np.array([o for o in ons2 if o == o])
print(f"MIT-BIH (44 records): abnormal beats take {100 * in_n / tot_n:.2f}% of samples and "
      f"{100 * in_bits / tot_bits:.2f}% of bits: concentration {(in_bits / tot_bits) / (in_n / tot_n):.2f}x; "
      f"onset share (3 samples of ~144) median {np.median(ons2):.2f}")
