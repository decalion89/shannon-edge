#!/usr/bin/env python3
"""Census of one-sample spikes across a mission: x[t] differs from x[t-1]
and x[t+1] == x[t-1]. Size is in local quantisation steps (smallest positive
gap between distinct values within +-5,000 samples). Reports per-channel
counts, the size histogram, coincidences across channels (spikes within
+-2 s on different channels), and time-of-day / interval structure.

    python3 bench/analysis/spike_census.py ESA-MissionN.zip CHANNEL...
"""
import collections
import sys
import zipfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import anomaly_esaadb as A  # noqa: E402

zp, chans = sys.argv[1], sys.argv[2:]
z = zipfile.ZipFile(zp)
root = next(n.split("/")[0] for n in z.namelist() if n.endswith("labels.csv"))
allsp = []  # (time ns, channel, steps)
for c in chans:
    s = A.load(z, f"{root}/channels/channel_{c}.zip")
    s = s[~s.index.duplicated(keep="last")]
    v = s.to_numpy(np.float64)
    ts = s.index.values.astype("datetime64[ns]").astype(np.int64)
    i = np.nonzero((v[1:-1] != v[:-2]) & (v[2:] == v[:-2]))[0] + 1
    if len(i) == 0:
        continue
    u = np.unique(v)
    gaps = np.diff(u)
    step = np.median(gaps[gaps > 0][: 10000]) if (gaps > 0).any() else 1.0
    steps = np.round(np.abs(v[i] - v[i - 1]) / step).astype(np.int64)
    allsp += [(int(t), int(c), int(k)) for t, k in zip(ts[i], steps)]
    big = steps >= 8
    print(f"channel {c}: {len(i):,} one-sample spikes, {big.sum():,} of >= 8 steps; "
          f"top sizes {collections.Counter(steps[big].tolist()).most_common(5)}", flush=True)
sp = np.array(allsp, dtype=np.int64)
if len(sp) == 0:
    sys.exit()
sp = sp[np.argsort(sp[:, 0])]
big = sp[sp[:, 2] >= 8]
print(f"\nall channels: {len(sp):,} spikes, {len(big):,} of >= 8 steps")
print("size histogram (>= 8 steps):", sorted(collections.Counter(big[:, 2].tolist()).most_common(12)))
# coincidences: big spikes on >= 2 distinct channels within +-2 s
t = big[:, 0]
j = 0
groups = []
for k in range(len(t)):
    while t[k] - t[j] > 2_000_000_000:
        j += 1
    chs = set(big[j:k + 1, 1].tolist())
    if len(chs) >= 2:
        groups.append((t[k], tuple(sorted(chs))))
print(f"big spikes coinciding (+-2 s) across >= 2 channels: {len(groups)}; examples:",
      [(str(np.datetime64(g[0], 'ns'))[:19], g[1]) for g in groups[:6]])
hours = ((big[:, 0] // 3_600_000_000_000) % 24)
print("big spikes by UTC hour:", np.bincount(hours, minlength=24).tolist())
secs = (big[:, 0] // 1_000_000_000) % 60
print("big spikes by second-of-minute (top 6):", collections.Counter(secs.tolist()).most_common(6))
