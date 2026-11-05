#!/usr/bin/env python3
"""Is the size of a compressed packet an anomaly score? (no decoding needed)

    python3 bench/analysis/packet_size_priority.py ESA-MissionN.zip SPLIT CHANNEL...

Each channel is compressed by the flight profile in packets of 256 samples
(as examples/flight_surprise.rs does). A packet's size is the sum of its
samples' costs, i.e. its payload length up to framing. In the test period,
rank the packets of all channels by size and keep the top x%. Report how
many labelled events (Anomaly / Rare Event on these channels) overlap a
kept packet, against the share of test time the kept packets cover. That
second number is what a random choice of packets would catch.
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
pk = []  # (bits, start, end, channel)
for ch in names:
    s = A.load(z, f"{root}/channels/{ch}.zip")
    c = A.surprise(s)
    ts = s.index.values.astype("datetime64[ns]")
    n = len(c) // 256 * 256
    bits = c[:n].reshape(-1, 256).sum(1)
    st, en = ts[:n:256], ts[255:n:256]
    keep = st >= split
    pk += [(b, a, e, ch) for b, a, e in zip(bits[keep], st[keep], en[keep])]
pk.sort(key=lambda x: -x[0])
ev = lab.groupby("ID").agg(s=("StartTime", "min"), e=("EndTime", "max"), cat=("Category", "first"))
span = sum((e - a) for _, a, e, _ in pk) / np.timedelta64(1, "s")
print(f"{root}: {len(pk):,} test packets, {len(ev)} test events")
print("| Top packets by size | Share of test time covered | Events overlapping (Anomaly / Rare Event) | Same number of random packets (mean of 20) |")
print("|---:|---:|---|---|")
rng = np.random.default_rng(0)


def overlaps(sel):
    a_ = np.array([t[1] for t in sel]); e_ = np.array([t[2] for t in sel])
    out = {"Anomaly": 0, "Rare Event": 0}
    for r in ev.itertuples():
        if ((a_ <= np.datetime64(r.e)) & (e_ >= np.datetime64(r.s))).any():
            out[r.cat] += 1
    return out
for frac in (0.001, 0.01, 0.05):
    top = pk[: max(1, int(len(pk) * frac))]
    cover = sum((e - a) for _, a, e, _ in top) / np.timedelta64(1, "s") / span
    a_ = np.array([t[1] for t in top]); e_ = np.array([t[2] for t in top])
    hit = {cat: 0 for cat in ("Anomaly", "Rare Event")}
    tot = {cat: int((ev.cat == cat).sum()) for cat in hit}
    for r in ev.itertuples():
        if ((a_ <= np.datetime64(r.e)) & (e_ >= np.datetime64(r.s))).any():
            hit[r.cat] += 1
    rnd = [overlaps([pk[i] for i in rng.choice(len(pk), len(top), replace=False)]) for _ in range(20)]
    ra = np.mean([r["Anomaly"] for r in rnd]); rr = np.mean([r["Rare Event"] for r in rnd])
    print(f"| {100 * frac:g}% | {100 * cover:.2f}% | {hit['Anomaly']}/{tot['Anomaly']} / {hit['Rare Event']}/{tot['Rare Event']} | "
          f"{ra:.1f} / {rr:.1f} |")
