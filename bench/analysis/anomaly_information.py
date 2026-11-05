#!/usr/bin/env python3
"""How much of a mission's information is in its anomalies?

    python3 bench/analysis/anomaly_information.py ESA-MissionN.zip CHANNEL...

For each channel: the flight profile's online cost (bits) of every sample,
summed inside labelled events of that channel (by category) and outside
them. Reports the share of time (samples) and the share of information
(bits) that events take, and their ratio: the information concentration.
"""
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import anomaly_esaadb as A  # noqa: E402

zp, chans = sys.argv[1], sys.argv[2:]
z = zipfile.ZipFile(zp)
root = next(n.split("/")[0] for n in z.namelist() if n.endswith("labels.csv"))
lab = pd.read_csv(io.BytesIO(z.read(f"{root}/labels.csv")))
typ = pd.read_csv(io.BytesIO(z.read(f"{root}/anomaly_types.csv")))
for c in ("StartTime", "EndTime"):
    lab[c] = pd.to_datetime(lab[c]).dt.tz_localize(None)
lab = lab.merge(typ[["ID", "Category"]], on="ID")
tot = {"samples": 0, "bits": 0.0}
cat = {}
for c in chans:
    ch = f"channel_{c}"
    s = A.load(z, f"{root}/channels/{ch}.zip")
    cost = A.surprise(s)
    ts = s.index.values.astype("datetime64[ns]")
    tot["samples"] += len(cost)
    tot["bits"] += float(cost.sum())
    for k, g in lab[lab.Channel == ch].groupby("Category"):
        m = np.zeros(len(ts), bool)
        for r in g.itertuples():
            a, e = np.searchsorted(ts, np.datetime64(r.StartTime)), np.searchsorted(ts, np.datetime64(r.EndTime), "right")
            m[a:max(e, a + 1)] = True
        d = cat.setdefault(k, {"samples": 0, "bits": 0.0, "peak": []})
        d["samples"] += int(m.sum())
        d["bits"] += float(cost[m].sum())
    del s, cost
print(f"{root}, {len(chans)} channels: {tot['samples']:,} samples, {tot['bits'] / 8e6:,.2f} MB of information")
print("| Category | Share of samples | Share of information (bits) | Concentration (info share / time share) | Bits per sample inside | Bits per sample overall |")
print("|---|---:|---:|---:|---:|---:|")
for k, d in sorted(cat.items()):
    ts_ = d["samples"] / tot["samples"]
    is_ = d["bits"] / tot["bits"]
    print(f"| {k} | {100 * ts_:.3f}% | {100 * is_:.3f}% | {is_ / ts_ if ts_ else float('nan'):.1f}x | "
          f"{d['bits'] / max(d['samples'], 1):.2f} | {tot['bits'] / tot['samples']:.2f} |")
