#!/usr/bin/env python3
"""Beat-level evidence from two codes on MIT-BIH (training-free).

    python3 bench/ecg_ville.py MITDB_DIR [--t auto|T ...]

Same data and exclusions as bench/ecg_kraft.py. Two sequential codes per
record, both started empty, both using only the past:
* Q, "the rhythm repeats": each sample is predicted by the sample at the same
  offset from the R peak in the last beat that was not flagged. The residual
  is coded with a discrete Laplace law whose scale is the mean absolute
  residual of that beat (at least 1).
* R: the flight profile (a general adaptive code).
Beat j covers the samples from 250 ms before its R peak to 250 ms before the
next one. Its evidence is S_j = sum over its samples of (cost_Q - cost_R)
in bits. If the data follow Q, E_Q[2^S_j | past] <= 1 (each factor
R(x)/Q(x) has Q-expectation <= 1), so P(S_j >= t) <= 2^-t: at most
(beats) * 2^-t false beat alarms. t = auto: ceil(log2(beats in the record)),
at most one expected false beat alarm per record if Q is calibrated.
R peaks come from the annotation times (a QRS detector's job; no beat
label is used).
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import wfdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ecg_kraft import AAMI, NORMAL, PACED, costs  # noqa: E402

PRE = 90  # 250 ms at 360 Hz


def laplace_bits(r: np.ndarray, s: float) -> np.ndarray:
    th = np.exp(-1.0 / s)
    return -(np.log2((1 - th) / (1 + th)) + np.abs(r) * np.log2(th))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mitdb", type=Path)
    ap.add_argument("--t", nargs="+", default=["auto"])
    args = ap.parse_args()
    records = [r for r in (args.mitdb / "RECORDS").read_text().split() if r not in PACED]
    tot = {t: Counter() for t in args.t}
    for rec in records:
        r = wfdb.rdrecord(str(args.mitdb / rec), physical=False)
        a = wfdb.rdann(str(args.mitdb / rec), "atr")
        x = r.d_signal[:, 0].astype(np.int64)
        cost_r, _b = costs(x)
        beats = [(s, sym) for s, sym in zip(a.sample, a.symbol) if sym in AAMI]
        pos = np.array([s for s, _ in beats])
        normal = np.array([sym in NORMAL for _, sym in beats])
        for t in args.t:
            tt = float(np.ceil(np.log2(len(pos)))) if t == "auto" else float(t)
            flagged = np.zeros(len(pos), bool)
            tmpl, scale = None, None
            for j in range(len(pos) - 1):
                lo, hi = pos[j] - PRE, pos[j + 1] - PRE
                if lo < 0:
                    continue
                if tmpl is None:
                    tmpl, scale = j, 8.0  # first beat: accept as template, unflagged
                    continue
                idx = np.arange(lo, hi)
                src = pos[tmpl] + (idx - pos[j])
                ok = (src >= 0) & (src < idx)
                pred = np.where(ok, x[np.clip(src, 0, len(x) - 1)], x[idx - 1])
                res = x[idx] - pred
                s_j = float((laplace_bits(res, scale) - cost_r[idx]).sum())
                if s_j >= tt:
                    flagged[j] = True
                else:
                    tmpl, scale = j, max(1.0, float(np.abs(res).mean()))
            c = tot[t]
            for (s, sym), f in zip(beats, flagged):
                c[f"{AAMI[sym]}_n"] += 1
                c[f"{AAMI[sym]}_hit"] += int(f)
            c["beats"] += len(pos)
            c["hours"] += len(x) / r.fs / 3600
            c["fp"] += int((flagged & normal).sum())
            print(rec, t, tt, f"abn {flagged[~normal].sum()}/{(~normal).sum()}",
                  f"norm {flagged[normal].sum()}/{normal.sum()}", file=sys.stderr, flush=True)
    print(f"MIT-BIH, {len(records)} records (paced excluded); two codes started empty on each record, "
          "no training.\n")
    print("| t (bits) | Abnormal beats flagged (sensitivity) | SVEB | VEB | F | Normal beats flagged (FPR) | "
          "False beat alarms per hour | Bound: beats * 2^-t |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for t, c in tot.items():
        ab_n = sum(c[f"{k}_n"] for k in ("SVEB", "VEB", "F", "Q"))
        ab_h = sum(c[f"{k}_hit"] for k in ("SVEB", "VEB", "F", "Q"))
        sens = lambda k: f"{c[k + '_hit'] / c[k + '_n']:.3f} ({c[k + '_hit']}/{c[k + '_n']})" if c[k + "_n"] else "-"
        bound = len(records) if t == "auto" else c["beats"] * 2.0 ** -float(t)
        print(f"| {'auto (ceil log2 beats per record)' if t == 'auto' else t} | {ab_h / ab_n:.3f} ({ab_h}/{ab_n}) | "
              f"{sens('SVEB')} | {sens('VEB')} | {sens('F')} | {c['N_hit'] / c['N_n']:.4f} ({c['N_hit']}/{c['N_n']}) | "
              f"{c['fp'] / c['hours']:.2f} | {bound:,.1f} |")


if __name__ == "__main__":
    main()
