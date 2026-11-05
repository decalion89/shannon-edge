#!/usr/bin/env python3
"""Feasibility on the development years only (2000-2006): the first class_7 event as the single
template; z-normalised distance profile (MASS) of 5-min medians of channel 14; per 6-h window the
minimum distance. How do class_7 windows rank among all windows?

Usage: oneshot_feasibility.py SCRATCH_DIR channel_14 channel_21 channel_29
(SCRATCH_DIR/esa/raw/ESA-Mission1.zip). Needs stumpy."""
import io, sys, zipfile, numpy as np, pandas as pd, stumpy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from anomaly_esaadb import load
SP = sys.argv.pop(1) if len(sys.argv) > 1 and not sys.argv[1].startswith("channel_") else "."  # dir holding esa/raw/ESA-Mission1.zip
z = zipfile.ZipFile(f"{SP}/esa/raw/ESA-Mission1.zip"); r = "ESA-Mission1"
lab = pd.read_csv(io.BytesIO(z.read(f"{r}/labels.csv"))); ty = pd.read_csv(io.BytesIO(z.read(f"{r}/anomaly_types.csv")))
for c in ("StartTime", "EndTime"): lab[c] = pd.to_datetime(lab[c]).dt.tz_localize(None)
lab = lab.merge(ty, on="ID")
END = pd.Timestamp("2007-01-01")
c7 = lab[(lab.Class == "class_7")].groupby("ID").agg(s=("StartTime", "min"), e=("EndTime", "max")).sort_values("s")
c7 = c7[c7.e < END]; first = c7.iloc[0]; rest = c7.iloc[1:]
print("template", first.name, first.s, first.e, "; other class_7 events in dev:", len(rest))
allev = lab[lab.Category != "Communication Gap"].groupby("ID").agg(s=("StartTime", "min"), e=("EndTime", "max"))
for chname in sys.argv[1:]:
    s = load(z, f"{r}/channels/{chname}.zip"); s = s[~s.index.duplicated(keep="last")].sort_index()
    x = s[:END].resample("5min").median().interpolate(limit=12)
    tmpl = x[first.s - pd.Timedelta(minutes=30):first.e + pd.Timedelta(minutes=30)].to_numpy(np.float64)
    m = len(tmpl); xv = x.to_numpy(np.float64)
    ok = np.isfinite(xv)
    xv = np.where(ok, xv, np.nanmedian(xv))
    d = stumpy.mass(tmpl, xv)
    t = x.index[: len(d)]
    dd = pd.Series(d, index=t)
    # exclude the template itself
    dd[(dd.index > first.s - pd.Timedelta(days=1)) & (dd.index < first.e + pd.Timedelta(days=1))] = np.inf
    w = dd.groupby(dd.index.floor("6h")).min()
    # window labels: class_7 window if overlaps any other class_7 event (subsequence start within [s - m*5min, e])
    lab7 = pd.Series(False, index=w.index); labany = pd.Series(False, index=w.index)
    for ev in rest.itertuples():
        lab7[(w.index >= ev.s.floor("6h") - pd.Timedelta(hours=6)) & (w.index <= ev.e)] = True
    for ev in allev.itertuples():
        labany[(w.index >= ev.s.floor("6h") - pd.Timedelta(hours=6)) & (w.index <= ev.e)] = True
    nominal = w[~labany & np.isfinite(w)]
    hits = []
    for ev in rest.itertuples():
        sel = w[(w.index >= ev.s.floor("6h") - pd.Timedelta(hours=6)) & (w.index <= ev.e)]
        hits.append(sel.min())
    hits = np.array(hits)
    print(f"{chname}: m={m} points; class_7 events: best distance median {np.median(hits):.2f}; nominal windows {len(nominal):,} distance quantiles 0.1%/1%/5%: {np.quantile(nominal, [0.001, 0.01, 0.05]).round(2)}")
    for thr in np.quantile(nominal, [0.0005, 0.001, 0.002, 0.005, 0.01]):
        print(f"  thr {thr:.2f}: class_7 found {(hits <= thr).sum()}/{len(hits)}, nominal windows below {(nominal <= thr).sum()}")
