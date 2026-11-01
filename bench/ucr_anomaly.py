#!/usr/bin/env python3
"""UCR Time Series Anomaly Archive (Wu & Keogh, 2021): does the compressor's
largest surprise land on the anomaly?

    python3 bench/ucr_anomaly.py UCR_Anomaly_FullData/ [--method surprise|mp] [--out results.csv]

Each of the 250 files has one anomaly, after a training prefix that is
anomaly-free. The file name gives the training end and the anomaly's begin
and end (1-based). Score per file: correct if the predicted location lies in
[begin - 100, end + 100]. That is the tolerance commonly used with this
archive; the archive's slides ask for a little "play" without fixing a
number. Accuracy = fraction of correct files.

Methods, fixed before running:
* surprise: the flight profile, started empty, compresses the whole series
  online. Values are coded by rank (an order-preserving 16-bit code, binned
  if there are more than 65,536 distinct values). The prediction is the test
  sample with the highest cost. No training, no parameter.
* surprise-w: the same costs summed over a window of length m, where m is
  the period estimated on the training prefix (first autocorrelation peak,
  clipped to 10..500). Same m as for the matrix profile.
* mp: matrix-profile discord (stumpy) with window m: the test subsequence
  farthest from its nearest non-trivial neighbour. The classic baseline
  of the archive's authors.
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def prominence(score):
    """How far the top score stands out of the rest: (max - median) / MAD."""
    s = np.asarray(score, dtype=np.float64)
    s = s[np.isfinite(s)]
    med = np.median(s)
    mad = np.median(np.abs(s - med)) + 1e-12
    return float((s.max() - med) / mad)


def period(train):
    x = train - train.mean()
    n = min(len(x), 20000)
    x = x[:n]
    f = np.fft.rfft(x, 2 * n)
    ac = np.fft.irfft(f * np.conj(f))[:n]
    ac /= ac[0] if ac[0] else 1
    for lag in range(10, min(n // 2, 501)):
        if ac[lag] > ac[lag - 1] and ac[lag] >= ac[lag + 1] and ac[lag] > 0.1:
            return lag
    return 100


def costs(x):
    uniq, codes = np.unique(x.astype(np.float64), return_inverse=True)
    if len(uniq) > 65536:
        codes = codes.astype(np.int64) * 65536 // len(uniq)
    with tempfile.TemporaryDirectory() as t:
        cp, sp = Path(t) / "c.u16", Path(t) / "s.u32"
        codes.astype("<u2").tofile(cp)
        subprocess.run([str(ROOT / "target/release/examples/flight_surprise"), str(cp), str(sp)],
                       check=True, capture_output=True)
        return np.fromfile(sp, dtype="<u4").astype(np.float64) / 256.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--method", choices=["surprise", "mp"], default="surprise")
    ap.add_argument("--out", default=None)
    ap.add_argument("--combine", nargs=2, metavar=("SURPRISE_CSV", "MP_CSV"), default=None,
                    help="score the combination rule fixed before the matrix-profile results were seen: per "
                         "file, take the prediction of 'surprise' if its prominence (robust z of the top score "
                         "within that file) is larger than the matrix profile's, else the matrix profile's. Uses "
                         "no information from other files")
    args = ap.parse_args()
    if args.combine:
        import csv
        rows = {}
        for path in args.combine:
            for r in csv.DictReader(open(path)):
                rows.setdefault(r["file"], {})[r["method"]] = r
        ok = {"surprise": 0, "mp": 0, "combined": 0, "either (oracle, not a method)": 0}
        n = 0
        for f, d in sorted(rows.items()):
            if "surprise" not in d or "mp" not in d:
                continue
            n += 1
            s_, m_ = d["surprise"], d["mp"]
            pick = s_ if float(s_["prominence"]) > float(m_["prominence"]) else m_
            ok["surprise"] += int(s_["correct"])
            ok["mp"] += int(m_["correct"])
            ok["combined"] += int(pick["correct"])
            ok["either (oracle, not a method)"] += int(s_["correct"]) | int(m_["correct"])
        for k, v in ok.items():
            print(f"{k}: {v}/{n} ({v / n:.3f})")
        return
    files = sorted(glob.glob(os.path.join(args.folder, "*.txt")))
    rows = []
    for f in files:
        m = re.search(r"_(\d+)_(\d+)_(\d+)\.txt$", f)
        train_end, b, e = (int(g) for g in m.groups())
        x = np.loadtxt(f).ravel()
        mlen = period(x[:train_end])
        t0 = time.time()
        if args.method == "surprise":
            c = costs(x)
            test = np.arange(train_end, len(x))
            p1 = int(test[np.argmax(c[train_end:])]) + 1
            cw = np.convolve(c, np.ones(mlen), "valid")  # window starting at i
            p2 = int(train_end + np.argmax(cw[train_end:]) + mlen // 2) + 1
            preds = {"surprise": p1, "surprise-w": p2}
            conf = {"surprise": prominence(c[train_end:]), "surprise-w": prominence(cw[train_end:])}
        else:
            import stumpy
            mp = stumpy.stump(x.astype(np.float64), mlen)[:, 0].astype(np.float64)
            mp[~np.isfinite(mp)] = -1
            i = train_end + int(np.argmax(mp[train_end:len(x) - mlen + 1]))
            preds = {"mp": i + mlen // 2 + 1}
            conf = {"mp": prominence(mp[train_end:len(x) - mlen + 1])}
        for k, p in preds.items():
            rows.append((os.path.basename(f), k, p, b, e, int(b - 100 <= p <= e + 100), mlen, time.time() - t0,
                         round(conf[k], 4)))
        print(os.path.basename(f), {k: int(b - 100 <= p <= e + 100) for k, p in preds.items()}, file=sys.stderr, flush=True)
    if args.out:
        with open(args.out, "w") as h:
            h.write("file,method,pred,begin,end,correct,m,seconds,prominence\n")
            for r in rows:
                h.write(",".join(map(str, r)) + "\n")
    for k in sorted({r[1] for r in rows}):
        rr = [r for r in rows if r[1] == k]
        print(f"{k}: {sum(r[5] for r in rr)}/{len(rr)} correct ({sum(r[5] for r in rr) / len(rr):.3f})")


if __name__ == "__main__":
    main()
