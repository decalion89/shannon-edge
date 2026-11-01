#!/usr/bin/env python3
"""Circular time-shift control for a set of detections (as dumped by
bench/esa_chronological.py --dump): the corrected event-wise F0.5 of the
detections as they are, and of the same detections shifted in time by
k/(K+1) of the scored span, k = 1..K, wrapping around. The shifts keep
the number, lengths and spacing of detections and destroy only their
alignment with events. A score explained by detecting much, rather than
detecting the right moments, survives the shift.

Scoring: the event-wise logic of ESA-ADB's ESAScores (bench/anomaly_esaadb.py,
esa_event_scores), on events of category Anomaly and Rare Event entirely
inside the scored period (target channels).

Usage: shift_control.py ESA-MissionN.zip detections.csv [--shifts 20]
"""
import argparse
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import portion as P

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from anomaly_esaadb import esa_event_scores  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mission_zip", type=Path)
    ap.add_argument("detections", type=Path)
    ap.add_argument("--start", default=None, help="scored period start (default: as in the dump's run)")
    ap.add_argument("--end", default=None)
    ap.add_argument("--shifts", type=int, default=20)
    args = ap.parse_args()
    z = zipfile.ZipFile(args.mission_zip)
    root = next(n.split("/")[0] for n in z.namelist() if n.endswith("labels.csv"))
    lab = pd.read_csv(io.BytesIO(z.read(f"{root}/labels.csv")))
    ty = pd.read_csv(io.BytesIO(z.read(f"{root}/anomaly_types.csv")))
    ch = pd.read_csv(io.BytesIO(z.read(f"{root}/channels.csv")))
    for c in ("StartTime", "EndTime"):
        lab[c] = pd.to_datetime(lab[c]).dt.tz_localize(None)
    lab = lab.merge(ty[["ID", "Category"]], on="ID")
    det = pd.read_csv(args.detections, parse_dates=["start", "end"])
    names = set(ch[ch.Target == "YES"].Channel)
    lo = pd.Timestamp(args.start) if args.start else None
    hi = pd.Timestamp(args.end) if args.end else None
    if lo is None or hi is None:
        # Same default as esa_chronological.py: first sample + 1 month (day), to the last sample.
        # Recovered from the labels' span is not exact, so require them from the run's header.
        sys.exit("pass --start and --end as printed by esa_chronological.py ('Scored A to B')")
    yt = lab[lab.Channel.isin(names) & (lab.StartTime >= lo) & (lab.EndTime <= hi)]
    span = hi - lo
    rows = []
    for k in range(args.shifts + 1):
        off = span * k / (args.shifts + 1)
        iv = []
        for a, e in zip(det.start, det.end):
            a2, e2 = a + off, e + off
            if a2 > hi:
                a2, e2 = a2 - span, e2 - span
            if e2 > hi:  # wrapped across the end: split
                iv += [P.closed(a2, hi), P.closed(lo, lo + (e2 - hi))]
            else:
                iv.append(P.closed(a2, e2))
        r = esa_event_scores(yt, P.Interval(*iv), (lo, hi))
        rows.append((k, r["tp"], r["fp"], r["fn"], r["precision"], r["recall"], r["f05"]))
    flagged = sum((e - a).total_seconds() for a, e in zip(det.start, det.end)) / span.total_seconds()
    print(f"{len(det)} detections covering {100 * flagged:.2f}% of the scored time; "
          f"{yt[yt.Category.isin(['Anomaly', 'Rare Event'])].ID.nunique()} events\n")
    print("| Shift | TP | FP | FN | Corrected precision | Recall | Event-wise F0.5 |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for k, tp, fp, fn, p, rc, f in rows:
        print(f"| {'none' if k == 0 else f'{k}/{args.shifts + 1}'} | {tp} | {fp} | {fn} | {p:.3f} | {rc:.3f} | {f:.3f} |")
    sh = np.array([r[-1] for r in rows[1:]])
    print(f"\nShifted: median {np.median(sh):.3f}, max {sh.max():.3f}; unshifted {rows[0][-1]:.3f} "
          f"(above all {len(sh)} shifts: {bool((sh < rows[0][-1]).all())})")


if __name__ == "__main__":
    main()
