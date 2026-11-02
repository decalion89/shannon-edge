#!/usr/bin/env python3
"""TSB-AD-U: does the general model's subsequence memory see shape anomalies?

The flight profile predicts each sample from the last few. It has no
memory of subsequences, so an abnormal shape made of normal-looking steps
costs little. The general sedge model (the file compressor) has a match
model, which follows the longest earlier repeat of the recent bytes. On
periodic data it predicts almost perfectly while the shape repeats, and
pays when the shape breaks.

Per series (univariate):
* values are quantised to 8 bits, uniformly between the min and max of
  the normal prefix (clipped);
* each sample's cost in bits comes from shannon_edge::byte_costs
  (examples/byte_costs, MEM_BITS 22), online from the first sample.

Scores:
* CM_raw:  per-sample cost;
* CM_mean: its causal moving mean over the benchmark's window L;
* CM_max:  causal moving max over L.
VUS-PR comes from the benchmark's code, as in bench/tsbad_reference.py.

Usage: tsbad_cm.py TSB-AD-U.zip TSB-AD-checkout {tuning|eval} out.csv [--jobs 4]
"""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import tempfile
import zipfile
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ZIP = None
CODE = None


def costs(x: np.ndarray, train: int) -> np.ndarray:
    ref = x[: max(train, 2)]
    lo, hi = float(np.min(ref)), float(np.max(ref))
    q = np.clip(np.round((x - lo) / (hi - lo) * 255) if hi > lo else np.zeros_like(x), 0, 255).astype(np.uint8)
    with tempfile.TemporaryDirectory() as t:
        ip, op = Path(t) / "in.bin", Path(t) / "out.f32"
        q.tofile(ip)
        subprocess.run([str(ROOT / "target/release/examples/byte_costs"), str(ip), str(op), "22"],
                       check=True, capture_output=True)
        return np.fromfile(op, dtype="<f4").astype(np.float64)


def moving(v: np.ndarray, L: int, how: str) -> np.ndarray:
    s = pd.Series(v)
    r = s.rolling(L, min_periods=1)
    return (r.mean() if how == "mean" else r.max()).to_numpy()


def one(name: str):
    sys.path.insert(0, CODE)
    from TSB_AD.evaluation.basic_metrics import generate_curve
    from TSB_AD.utils.slidingWindows import find_length_rank
    z = zipfile.ZipFile(ZIP)
    root = next(n.split("/")[0] for n in z.namelist() if n.endswith(name))
    df = pd.read_csv(io.BytesIO(z.read(f"{root}/{name}"))).dropna()
    data = df.iloc[:, 0:-1].values.astype(float)
    label = df["Label"].astype(int).to_numpy()
    L = int(find_length_rank(data[:, 0].reshape(-1, 1), rank=1))
    train = int(name.split(".")[0].split("_")[-3])
    c = costs(data[:, 0], train)
    out = {"file": name, "L": L, "n": len(label)}
    for k, v in (("CM_raw", c), ("CM_mean", moving(c, L, "mean")), ("CM_max", moving(c, L, "max"))):
        lo, hi = v.min(), v.max()
        v = (v - lo) / (hi - lo) if hi > lo else np.zeros_like(v)
        out[k] = float(generate_curve(label, v, L, "opt", 250)[7])
    print(name + " " + " ".join(f"{k}={out[k]:.3f}" for k in ("CM_raw", "CM_mean", "CM_max")), file=sys.stderr,
          flush=True)
    return out


def init(zp, code):
    global ZIP, CODE
    ZIP, CODE = zp, code


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zip")
    ap.add_argument("checkout")
    ap.add_argument("split", choices=["tuning", "eval"])
    ap.add_argument("out")
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    args = ap.parse_args()
    lst = "TSB-AD-U-" + {"tuning": "Tuning.csv", "eval": "Eva.csv"}[args.split]
    files = pd.read_csv(Path(args.checkout) / "Datasets/File_List" / lst)["file_name"].tolist()
    done = set(pd.read_csv(args.out)["file"]) if Path(args.out).exists() else set()
    zsz = {i.filename.split("/")[-1]: i.file_size for i in zipfile.ZipFile(args.zip).infolist()}
    todo = sorted((f for f in files if f not in done), key=lambda f: -zsz.get(f, 0))
    with Pool(args.jobs, initializer=init, initargs=(args.zip, str(Path(args.checkout).resolve()))) as pool:
        for r in pool.imap_unordered(one, todo):
            pd.DataFrame([r]).to_csv(args.out, mode="a", header=not Path(args.out).exists(), index=False)


if __name__ == "__main__":
    main()
