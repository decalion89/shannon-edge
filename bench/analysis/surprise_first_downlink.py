#!/usr/bin/env python3
"""Surprise-first downlink: with a daily budget smaller than what the
spacecraft produces, which anomalies reach the ground the same day?

    python3 bench/analysis/surprise_first_downlink.py ESA-MissionN.zip SPLIT CHANNEL...

Each channel is compressed by the flight profile in packets of 256 samples
(size = the sum of the samples' costs). Each test day may send only a
fraction c of that day's compressed bytes. Policies:
* fifo: packets in time order until the budget runs out (today's practice);
* surprise-first: packets in decreasing size until the budget runs out.
An event counts as delivered that day if a packet that overlaps it on one
of its labelled channels was sent.
"""
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import anomaly_esaadb as A  # noqa: E402

zp, split, chans = sys.argv[1], np.datetime64(sys.argv[2]), sys.argv[3:]
z = zipfile.ZipFile(zp)
root = next(n.split("/")[0] for n in z.namelist() if n.endswith("labels.csv"))
lab = pd.read_csv(io.BytesIO(z.read(f"{root}/labels.csv")))
typ = pd.read_csv(io.BytesIO(z.read(f"{root}/anomaly_types.csv")))
for c in ("StartTime", "EndTime"):
    lab[c] = pd.to_datetime(lab[c]).dt.tz_localize(None)
lab = lab.merge(typ[["ID", "Category"]], on="ID")
names = [f"channel_{c}" for c in chans]
lab = lab[lab.Category.isin(["Anomaly", "Rare Event"]) & lab.Channel.isin(names) & (lab.EndTime > pd.Timestamp(split))]
rows = []
for ci, ch in enumerate(names):
    s = A.load(z, f"{root}/channels/{ch}.zip")
    c = A.surprise(s)
    ts = s.index.values.astype("datetime64[ns]")
    n = len(c) // 256 * 256
    bits = c[:n].reshape(-1, 256).sum(1)
    st, en = ts[:n:256], ts[255:n:256]
    keep = st >= split
    rows.append(pd.DataFrame({"bits": bits[keep], "start": st[keep], "end": en[keep], "ch": ch}))
pk = pd.concat(rows, ignore_index=True)
pk["day"] = pk["start"].values.astype("datetime64[D]")
ev = [(r.ID, r.Category, r.Channel, np.datetime64(r.StartTime), np.datetime64(r.EndTime)) for r in lab.itertuples()]
cats = {e[0]: e[1] for e in ev}
print(f"{root}: {len(pk):,} test packets over {pk['day'].nunique()} days, {len(cats)} events")
print("| Daily budget (share of compressed bytes) | Policy | Anomalies delivered | Rare events delivered |")
print("|---:|---|---:|---:|")
for c in (0.05, 0.10, 0.25):
    for pol in ("fifo", "surprise-first"):
        sent = np.zeros(len(pk), bool)
        for _, g in pk.groupby("day"):
            budget = c * g["bits"].sum()
            order = g.index.values if pol == "fifo" else g.sort_values("bits", ascending=False).index.values
            cum = np.cumsum(pk.loc[order, "bits"].values)
            sent[order[cum <= budget]] = True
        sp = pk[sent]
        got = set()
        by_ch = {ch: (g["start"].values, g["end"].values) for ch, g in sp.groupby("ch")}
        for eid, cat, ch, a, e in ev:
            if ch in by_ch:
                s_, e_ = by_ch[ch]
                if ((s_ <= e) & (e_ >= a)).any():
                    got.add(eid)
        na = sum(1 for k in got if cats[k] == "Anomaly"); ta = sum(1 for v in cats.values() if v == "Anomaly")
        nr = sum(1 for k in got if cats[k] == "Rare Event"); tr = sum(1 for v in cats.values() if v == "Rare Event")
        print(f"| {100 * c:g}% | {pol} | {na}/{ta} | {nr}/{tr} |")
