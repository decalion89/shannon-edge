#!/usr/bin/env python3
"""The training-free Kraft rule over a whole ESA mission, chronologically.

Protocol of Alcarria et al., "Structure-Aware Unsupervised Anomaly Detection
for Spacecraft Telemetry with Adaptive EVT Thresholding" (SPAICE 2026,
arXiv:2609.10017): all target channels, predictions from the second month of
the mission to its end, events of category "Anomaly" and "Rare Event",
detections closer than 6 hours grouped into one, scored with the corrected
event-wise F0.5. That method retrains a model every month (46.6 CPU-hours on
Mission 1) and reports F0.5 = 0.700 (Mission 1) and 0.698 (Mission 2).

Here nothing is trained and nothing is chosen: every sample is scored online
by the flight profile (a model that has seen only the past), and a sample is
flagged when its cost reaches b + t bits, t = ceil(log2(samples scored over
all target channels)). Under the Kraft bound a calibrated model raises at
most one expected false sample-flag in the whole run (docs/KRAFT_DETECTION.md).

Scores come from ESA-ADB's own metric code (--official, a checkout of
github.com/kplabs-pl/ESA-ADB): ESAScores, ChannelAwareFScore and ADTQC for
anomalies and rare events, and ESAScores for anomalies only.

Usage:
    cargo build --release --example flight_surprise
    python3 bench/esa_chronological.py ESA-Mission1.zip --official ESA-ADB \
        --merge-minutes 360 10 [--cache DIR]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from anomaly_esaadb import change_list, load, load_official_metrics, surprise  # noqa: E402

DAY = 86_400 * 10**9
KEEP_BITS = 16.0  # keep samples whose cost exceeds b by at least this; t is always larger


E_GRID = (2.0 ** -1, 2.0 ** -4, 2.0 ** -8, 2.0 ** -12)
KEEP_WINDOW_BITS = 8.0


def window_evidence(ts: np.ndarray, excess: np.ndarray, hours: float):
    """log2 of the mixture e-process M_n = mean_e prod_{i<=n} ((1-e) + e 2^(cost_i - b)), restarted at
    every `hours`-long UTC window; and the window index of every sample. Under a calibrated code
    each factor has conditional expectation <= 1 (Kraft), so M is a nonnegative supermartingale
    from 1 within a window and P(sup M >= 2^t) <= 2^-t (Ville)."""
    w = ts // int(hours * 3600 * 10**9)
    _, first = np.unique(w, return_index=True)
    start = np.repeat(first, np.diff(np.r_[first, len(w)]))
    out = None
    for e in E_GRID:
        x = np.log2((1 - e) + e * np.exp2(np.minimum(excess, 1000.0)))
        c = np.cumsum(x)
        before = np.where(start > 0, c[np.maximum(start - 1, 0)], 0.0)
        s = c - before
        out = s if out is None else np.logaddexp2(out, s)
        del x, c, before, s
    return out - np.log2(len(E_GRID)), w


def channel_scores(z, root, ch, cache: Path | None, window_hours: float = 0.0):
    """Timestamps of the samples whose score is at least KEEP_BITS (excess of the cost over b) or,
    with window_hours, KEEP_WINDOW_BITS (log2 of the windowed e-process); the scores and the
    timestamp of the sample after each; samples per day (to count the samples scored); b; with
    window_hours, the distinct windows holding samples."""
    suffix = f"_w{window_hours:g}" if window_hours else ""
    f = cache / f"{root}_{ch}{suffix}.npz" if cache else None
    if f is not None and f.exists():
        d = np.load(f)
        return {k: d[k] for k in d.files}
    s = load(z, f"{root}/channels/{ch}.zip")
    s = s[~s.index.duplicated(keep="last")].sort_index()
    if not pd.api.types.is_numeric_dtype(s):
        # Categorical channels (Mission 3 has some, e.g. "value_0"): code each state by its order of
        # first appearance; the compressor sees a symbol stream either way.
        s = pd.Series(pd.factorize(s)[0].astype(np.float32), index=s.index, name=s.name)
    cost = surprise(s)
    b = max(1, (min(len(np.unique(s.to_numpy().astype(np.float32))), 65536) - 1).bit_length())
    ts = s.index.values.astype("datetime64[ns]").astype(np.int64)
    excess = cost - b
    extra = {}
    if window_hours:
        excess, w = window_evidence(ts, excess, window_hours)
        extra["windows"] = np.unique(w)
        keep = np.nonzero(excess >= KEEP_WINDOW_BITS)[0]
    else:
        keep = np.nonzero(excess >= KEEP_BITS)[0]
    nxt = np.minimum(keep + 1, len(ts) - 1)
    med = int(np.median(np.diff(ts))) if len(ts) > 1 else 0
    nxt_t = np.where(keep + 1 < len(ts), ts[nxt], ts[keep] + med)
    day = ts // DAY
    out = dict(t=ts[keep], excess=excess[keep].astype(np.float32), next_t=nxt_t,
               day0=np.array([day[0]]), per_day=np.bincount(day - day[0]), span=np.array([ts[0], ts[-1]]),
               b=np.array([b]), **extra)
    if f is not None:
        np.savez(f, **out)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mission_zip", type=Path)
    ap.add_argument("--official", type=Path, required=True, help="ESA-ADB checkout (metric code)")
    ap.add_argument("--channels", nargs="*", type=int, default=None, help="default: all target channels")
    ap.add_argument("--merge-minutes", nargs="+", type=float, default=[360.0])
    ap.add_argument("--start", default=None, help="first scored instant (default: first sample + 1 month)")
    ap.add_argument("--end", default=None, help="last scored instant (default: last sample)")
    ap.add_argument("--margins", nargs="*", type=float, default=[],
                    help="extra margins t (bits) to report for reference; auto is always reported first")
    ap.add_argument("--cache", type=Path, default=None)
    ap.add_argument("--dump", type=Path, default=None,
                    help="write the grouped detections of the a-priori rule (first grouping) to this CSV")
    ap.add_argument("--window-hours", type=float, default=0.0,
                    help="windowed e-value rule: alarm when log2 of the mixture e-process restarted every "
                         "this many hours reaches ceil(log2 W), W = channel-windows scored (Ville); "
                         "0 = the per-sample rule")
    args = ap.parse_args()
    if args.cache:
        args.cache.mkdir(parents=True, exist_ok=True)

    z = zipfile.ZipFile(args.mission_zip)
    root = next(n.split("/")[0] for n in z.namelist() if n.endswith("labels.csv"))
    labels = pd.read_csv(io.BytesIO(z.read(f"{root}/labels.csv")))
    types = pd.read_csv(io.BytesIO(z.read(f"{root}/anomaly_types.csv")))
    chans = pd.read_csv(io.BytesIO(z.read(f"{root}/channels.csv")))
    for c in ("StartTime", "EndTime"):
        labels[c] = pd.to_datetime(labels[c]).dt.tz_localize(None)
    names = ([f"channel_{c}" for c in args.channels] if args.channels
             else list(chans[chans["Target"] == "YES"]["Channel"]))

    data = {}
    t0 = time.time()
    for ch in names:
        data[ch] = channel_scores(z, root, ch, args.cache, args.window_hours)
        print(f"{ch}: {int(data[ch]['per_day'].sum()):,} samples, b = {int(data[ch]['b'][0])}, "
              f"{time.time() - t0:.0f} s", file=sys.stderr, flush=True)
    first = min(int(d["span"][0]) for d in data.values())
    last = max(int(d["span"][1]) for d in data.values())
    # Day boundaries, so that the samples scored are counted exactly from the per-day counts.
    lo = (pd.Timestamp(args.start) if args.start else pd.Timestamp(first) + pd.DateOffset(months=1)).floor("D")
    hi = pd.Timestamp(args.end).ceil("D") if args.end else pd.Timestamp(last)
    lo_ns, hi_ns = lo.value, hi.value

    def scored(d):
        days = int(d["day0"][0]) + np.arange(len(d["per_day"]))
        return int(d["per_day"][(days >= lo_ns // DAY) & (days * DAY < hi_ns)].sum())
    n_scored = sum(scored(d) for d in data.values())
    t_auto = float(np.ceil(np.log2(n_scored)))
    if args.window_hours:
        wn = int(args.window_hours * 3600 * 10**9)
        n_windows = sum(int(np.count_nonzero((d["windows"] >= lo_ns // wn) & (d["windows"] * wn <= hi_ns)))
                        for d in data.values())
        t_auto = float(np.ceil(np.log2(n_windows)))
        print(f"Windowed e-value rule ({args.window_hours:g} h): {n_windows:,} channel-windows -> "
              f"t_w = {t_auto:g} bits", file=sys.stderr)
    print(f"Scored {lo} to {hi}: {n_scored:,} samples over {len(names)} channels -> t = {t_auto:g} bits",
          file=sys.stderr)

    ESAScores, ChannelAwareFScore, ADTQC = load_official_metrics(args.official)
    yt = labels[labels["Channel"].isin(names)]
    yt = yt[(yt["StartTime"] >= lo) & (yt["EndTime"] <= hi)]
    cols = list(types.columns[-4:])
    yt = yt.merge(types[["ID"] + cols], on="ID", how="left")  # cols include Category
    subsystems = {sub: [*v] for sub, v in chans[chans["Channel"].isin(names)].groupby("Subsystem")["Channel"]}
    both = {"Category": ["Rare Event", "Anomaly"]}
    anom = {"Category": ["Anomaly"]}
    n_both = yt[yt["Category"].isin(both["Category"])]["ID"].nunique()
    n_anom = yt[yt["Category"] == "Anomaly"]["ID"].nunique()

    rule = (f"windowed e-value rule, {args.window_hours:g}-h windows, t_w = ceil(log2 {n_windows:,} "
            f"channel-windows) = {t_auto:g} bits" if args.window_hours else f"t = ceil(log2 N) = {t_auto:g} bits")
    print(f"# Training-free Kraft rule, whole mission ({root})\n")
    print(f"Scored {lo} to {hi}; {len(names)} target channels; {n_scored:,} samples; "
          f"{rule}. Test events: {n_both} anomalies and rare events, "
          f"{n_anom} anomalies.\n")
    print("| Margin t | Grouping | Detections | Event-wise F0.5 | Precision (corrected) | Recall | "
          "Alarming precision | Channel-aware F0.5 | ADTQC | Anomalies only: F0.5 | Precision | Recall |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for t in [t_auto] + list(args.margins):
        for mm in args.merge_minutes:
            merge = int(mm * 60e9)
            per_channel = {}
            for ch in names:
                d = data[ch]
                sel = (d["excess"] >= t) & (d["t"] >= lo_ns) & (d["t"] <= hi_ns)
                ft, fn = d["t"][sel], d["next_t"][sel]
                iv = []
                if len(ft):
                    brk = np.nonzero(np.diff(ft) > merge)[0]
                    starts, ends = np.r_[0, brk + 1], np.r_[brk, len(ft) - 1]
                    iv = [(pd.Timestamp(int(ft[a])), pd.Timestamp(int(min(fn[e], hi_ns)))) for a, e in zip(starts, ends)]
                per_channel[ch] = iv
            # Grouping across channels as well: global detections closer than the grouping window merge.
            flat = sorted(x for v in per_channel.values() for x in v)
            grouped = []
            for a, e in flat:
                if grouped and a - grouped[-1][1] <= pd.Timedelta(minutes=mm):
                    grouped[-1][1] = max(grouped[-1][1], e)
                else:
                    grouped.append([a, e])
            glob = change_list([(a, e) for a, e in grouped], lo, hi)
            if args.dump is not None and t == t_auto and mm == args.merge_minutes[0]:
                pd.DataFrame(grouped, columns=["start", "end"]).to_csv(args.dump, index=False)
            pc = {ch: change_list(v, lo, hi) for ch, v in per_channel.items()}
            quiet = contextlib.redirect_stdout(io.StringIO())
            with quiet:
                e_both = ESAScores(betas=0.5, select_labels=both).score(yt.drop(columns=["Channel"]), glob)
                e_anom = ESAScores(betas=0.5, select_labels=anom).score(yt.drop(columns=["Channel"]), glob)
                ca = ChannelAwareFScore(beta=0.5, select_labels=both).score(yt.copy(),
                                                                          dict(pc), subsystems)
                ytg = yt.copy()
                ytg["Channel"] = "global"
                lat = ADTQC(select_labels=both).score(ytg, {"global": glob})

            def g(dct, *keys):
                for k in keys:
                    for kk, v in dct.items():
                        if kk.lower() == k.lower():
                            return v
                return float("nan")
            print(f"| {t:g}{' (auto)' if t == t_auto else ''} | {mm:g} min | {len(grouped)} | "
                  f"**{g(e_both, 'EW_F_0.50'):.3f}** | {g(e_both, 'EW_precision'):.3f} | "
                  f"{g(e_both, 'EW_recall'):.3f} | {g(e_both, 'alarming_precision'):.3f} | "
                  f"{g(ca, 'channel_F0.50', 'F0.50'):.3f} | {g(lat, 'Total'):.3f} | "
                  f"**{g(e_anom, 'EW_F_0.50'):.3f}** | {g(e_anom, 'EW_precision'):.3f} | "
                  f"{g(e_anom, 'EW_recall'):.3f} |", flush=True)
            if t == t_auto and mm == args.merge_minutes[0]:
                print("<!-- keys: " + ", ".join(list(e_both) + list(ca) + list(lat)) + " -->", flush=True)


if __name__ == "__main__":
    main()
