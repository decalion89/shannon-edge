#!/usr/bin/env python3
"""Does Mission 1's class_7 recur with a fixed period? (pre-registered in
bench/discovery/class7_period_preregistration.md)

Period and mean phase are fixed from the 20 training onsets (before 2006-10-01): P = 34.85 days, scanned on
10-200 days. Test: the onsets from 2007-01-01 (never examined), V-test (Rayleigh test with a known
direction) of their phases against the training mean phase.

Usage: class7_period.py ESA-Mission1.zip
"""
import io
import sys
import zipfile

import numpy as np
import pandas as pd

P = 34.85
EPOCH = pd.Timestamp("2000-01-01")


def onsets(z):
    lab = pd.read_csv(io.BytesIO(z.read("ESA-Mission1/labels.csv")))
    typ = pd.read_csv(io.BytesIO(z.read("ESA-Mission1/anomaly_types.csv")))
    lab = lab.merge(typ, on="ID")
    lab["StartTime"] = pd.to_datetime(lab.StartTime).dt.tz_localize(None)
    g = lab.groupby("ID").agg(t0=("StartTime", "min"), cls=("Class", "first"))
    return g[g.cls == "class_7"].t0


def phases(t):
    return 2 * np.pi * (((t - EPOCH).dt.total_seconds().values / 86400) / P % 1)


def main():
    t = onsets(zipfile.ZipFile(sys.argv[1]))
    tr, te = t[t < pd.Timestamp("2006-10-01")], t[t >= pd.Timestamp("2007-01-01")]
    mu = np.angle(np.exp(1j * phases(tr)).mean())
    ph = phases(te)
    n = len(ph)
    V = np.sum(np.cos(ph - mu))
    u = V * np.sqrt(2.0 / n)
    from scipy.stats import norm
    p = norm.sf(u)
    R = np.abs(np.exp(1j * ph).mean())
    print(f"training onsets {len(tr)}, mean phase {mu / (2 * np.pi) % 1:.3f} cycles; test onsets {n}")
    print(f"test: resultant length R = {R:.3f}; mean phase {np.angle(np.exp(1j * ph).mean()) / (2 * np.pi) % 1:.3f}")
    print(f"C1 V-test toward the training phase: u = {u:.2f}, one-sided p = {p:.3g} (needs p < 0.01): "
          f"{'HOLDS' if p < 0.01 else 'REFUTED'}")
    print("test phases (cycles):", np.round(np.sort(ph / (2 * np.pi)), 2))


if __name__ == "__main__":
    main()
