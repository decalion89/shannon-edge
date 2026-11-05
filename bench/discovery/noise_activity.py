#!/usr/bin/env python3
"""Replication: does fine-scale activity in the discarded noise detect anomalies the on-board surprise
detector misses? (pre-registered in bench/discovery/noise_activity_preregistration.md)

Statistic of a window: A = mean over the window of sum_c (d_c / s_c)^2, with d_c the sample-to-sample
increment of channel c and s_c its training standard deviation, divided by the training mean of the same.
Events: labelled events touching the set's channels, starting in the test period (communication gaps
excluded, windows of >= 2 samples). Controls: one unlabelled test window of the same length per event
(seed 0). Missed: no on-board Kraft alarm (esa_edge_link.py rule) on the set's channels in the window.

Usage: noise_activity.py ESA-Mission1.zip ESA-Mission2.zip
"""

import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from anomaly_esaadb import load  # noqa: E402
from esa_edge_link import flight, to_codes  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "results" / "data"
SETS = [("M2-18-20", "ESA-Mission2", [18, 19, 20], "2001-07-01", "2001-10-01"),
        ("M1-group4", "ESA-Mission1", [14, 21, 29, 30, 38], "2006-10-01", "2007-01-01")]


def auc_p(a, b):
    r = mannwhitneyu(a, b, alternative="greater")
    return r.statistic / (len(a) * len(b)), r.pvalue


def run(z, name, mission, chans, val, split, rng):
    S = {}
    for c in chans:
        s = load(z, f"{mission}/channels/channel_{c}.zip")
        S[c] = s[~s.index.duplicated(keep="last")].sort_index()
    for c in chans:
        assert S[c].index.equals(S[chans[0]].index), "channels must share timestamps"
    idx = S[chans[0]].index
    idx = idx.tz_localize(None) if idx.tz is not None else idx
    n = len(idx)
    train, test = idx < pd.Timestamp(val), idx >= pd.Timestamp(split)
    act = np.zeros(n)
    for c in chans:
        d = np.r_[0.0, np.diff(S[c].to_numpy(np.float64))]
        sd = d[train][1:].std()
        if sd > 0:
            act += (d / sd) ** 2
    act /= act[train][1:].mean()
    ca = np.r_[0.0, np.cumsum(act)]
    t = float(np.ceil(np.log2(int(test.sum()) * len(chans))))
    alarm = np.zeros(n, bool)
    for c in chans:
        codes = to_codes(S[c].to_numpy(np.float64))
        b = max(1, int(codes.max()).bit_length())
        _, cost = flight(codes)
        alarm |= test & (cost >= b + t)
    cal = np.r_[0, np.cumsum(alarm)]
    lab = pd.read_csv(io.BytesIO(z.read(f"{mission}/labels.csv")))
    typ = pd.read_csv(io.BytesIO(z.read(f"{mission}/anomaly_types.csv")))
    lab = lab[lab.Channel.isin([f"channel_{c}" for c in chans])].merge(typ, on="ID")
    lab = lab[lab.Category != "Communication Gap"]
    for k in ("StartTime", "EndTime"):
        lab[k] = pd.to_datetime(lab[k]).dt.tz_localize(None)
    lab["i0"] = np.searchsorted(idx, lab.StartTime.to_numpy())
    lab["i1"] = np.maximum(np.searchsorted(idx, lab.EndTime.to_numpy(), side="right") - 1, lab.i0)
    labelled = np.zeros(n, bool)
    for a, b in zip(lab.i0, lab.i1):
        labelled[a:b + 1] = True
    ok = np.r_[0, np.cumsum(test & ~labelled)]
    first = int(np.searchsorted(idx, np.datetime64(split)))
    ev = lab.groupby("ID").agg(i0=("i0", "min"), i1=("i1", "max"), cls=("Class", "first"))
    ev = ev[ev.i0 >= first]
    rows = []
    for eid, e in ev.iterrows():
        a, b = int(e.i0), int(e.i1) + 1
        ell = b - a
        if ell < 2:
            continue
        st = np.nonzero(ok[ell:] - ok[:-ell] == ell)[0]
        if not len(st):
            continue
        c0 = int(rng.choice(st))
        rows.append(dict(set=name, ID=eid, cls=e.cls, length=ell, A_event=(ca[b] - ca[a]) / ell,
                         A_control=(ca[c0 + ell] - ca[c0]) / ell, alarmed=bool(cal[b] - cal[a] > 0)))
    return pd.DataFrame(rows)


def main():
    rng = np.random.default_rng(0)
    zips = {"ESA-Mission1": zipfile.ZipFile(sys.argv[1]), "ESA-Mission2": zipfile.ZipFile(sys.argv[2])}
    out = []
    for name, mission, chans, val, split in SETS:
        d = run(zips[mission], name, mission, chans, val, split, rng)
        out.append(d)
        a1, p1 = auc_p(d.A_event, d.A_control)
        un = d[~d.alarmed]
        a2, p2 = auc_p(un.A_event, un.A_control) if len(un) > 1 else (float("nan"), 1.0)
        print(f"{name}: {len(d)} test events, {len(un)} missed on board")
        print(f"  R1 all events: AUC {a1:.3f}, p = {p1:.3g} (needs >= 0.65, p < 0.01): "
              f"{'HOLDS' if (a1 >= 0.65 and p1 < 0.01) else 'REFUTED'}")
        print(f"  R2 missed events: AUC {a2:.3f}, p = {p2:.3g} (needs >= 0.60, p < 0.05): "
              f"{'HOLDS' if (a2 >= 0.60 and p2 < 0.05) else 'REFUTED'}")
    pd.concat(out).to_csv(DATA / "noise_activity.csv", index=False)


if __name__ == "__main__":
    main()
