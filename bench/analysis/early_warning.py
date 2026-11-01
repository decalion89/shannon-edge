#!/usr/bin/env python3
"""Does the telemetry become less compressible in the days before an anomaly?

    python3 bench/analysis/early_warning.py [--gap-days=N] ESA-MissionN.zip CHANNEL...

For each labelled event of category "Anomaly" on the given channels, compare
the median surprise (flight profile, bits per sample) of its labelled
channels in the PRE window (3 days before the start, ending 1 hour before
it) with the BASE window (30 to 10 days before the start). The statistic
is log2(PRE / BASE). It is averaged over events and compared with the same
statistic at 2,000 random placebo times (same channels, no event within
30 days; --gap-days=N for missions whose events are too dense for that). The one-sided p-value is the share of placebo means, resampled
with the events' size, that are at least the observed mean.
"""
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import anomaly_esaadb as A  # noqa: E402

args = sys.argv[1:]
gap_days = 30
if args[0].startswith("--gap-days="):
    gap_days = int(args.pop(0).split("=")[1])
zp, chans = args[0], args[1:]
z = zipfile.ZipFile(zp)
root = next(n.split("/")[0] for n in z.namelist() if n.endswith("labels.csv"))
lab = pd.read_csv(io.BytesIO(z.read(f"{root}/labels.csv")))
typ = pd.read_csv(io.BytesIO(z.read(f"{root}/anomaly_types.csv")))
for c in ("StartTime", "EndTime"):
    lab[c] = pd.to_datetime(lab[c]).dt.tz_localize(None)
lab = lab.merge(typ[["ID", "Category"]], on="ID")
names = [f"channel_{c}" for c in chans]
lab = lab[lab["Channel"].isin(names)]
cost, tsd = {}, {}
for ch in names:
    s = A.load(z, f"{root}/channels/{ch}.zip")
    cost[ch] = A.surprise(s).astype(np.float32)
    tsd[ch] = s.index.values.astype("datetime64[ns]")
    del s
D = np.timedelta64(1, "D")


def stat(ch, t0):
    ts, c = tsd[ch], cost[ch]
    pre = c[np.searchsorted(ts, t0 - 3 * D):np.searchsorted(ts, t0 - np.timedelta64(1, "h"))]
    base = c[np.searchsorted(ts, t0 - 30 * D):np.searchsorted(ts, t0 - 10 * D)]
    if len(pre) < 50 or len(base) < 50:
        return np.nan
    return float(np.log2((np.median(pre) + 0.01) / (np.median(base) + 0.01)))


an = lab[lab["Category"] == "Anomaly"].groupby("ID").agg(start=("StartTime", "min"), chs=("Channel", lambda v: sorted(set(v))))
obs = []
for r in an.itertuples():
    v = [stat(ch, np.datetime64(r.start)) for ch in r.chs]
    v = [x for x in v if x == x]
    if v:
        obs.append(np.mean(v))
obs = np.array(obs)
allev = np.sort(lab["StartTime"].values.astype("datetime64[ns]"))
rng = np.random.default_rng(0)
t_lo, t_hi = max(t[0] for t in tsd.values()) + 31 * D, min(t[-1] for t in tsd.values())
plac = []
while len(plac) < 2000:
    t0 = t_lo + (t_hi - t_lo) * rng.random()
    t0 = np.datetime64(int(t0.astype(np.int64)), "ns") if not isinstance(t0, np.datetime64) else t0
    k = np.searchsorted(allev, t0)
    near = [allev[i] for i in (k - 1, k) if 0 <= i < len(allev)]
    if any(abs(t0 - e) < gap_days * D for e in near):
        continue
    ch = names[rng.integers(len(names))]
    v = stat(ch, t0)
    if v == v:
        plac.append(v)
plac = np.array(plac)
boot = np.array([rng.choice(plac, len(obs)).mean() for _ in range(10000)])
print(f"{root}, channels {' '.join(chans)}: {len(obs)} anomalies with data")
print(f"  log2(pre/base) mean over anomalies {obs.mean():+.3f} (median {np.median(obs):+.3f}); "
      f"placebo mean {plac.mean():+.3f} (sd {plac.std():.3f})")
print(f"  share of anomalies with pre > base: {np.mean(obs > 0):.2f} (placebo {np.mean(plac > 0):.2f})")
print(f"  one-sided p (placebo means >= observed): {np.mean(boot >= obs.mean()):.4f}")
