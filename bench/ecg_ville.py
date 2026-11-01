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

--design delta (second attempt): Q predicts the *change* from the previous
sample by the mean change at the same offset over the last 8 unflagged
beats (insensitive to baseline wander), with a per-offset Laplace scale
from those beats' residuals. It picks the best alignment shift in -2..2
and pays log2(5) bits to signal it (a two-part code, still a valid code).
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


K_BEATS, SHIFTS, MAXLEN = 8, (-2, -1, 0, 1, 2), 720


def delta_design(x, pos, cost_r, tt):
    """Q codes d_i = x_i - x_{i-1} by the mean d at the same offset from the R peak over the last
    K_BEATS unflagged beats (shift s in SHIFTS chosen per beat, log2(len(SHIFTS)) bits), with a
    per-offset discrete Laplace scale = mean |residual| at that offset over those beats (>= 1)."""
    d = np.diff(x, prepend=x[:1])
    flagged = np.zeros(len(pos), bool)
    hist_d, hist_r = [], []  # per accepted beat: d over offsets 0..MAXLEN-1 (from lo), residuals
    shift_bits = np.log2(len(SHIFTS))
    for j in range(len(pos) - 1):
        lo, hi = pos[j] - PRE, pos[j + 1] - PRE
        if lo < 2:
            continue
        n = min(hi - lo, MAXLEN)
        idx = np.arange(lo, lo + n)
        if len(hist_d) < 2:
            seg = np.full(MAXLEN, np.nan)
            seg[:n] = d[idx]
            hist_d.append(seg)
            hist_r.append(np.full(MAXLEN, np.nan))
            continue
        tmpl = np.nanmean(np.array(hist_d[-K_BEATS:]), axis=0)
        rs = np.array(hist_r[-K_BEATS:])
        scale = np.nanmean(np.abs(rs), axis=0) if np.isfinite(rs).any() else np.full(MAXLEN, 8.0)
        scale = np.where(np.isfinite(scale), np.maximum(scale, 1.0), 8.0)
        best = None
        for sh in SHIFTS:
            src = np.arange(n) - sh
            okk = (src >= 0) & (src < MAXLEN)
            pred = np.where(okk, tmpl[np.clip(src, 0, MAXLEN - 1)], 0.0)
            pred = np.where(np.isfinite(pred), pred, 0.0)
            sc = np.where(okk, scale[np.clip(src, 0, MAXLEN - 1)], 8.0)
            res = np.round(d[idx] - pred)
            bits = laplace_bits(res, 0.0 + sc).sum() + shift_bits
            if best is None or bits < best[0]:
                best = (bits, res)
        s_j = best[0] - cost_r[idx].sum()
        if s_j >= tt:
            flagged[j] = True
        else:
            seg = np.full(MAXLEN, np.nan)
            seg[:n] = d[idx]
            hist_d.append(seg)
            rr = np.full(MAXLEN, np.nan)
            rr[:n] = best[1]
            hist_r.append(rr)
            if len(hist_d) > K_BEATS:
                hist_d.pop(0)
                hist_r.pop(0)
    return flagged


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mitdb", type=Path)
    ap.add_argument("--t", nargs="+", default=["auto"])
    ap.add_argument("--design", choices=["template", "delta"], default="template")
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
            if args.design == "delta":
                flagged = delta_design(x, pos, cost_r, tt)
                c = tot[t]
                for (s, sym), f in zip(beats, flagged):
                    c[f"{AAMI[sym]}_n"] += 1
                    c[f"{AAMI[sym]}_hit"] += int(f)
                c["beats"] += len(pos)
                c["hours"] += len(x) / r.fs / 3600
                c["fp"] += int((flagged & normal).sum())
                print(rec, t, tt, f"abn {flagged[~normal].sum()}/{(~normal).sum()}",
                      f"norm {flagged[normal].sum()}/{normal.sum()}", file=sys.stderr, flush=True)
                continue
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
