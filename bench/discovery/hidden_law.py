#!/usr/bin/env python3
"""Do real anomalies break a balance law hidden below the noise floor? (pre-registered in
bench/discovery/hidden_law_preregistration.md)

Law found on Mission 1 training data only: the fine-scale increments of channels 41, 43 and 45 cancel,
var(d41 + d43 + d45) = 0.178 x the sum of their variances. Violation statistic per window:
V = mean over the window of (d41 + d43 + d45)^2 / training mean of the same.
Events: labelled events touching channels 41-46 in the test period (from 2007-01-01), excluding
communication gaps. Controls: one unlabelled window of the same length per event, test period, seed 0.
On-board alarms: the Kraft rule of esa_edge_link.py on channels 41-46 (cost >= b + t).

Usage: hidden_law.py ESA-Mission1.zip
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
CH = [41, 42, 43, 44, 45, 46]
LAW = [41, 43, 45]
VAL, SPLIT = "2006-10-01", "2007-01-01"


def auc(a, b):
    return mannwhitneyu(a, b, alternative="greater").statistic / (len(a) * len(b))


def main():
    rng = np.random.default_rng(0)
    z = zipfile.ZipFile(sys.argv[1])
    S = {}
    for c in CH:
        s = load(z, f"ESA-Mission1/channels/channel_{c}.zip")
        S[c] = s[~s.index.duplicated(keep="last")].sort_index()
    idx = S[41].index
    idx = idx.tz_localize(None) if idx.tz is not None else idx
    for c in CH:
        assert S[c].index.equals(S[41].index)
    n = len(idx)
    X = {c: S[c].to_numpy(np.float64) for c in CH}
    inc = sum(np.r_[0.0, np.diff(X[c])] for c in LAW)
    train = idx < pd.Timestamp(VAL)
    v2 = inc ** 2 / np.mean(inc[train][1:] ** 2)
    cs = np.r_[0.0, np.cumsum(v2)]
    # on-board Kraft alarms (any of channels 41-46)
    test = idx >= pd.Timestamp(SPLIT)
    t = float(np.ceil(np.log2(int(test.sum()) * len(CH))))
    alarm = np.zeros(n, bool)
    for c in CH:
        codes = to_codes(X[c])
        b = max(1, int(codes.max()).bit_length())
        _, cost = flight(codes)
        alarm |= test & (cost >= b + t)
    ca = np.r_[0, np.cumsum(alarm)]
    lab = pd.read_csv(io.BytesIO(z.read("ESA-Mission1/labels.csv")))
    typ = pd.read_csv(io.BytesIO(z.read("ESA-Mission1/anomaly_types.csv")))
    lab = lab[lab.Channel.isin([f"channel_{c}" for c in CH])].merge(typ, on="ID")
    lab = lab[lab.Category != "Communication Gap"]
    for k in ("StartTime", "EndTime"):
        lab[k] = pd.to_datetime(lab[k]).dt.tz_localize(None)
    lab["i0"] = np.searchsorted(idx, lab.StartTime.to_numpy())
    lab["i1"] = np.maximum(np.searchsorted(idx, lab.EndTime.to_numpy(), side="right") - 1, lab.i0)
    labelled = np.zeros(n, bool)
    for a, b in zip(lab.i0, lab.i1):
        labelled[a:b + 1] = True
    ok = np.r_[0, np.cumsum(test & ~labelled)]
    ev = lab.groupby("ID").agg(i0=("i0", "min"), i1=("i1", "max"), cls=("Class", "first"))
    ev = ev[ev.i0 >= int(np.searchsorted(idx, np.datetime64(SPLIT)))]
    rows = []
    for eid, e in ev.iterrows():
        a, b = int(e.i0), int(e.i1) + 1
        ell = b - a
        if ell < 2:
            continue
        starts = np.nonzero(ok[ell:] - ok[:-ell] == ell)[0]
        if not len(starts):
            continue
        c0 = int(rng.choice(starts))
        rows.append(dict(ID=eid, cls=e.cls, length=ell, V_event=(cs[b] - cs[a]) / ell,
                         V_control=(cs[c0 + ell] - cs[c0]) / ell, alarmed=bool(ca[b] - ca[a] > 0)))
    d = pd.DataFrame(rows)
    d.to_csv(DATA / "hidden_law.csv", index=False)
    a1 = auc(d.V_event, d.V_control)
    p1 = mannwhitneyu(d.V_event, d.V_control, alternative="greater").pvalue
    un = d[~d.alarmed]
    a2 = auc(un.V_event, un.V_control) if len(un) > 1 else float("nan")
    p2 = mannwhitneyu(un.V_event, un.V_control, alternative="greater").pvalue if len(un) > 1 else 1.0
    print(f"{len(d)} test events ({int(d.alarmed.sum())} with an on-board alarm, {len(un)} without)")
    print(f"V1 all events: AUC {a1:.3f}, p = {p1:.3g} (needs AUC >= 0.65 and p < 0.01): "
          f"{'HOLDS' if (a1 >= 0.65 and p1 < 0.01) else 'REFUTED'}")
    print(f"V2 events the on-board detector misses: AUC {a2:.3f}, p = {p2:.3g} (needs AUC >= 0.60 and p < 0.05): "
          f"{'HOLDS' if (a2 >= 0.60 and p2 < 0.05) else 'REFUTED'}")
    print(d.groupby("cls").agg(n=("ID", "size"), V_event=("V_event", "median"), V_control=("V_control", "median"),
                               alarmed=("alarmed", "mean")).round(3).to_string())


if __name__ == "__main__":
    main()
