#!/usr/bin/env python3
"""Anomaly detection for free: does the flight compressor's surprise flag real
spacecraft anomalies?

The flight profile already computes, for every sample, how many bits it cost
— how unexpected it was given everything learned so far. Sender and receiver
get the same value without transmitting anything. This script measures how
well that score finds the anomalies that ESA engineers labelled in the ESA
Anomaly Dataset (Mission 1, CC BY 3.0 IGO, doi:10.5281/zenodo.12528696),
against two classical controls computed on the same samples:

* z-score: |x - rolling mean| / rolling std over 256 samples
* jump:    |x_t - x_(t-1)|, the simplest change detector

For each score, a threshold is set so that only a fraction q of nominal
samples (outside every labelled interval, after a 1% warm-up) exceed it;
an event counts as detected if its interval contains a sample above the
threshold. Reported: events detected at q = 0.1% and q = 0.01%.

Usage:
    cargo build --release --example flight_surprise
    python3 bench/anomaly.py --mission ESA-Mission1 CHANNEL_FILE [CHANNEL_FILE ...]

CHANNEL_FILE is an extracted channel pickle (e.g. ESA-Mission1/channels/
channel_12 after unzipping channel_12.zip); it is loaded with the whitelist
unpickler from bench/telemetry.py.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from telemetry import SafeUnpickler  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def load(path: Path) -> pd.Series:
    with open(path, "rb") as f:
        df = SafeUnpickler(f).load()
    return df.iloc[:, 0]


def events_for(labels: pd.DataFrame, types: pd.DataFrame, channel: str, index: pd.DatetimeIndex) -> list:
    rows = labels[labels["Channel"] == channel]
    out = []
    for _, r in rows.iterrows():
        start = index.searchsorted(pd.Timestamp(r["StartTime"]).tz_localize(None))
        end = index.searchsorted(pd.Timestamp(r["EndTime"]).tz_localize(None), side="right")
        if end > start:
            cat = types.loc[r["ID"], "Category"] if r["ID"] in types.index else "?"
            out.append((start, end, cat))
    return out


def evaluate(score: np.ndarray, events: list, warmup: int) -> dict:
    nominal = np.ones(len(score), dtype=bool)
    nominal[:warmup] = False
    for s, e, _ in events:
        nominal[s:e] = False
    res = {}
    for q in (1e-3, 1e-4):
        thr = np.quantile(score[nominal], 1 - q)
        hits = [score[s:e].max() > thr for s, e, _ in events if s >= warmup]
        res[q] = (sum(hits), len(hits))
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("channels", nargs="+", type=Path)
    ap.add_argument("--mission", type=Path, required=True, help="unzipped ESA-Mission1 directory (labels.csv)")
    args = ap.parse_args()

    labels = pd.read_csv(args.mission / "labels.csv")
    types = pd.read_csv(args.mission / "anomaly_types.csv").set_index("ID")
    binary = ROOT / "target/release/examples/flight_surprise"

    totals = {name: {1e-3: [0, 0], 1e-4: [0, 0]} for name in ("surprise", "z-score", "jump")}
    print("| Channel | Samples | Events | Detector | Events found, 0.1% false alarms | at 0.01% |")
    print("|---|---:|---:|---|---:|---:|")
    for path in args.channels:
        series = load(path)
        x = series.to_numpy().astype(np.float64)
        uniq, codes = np.unique(series.to_numpy().astype(np.float32), return_inverse=True)
        events = events_for(labels, types, path.name, series.index)
        with tempfile.TemporaryDirectory() as t:
            cpath, spath = Path(t) / "codes.u16", Path(t) / "surprise.u32"
            codes.astype("<u2").tofile(cpath)
            subprocess.run([str(binary), str(cpath), str(spath)], check=True, capture_output=True)
            surprise = np.fromfile(spath, dtype="<u4").astype(np.float64) / 256.0
        s = pd.Series(x)
        mean = s.rolling(256, min_periods=16).mean().shift(1)
        std = s.rolling(256, min_periods=16).std().shift(1)
        zscore = ((s - mean).abs() / (std + 1e-9)).fillna(0).to_numpy()
        jump = np.abs(np.diff(x, prepend=x[0]))
        warmup = len(x) // 100
        for name, score in (("surprise", surprise), ("z-score", zscore), ("jump", jump)):
            r = evaluate(score, events, warmup)
            for q in r:
                totals[name][q][0] += r[q][0]
                totals[name][q][1] += r[q][1]
            print(f"| {path.name} | {len(x):,} | {r[1e-3][1]} | {name} | {r[1e-3][0]} | {r[1e-4][0]} |", flush=True)
    print()
    print("| Detector | Events found, 0.1% false alarms | at 0.01% |")
    print("|---|---:|---:|")
    for name, t in totals.items():
        print(f"| {name} | {t[1e-3][0]}/{t[1e-3][1]} | {t[1e-4][0]}/{t[1e-4][1]} |")


if __name__ == "__main__":
    main()
