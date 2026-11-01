#!/usr/bin/env python3
"""Training-free arrhythmia detection on MIT-BIH with the Kraft bound.

    python3 bench/ecg_kraft.py MITDB_DIR [--t auto|T ...]

Data: PhysioNet MIT-BIH Arrhythmia Database v1.0.0 (Moody & Mark 2001;
Goldberger et al. 2000), Open Data Commons Attribution License v1.0. 48
half-hour two-lead records at 360 Hz, 11-bit ADC, every beat annotated by
cardiologists.

Protocol, fixed before any result was seen:
* Lead: the record's first signal (MLII in 45 records, V5 in 102 and 104),
  raw ADC codes. The paced records 102, 104, 107 and 217 are excluded, as
  in the AAMI EC57 convention.
* Model: the flight profile, started empty on each record. No training, no
  other patient's data, no parameter fitted to anything.
* Alarm on a sample whose cost reaches b + t bits, b = the code width the
  coder uses (11 bits for this ADC). Under the Kraft bound a calibrated
  model raises at most N * 2^-t false sample-alarms in N samples.
  t = auto: ceil(log2(N)) per record, i.e. at most one expected false
  sample-alarm per 30-minute record.
* Beats: each sample belongs to the nearest beat annotation; a beat is
  flagged if any of its samples alarms. Normal = AAMI class N (N, L, R,
  e, j); abnormal = every other beat label (V, A, a, J, S, F, E, /, f, Q).
  Non-beat annotations are ignored.
Reported: sensitivity on abnormal beats (overall and per AAMI class),
false-positive rate on normal beats, and false alarm episodes per hour
(alarms more than 1 s apart, on normal beats only).
"""
import argparse
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np
import wfdb

ROOT = Path(__file__).resolve().parent.parent
NORMAL = set("NLRej")
AAMI = {**{s: "N" for s in "NLRej"}, **{s: "SVEB" for s in "AaJS"}, **{s: "VEB" for s in "VE"},
        "F": "F", **{s: "Q" for s in "/fQ"}}
PACED = {"102", "104", "107", "217"}


def costs(codes: np.ndarray) -> tuple[np.ndarray, int]:
    bits = max(1, int(codes.max()).bit_length())
    with tempfile.TemporaryDirectory() as t:
        cp, sp = Path(t) / "c.u16", Path(t) / "s.u32"
        codes.astype("<u2").tofile(cp)
        subprocess.run([str(ROOT / "target/release/examples/flight_surprise"), str(cp), str(sp)],
                       check=True, capture_output=True)
        return np.fromfile(sp, dtype="<u4").astype(np.float64) / 256.0, bits


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mitdb", type=Path)
    ap.add_argument("--t", nargs="+", default=["auto"])
    args = ap.parse_args()
    records = [r for r in (args.mitdb / "RECORDS").read_text().split() if r not in PACED]
    tot = {t: Counter() for t in args.t}
    per_record = []
    for rec in records:
        r = wfdb.rdrecord(str(args.mitdb / rec), physical=False)
        a = wfdb.rdann(str(args.mitdb / rec), "atr")
        x = r.d_signal[:, 0].astype(np.int64)
        assert x.min() >= 0
        cost, b = costs(x)
        n = len(x)
        beats = [(s, sym) for s, sym in zip(a.sample, a.symbol) if sym in AAMI]
        pos = np.array([s for s, _ in beats])
        # each sample -> nearest beat
        mids = (pos[1:] + pos[:-1]) // 2
        owner = np.searchsorted(mids, np.arange(n), side="right")
        hours = n / r.fs / 3600
        row = [rec, b]
        for t in args.t:
            tt = float(np.ceil(np.log2(n))) if t == "auto" else float(t)
            alarm = cost >= b + tt
            flagged = np.zeros(len(pos), bool)
            flagged[np.unique(owner[alarm])] = True
            c = tot[t]
            for (s, sym), f in zip(beats, flagged):
                cls = AAMI[sym]
                c[f"{cls}_n"] += 1
                c[f"{cls}_hit"] += int(f)
            # false alarm episodes: alarming samples owned by normal beats, >1 s apart
            normal_beat = np.array([sym in NORMAL for _, sym in beats])
            fa = np.nonzero(alarm & normal_beat[owner])[0]
            ep = int(len(fa) > 0) + int((np.diff(fa) > r.fs).sum()) if len(fa) else 0
            c["fa_episodes"] += ep
            c["hours"] += hours
            c["samples"] += n
            c["alarm_samples"] += int(alarm.sum())
            ab = ~normal_beat
            row += [tt, f"{flagged[ab].sum()}/{ab.sum()}", f"{flagged[normal_beat].sum()}/{normal_beat.sum()}", ep]
        per_record.append(row)
        print(" ".join(map(str, row)), file=sys.stderr, flush=True)
    print(f"MIT-BIH, {len(records)} records (paced excluded), flight profile started empty on each record, "
          "no training.\n")
    print("| t | Abnormal beats flagged (sensitivity) | SVEB | VEB | F | Normal beats flagged (FPR) | "
          "False alarm episodes per hour | Alarm samples / bound N*2^-t |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for t, c in tot.items():
        ab_n = sum(c[f"{k}_n"] for k in ("SVEB", "VEB", "F", "Q"))
        ab_h = sum(c[f"{k}_hit"] for k in ("SVEB", "VEB", "F", "Q"))
        sens = lambda k: f"{c[k + '_hit'] / c[k + '_n']:.3f} ({c[k + '_hit']}/{c[k + '_n']})" if c[k + "_n"] else "-"
        tt = "auto (ceil log2 N per record)" if t == "auto" else t
        bound = c["samples"] * 2.0 ** -float(t) if t != "auto" else len(records)
        print(f"| {tt} | {ab_h / ab_n:.3f} ({ab_h}/{ab_n}) | {sens('SVEB')} | {sens('VEB')} | {sens('F')} | "
              f"{c['N_hit'] / c['N_n']:.4f} ({c['N_hit']}/{c['N_n']}) | {c['fa_episodes'] / c['hours']:.2f} | "
              f"{c['alarm_samples']:,} / {bound:,.1f} |")


if __name__ == "__main__":
    main()
