#!/usr/bin/env python3
"""Development: the free low-bit channel of the flight profile, and a variance gate (TSB-AD-U).

examples/flight_lowbits gives, per sample, the cost of the value and the cost of its two least
significant bits under the transition model, coded given the high bits and the past
(FlightSession::compress_scored_split). That is the fine-scale increment of the coded entropy: a
free local-dimension estimate (no second model), compared here with the two-model slope of
bench/tsbad_dimension.py.

Values are quantised to 8 bits on the normal prefix's range, as in tsbad_dimension.py.

Scores (VUS-PR, benchmark code):
* LB_dev:   |moving mean over L of the low-bit cost - its median on the normal prefix|;
* DIM_dev:  the two-model slope deviation (8 vs 6 bits), for comparison;
* F:        the compressor's change+state score (tsbad_cascade.onboard_score);
* HYB_LB:   max(z(F), z(LB_dev));
* HYB_DIM:  max(z(F), z(DIM_dev));
* GATED_LB: max(z(F), g * z(LB_dev)), where g = Var(low-bit cost) / Var(total cost) on the normal
            prefix (0..1). When the total cost fluctuates far more than the low-bit cost, the
            noise is in the amplitude, not the fine scale, and the low-bit channel is attenuated.
            Integer version on board: g = (sum of squared low-cost deviations << 8) / (sum of
            squared total-cost deviations), one division per prefix.

Usage: tsbad_lowbits.py TSB-AD-U.zip TSB-AD-checkout {tuning|eval} out.csv [--jobs N]
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tsbad_cascade import onboard_score, zs_  # noqa: E402
from tsbad_dimension import B, quantised_cost  # noqa: E402
from tsbad_reference import moving_mean  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ZIP = None
CODE = None


def split_costs(q: np.ndarray):
    with tempfile.TemporaryDirectory() as t:
        ip, cp, lp = Path(t) / "s.u16", Path(t) / "c.u32", Path(t) / "l.u32"
        q.astype("<u2").tofile(ip)
        subprocess.run([str(ROOT / "target/release/examples/flight_lowbits"), str(ip), str(cp), str(lp)],
                       check=True, capture_output=True)
        return (np.fromfile(cp, dtype="<u4").astype(np.float64) / 256.0,
                np.fromfile(lp, dtype="<u4").astype(np.float64) / 256.0)


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
    x = data[:, 0]
    pre = slice(0, max(train, 2))
    lo, hi = float(x[pre].min()), float(x[pre].max())
    q = np.clip(np.floor((x - lo) / (hi - lo) * (1 << B)) if hi > lo else np.zeros_like(x), 0, (1 << B) - 1)
    total, low = split_costs(q.astype(np.int64))
    lb = moving_mean(low, L)
    lb_dev = np.abs(lb - np.median(lb[pre]))
    slope = moving_mean((quantised_cost(x, lo, hi, B) - quantised_cost(x, lo, hi, B - 2)) / 2.0, L)
    dim_dev = np.abs(slope - np.median(slope[pre]))
    f = onboard_score(x, train, L)
    vt, vl = float(np.var(total[pre])), float(np.var(low[pre]))
    g = min(1.0, vl / vt) if vt > 0 else 0.0
    scores = {"LB_dev": lb_dev, "DIM_dev": dim_dev, "F": f,
              "HYB_LB": np.maximum(zs_(f), zs_(lb_dev)), "HYB_DIM": np.maximum(zs_(f), zs_(dim_dev)),
              "GATED_LB": np.maximum(zs_(f), g * zs_(lb_dev))}
    out = {"file": name, "L": L, "n": len(label), "gate": g}
    for k, v in scores.items():
        v = np.nan_to_num(v)
        a, b = v.min(), v.max()
        v = (v - a) / (b - a) if b > a else np.zeros_like(v)
        out[k] = float(generate_curve(label, v, L, "opt", 250)[7])
    print(name + " " + " ".join(f"{k}={out[k]:.3f}" for k in scores) + f" gate={g:.2f}", file=sys.stderr, flush=True)
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
    todo = sorted((f for f in files if f not in done), key=lambda f: zsz.get(f, 0))
    with Pool(args.jobs, initializer=init, initargs=(args.zip, str(Path(args.checkout).resolve()))) as pool:
        for r in pool.imap_unordered(one, todo):
            pd.DataFrame([r]).to_csv(args.out, mode="a", header=not Path(args.out).exists(), index=False)


if __name__ == "__main__":
    main()
