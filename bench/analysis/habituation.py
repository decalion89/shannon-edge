#!/usr/bin/env python3
"""Does the online model get used to anomalies that recur?

    python3 bench/analysis/habituation.py ESA-MissionN.zip CHANNEL...

For every labelled event touching the given channels: the peak surprise
over its labelled channels and interval, in bits above the channel's code
width b (the Kraft margin it reached). Events are grouped by ESA class and
ordered in time. Reports, per class with at least 5 occurrences, the peak
margin of the first and later occurrences, and the Spearman correlation
between occurrence index and peak margin.
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
types = pd.read_csv(io.BytesIO(z.read(f"{root}/anomaly_types.csv")))
for c in ("StartTime", "EndTime"):
    lab[c] = pd.to_datetime(lab[c]).dt.tz_localize(None)
names = [f"channel_{c}" for c in chans]
lab = lab[lab["Channel"].isin(names)].merge(types[["ID", "Class", "Category"]], on="ID")
peak = {}
for ch in names:
    s = A.load(z, f"{root}/channels/{ch}.zip")
    b = max(1, (min(len(np.unique(s.to_numpy().astype(np.float32))), 65536) - 1).bit_length())
    cost = A.surprise(s)
    ts = s.index.values.astype("datetime64[ns]")
    for r in lab[lab["Channel"] == ch].itertuples():
        i, j = np.searchsorted(ts, np.datetime64(r.StartTime)), np.searchsorted(ts, np.datetime64(r.EndTime), "right")
        j = max(j, i + 1)
        v = float(cost[i:j].max()) - b if i < len(cost) else np.nan
        peak[r.ID] = max(peak.get(r.ID, -np.inf), v)
    del s, cost
ev = lab.groupby("ID").agg(start=("StartTime", "min"), cls=("Class", "first"), cat=("Category", "first")).reset_index()
ev["peak"] = ev["ID"].map(peak)
ev = ev.dropna().sort_values("start")
print(f"{root}, channels {' '.join(chans)}: {len(ev)} events\n")
print("| Class | Category | Occurrences | Peak margin, first 3 (bits above b) | Peak margin, rest (median) | Spearman(index, peak) |")
print("|---|---|---:|---|---:|---:|")
for cls, g in ev.groupby("cls"):
    if len(g) < 5:
        continue
    p = g["peak"].to_numpy()
    rho = pd.Series(np.arange(len(p))).corr(pd.Series(p), method="spearman")
    print(f"| {cls} | {g['cat'].iloc[0]} | {len(g)} | {', '.join(f'{v:+.1f}' for v in p[:3])} | "
          f"{np.median(p[3:]):+.1f} | {rho:+.2f} |")
