#!/usr/bin/env python3
"""The compressor's surprise as an anomaly detector, scored with the ESA-ADB
metric (Kotowski et al., arXiv:2406.17826) on its Mission 1 protocol.

Protocol, as in ESA-ADB: train on samples up to 2007-01-01, test on samples
after it; events of category "Anomaly" and "Rare Event" count (communication
gaps do not, but detections inside them are not false positives); multivariate
scoring on the logical OR of detections across the target channels.

Detector: for every channel, the flight profile's per-sample cost in bits
(`examples/flight_surprise`, online: each sample is scored by a model that
has seen only the past) is compared with a per-channel threshold chosen on
the training part only, as the q-quantile of the cost of training samples
outside any labelled event. Flags closer than MERGE apart are merged into one
detection. Which quantile to use is chosen on the validation months of the
protocol (2006-10-01 to 2007-01-01, thresholds fitted before them); all
rules are reported. Nothing is tuned on the test part.

Scoring: the corrected event-wise precision/recall/F-beta and the alarming
precision, adapted from ESA-ADB's `ESAScores`
(github.com/kplabs-pl/ESA-ADB, timeeval/metrics/ESA_ADB_metrics.py, MIT
License, Copyright (c) 2024 Airbus, KP Labs; 2020-2021 P. Wenig, S. Schmidl).

Defaults are Mission 1's dates; for Mission 2 pass --split 2001-10-01
--validation 2001-07-01 (ESA-ADB's Mission 2 protocol).

Usage:
    cargo build --release --example flight_surprise
    pip install portion
    python3 bench/anomaly_esaadb.py ESA-Mission1.zip --channels 41 42 43 44 45 46 \
        --quantiles 0.9999 0.99999 0.999999 1.0
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import portion as P

sys.path.insert(0, str(Path(__file__).resolve().parent))
from telemetry import SafeUnpickler  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPLIT = pd.Timestamp("2007-01-01")
VALIDATION = pd.Timestamp("2006-10-01")  # last 3 months of training, as in ESA-ADB


def load(z: zipfile.ZipFile, member: str) -> pd.Series:
    inner = zipfile.ZipFile(io.BytesIO(z.read(member)))
    return SafeUnpickler(io.BytesIO(inner.read(inner.namelist()[0]))).load().iloc[:, 0]


def surprise(series: pd.Series) -> np.ndarray:
    uniq, codes = np.unique(series.to_numpy().astype(np.float32), return_inverse=True)
    if len(uniq) > 65536:
        raise SystemExit(f"{series.name}: more than 65,536 distinct values, not supported by flight_surprise")
    with tempfile.TemporaryDirectory() as t:
        cp, sp = Path(t) / "c.u16", Path(t) / "s.u32"
        codes.astype("<u2").tofile(cp)
        subprocess.run([str(ROOT / "target/release/examples/flight_surprise"), str(cp), str(sp)],
                       check=True, capture_output=True)
        return np.fromfile(sp, dtype="<u4").astype(np.float64) / 256.0


def esa_event_scores(y_true: pd.DataFrame, events_pred: P.Interval, full_range, beta=0.5) -> dict:
    """Event-wise part of ESA-ADB's ESAScores.score (see module docstring)."""
    selected = y_true[y_true["Category"].isin(["Rare Event", "Anomaly"])]
    preds = list(events_pred)
    tp = fp = fn = redundant = 0
    matched = [False] * len(preds)
    for aid in selected["ID"].unique():
        gt = selected[selected["ID"] == aid]
        gt_iv = P.Interval(*[P.closed(r.StartTime, r.EndTime) for r in gt.itertuples()])
        hits = [0] * len(list(gt_iv))
        found = False
        for p, pred in enumerate(preds):
            if pred.upper < gt_iv.lower or pred.lower > gt_iv.upper:
                continue
            inter = [not (pred & g).empty for g in gt_iv]
            if not any(inter):
                continue
            matched[p] = True
            if not found:
                tp += 1
                found = True
            for i, v in enumerate(inter):
                hits[i] += v
        redundant += sum(h - 1 for h in hits if h > 1)
        fn += not found
    events_gt = P.Interval(*[P.closed(r.StartTime, r.EndTime) for r in y_true.itertuples()])
    for pred, m in zip(preds, matched):
        if not m and (pred & events_gt).empty:
            fp += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    alarming = tp / (tp + redundant) if tp + redundant else 0.0
    if precision > 0:
        nominal = P.closed(*full_range) - events_gt
        fp_iv = nominal & events_pred
        nominal_s = sum((i.upper - i.lower).total_seconds() for i in nominal)
        fp_s = sum((i.upper - i.lower).total_seconds() for i in fp_iv)
        precision *= 1 - fp_s / nominal_s
    recall = tp / (tp + fn) if tp + fn else 0.0
    f = (1 + beta**2) * precision * recall / (beta**2 * precision + recall) if precision + recall else 0.0
    return dict(tp=tp, fp=fp, fn=fn, precision=precision, recall=recall, f05=f, alarming=alarming)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mission_zip", type=Path)
    ap.add_argument("--channels", nargs="+", type=int, required=True)
    ap.add_argument("--quantiles", nargs="+", type=float, default=[0.99999, 0.999999, 1.0])
    ap.add_argument("--merge-minutes", type=float, default=10.0)
    ap.add_argument("--split", default="2007-01-01", help="train/test split (Mission 2: 2001-10-01)")
    ap.add_argument("--validation", default="2006-10-01", help="validation start (Mission 2: 2001-07-01)")
    args = ap.parse_args()
    global SPLIT, VALIDATION
    SPLIT, VALIDATION = pd.Timestamp(args.split), pd.Timestamp(args.validation)

    z = zipfile.ZipFile(args.mission_zip)
    root = next(n.split("/")[0] for n in z.namelist() if n.endswith("labels.csv"))
    labels = pd.read_csv(io.BytesIO(z.read(f"{root}/labels.csv")))
    types = pd.read_csv(io.BytesIO(z.read(f"{root}/anomaly_types.csv")))
    for c in ("StartTime", "EndTime"):
        labels[c] = pd.to_datetime(labels[c]).dt.tz_localize(None)
    labels = labels.merge(types[["ID", "Category"]], on="ID", how="left")
    names = [f"channel_{c}" for c in args.channels]
    lab = labels[labels["Channel"].isin(names)]

    data = {}
    for ch in names:
        s = load(z, f"{root}/channels/{ch}.zip")
        b = surprise(s)
        ts = s.index.values.astype("datetime64[ns]")
        in_event = np.zeros(len(ts), dtype=bool)
        for r in lab[lab["Channel"] == ch].itertuples():
            a, e = np.searchsorted(ts, np.datetime64(r.StartTime)), np.searchsorted(ts, np.datetime64(r.EndTime), "right")
            in_event[a:e] = True
        data[ch] = (ts, b, in_event)
        print(f"{ch}: {len(ts):,} samples", file=sys.stderr, flush=True)

    test_end = max(d[0][-1] for d in data.values())
    full_range = (SPLIT, pd.Timestamp(test_end))
    y_true = lab[lab["EndTime"] > SPLIT].copy()
    y_true["StartTime"] = y_true["StartTime"].clip(lower=SPLIT)
    merge = np.timedelta64(int(args.merge_minutes * 60e9), "ns")

    def detect(q, fit_end, lo, hi):
        """Thresholds fitted on nominal samples before fit_end; detections in [lo, hi)."""
        starts, ends = [], []
        for ts, b, in_event in data.values():
            fit = (ts < np.datetime64(fit_end)) & ~in_event
            thr = np.quantile(b[fit], q) if q < 1 else b[fit].max()
            win = (ts >= np.datetime64(lo)) & (ts < np.datetime64(hi))
            flag_t = ts[win & (b > thr)]
            if len(flag_t) == 0:
                continue
            brk = np.nonzero(np.diff(flag_t) > merge)[0]
            starts += list(flag_t[np.r_[0, brk + 1]])
            ends += list(flag_t[np.r_[brk, len(flag_t) - 1]])
        return P.Interval(*[P.closed(pd.Timestamp(a), pd.Timestamp(e)) for a, e in zip(starts, ends)])

    # Choose the threshold rule on the validation months only (fit before them).
    y_val = lab[(lab["EndTime"] > VALIDATION) & (lab["StartTime"] < SPLIT)].copy()
    y_val["StartTime"] = y_val["StartTime"].clip(lower=VALIDATION)
    y_val["EndTime"] = y_val["EndTime"].clip(upper=SPLIT)
    val_f = {}
    for q in args.quantiles:
        ev = detect(q, VALIDATION, VALIDATION, SPLIT)
        if len(y_val[y_val["Category"].isin(["Rare Event", "Anomaly"])]):
            val_f[q] = esa_event_scores(y_val, ev, (VALIDATION, SPLIT))["f05"]
        else:
            val_f[q] = float("nan")
    best = max(args.quantiles, key=lambda q: (val_f[q] if val_f[q] == val_f[q] else -1, q))
    n_val = y_val[y_val["Category"].isin(["Rare Event", "Anomaly"])]["ID"].nunique()
    print(f"Validation (2006-10-01 to 2007-01-01, {n_val} events): F0.5 per rule "
          + ", ".join(f"{q}: {v:.3f}" for q, v in val_f.items()) + f"; chosen: {best}\n")

    print("| Threshold (quantile of training nominal cost) | Detections | TP | FP | FN | "
          "Corrected precision | Recall | **Corrected event-wise F0.5** | Alarming precision |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for q in args.quantiles:
        events = detect(q, SPLIT, SPLIT, pd.Timestamp(test_end) + pd.Timedelta(seconds=1))
        r = esa_event_scores(y_true, events, full_range)
        mark = " (chosen on validation)" if q == best else ""
        print(f"| {q}{mark} | {len(list(events))} | {r['tp']} | {r['fp']} | {r['fn']} | {r['precision']:.3f} | "
              f"{r['recall']:.3f} | **{r['f05']:.3f}** | {r['alarming']:.3f} |", flush=True)


if __name__ == "__main__":
    main()
