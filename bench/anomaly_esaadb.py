#!/usr/bin/env python3
"""The compressor's surprise as an anomaly detector, scored with the ESA-ADB
metric (Kotowski et al., arXiv:2406.17826) on its Mission 1 protocol.

Protocol, as in ESA-ADB: train on samples up to 2007-01-01, test on samples
after it; events of category "Anomaly" and "Rare Event" count (communication
gaps do not, but detections inside them are not false positives); multivariate
scoring on the logical OR of detections across the target channels.

Detector: for every channel, the flight profile's per-sample cost in bits
(channels with more than 65,536 distinct values are scored on their values
merged into 65,536 ordered bins)
(`examples/flight_surprise`, online: each sample is scored by a model that
has seen only the past) is compared with a per-channel threshold chosen on
the training part only, as the q-quantile of the cost of training samples
outside any labelled event. Flags closer than MERGE apart are merged into one
detection. Which quantile to use is chosen on the validation months of the
protocol (2006-10-01 to 2007-01-01, thresholds fitted before them); all
rules are reported. Nothing is tuned on the test part. Optional rules:
threshold multipliers (--factors) and muting channels that raised a false
detection in the 3 months before the evaluated period (--mute; for the
test, those are the validation months); a second, never-forgetting detector
of rare transitions, OR-combined (--slow); thresholds per kind of interval
since the previous sample — shorter than usual, usual, gap (--time-aware);
a persistent score, the minimum of a sample's cost and the next one's, so
that isolated spikes vanish (--persist, one sample of delay).

With --resample 30s, every channel is first resampled as in ESA-ADB's data
preparation (30-s grid, zero-order hold), so the detector sees the same
samples as the published algorithms.

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


MIN_COST = False  # --min-cost: score each sample by the cheaper of the two flight models


def surprise(series: pd.Series) -> np.ndarray:
    uniq, codes = np.unique(series.to_numpy().astype(np.float32), return_inverse=True)
    if len(uniq) > 65536:
        # The flight profile takes 16-bit codes. For detection only, merge
        # neighbouring distinct values into 65,536 ordered bins (a lossy view
        # of the channel; the compressor's own lossless results never do this).
        codes = (codes.astype(np.int64) * 65536 // len(uniq))
        print(f"{series.name}: {len(uniq):,} distinct values binned to 65,536 for scoring", file=sys.stderr)
    with tempfile.TemporaryDirectory() as t:
        cp, sp, op = Path(t) / "c.u16", Path(t) / "s.u32", Path(t) / "o.u32"
        codes.astype("<u2").tofile(cp)
        subprocess.run([str(ROOT / "target/release/examples/flight_surprise"), str(cp), str(sp), "14", str(op)],
                       check=True, capture_output=True)
        c = np.fromfile(sp, dtype="<u4").astype(np.float64) / 256.0
        if MIN_COST:
            c = np.minimum(c, np.fromfile(op, dtype="<u4").astype(np.float64) / 256.0)
        return c


def slow_surprise(series: pd.Series) -> np.ndarray:
    """A memory that never forgets: -log2 of how often this transition
    (previous value -> value) occurred before, relative to how often the
    previous value occurred, over the whole past of the channel (online, no
    future samples)."""
    _, codes = np.unique(series.to_numpy().astype(np.float32), return_inverse=True)
    codes = codes.astype(np.int64)
    n = len(codes)
    prev = np.r_[-1, codes[:-1]]

    def occurrences_before(keys: np.ndarray) -> np.ndarray:
        order = np.lexsort((np.arange(n), keys))
        k = keys[order]
        start = np.r_[0, np.nonzero(k[1:] != k[:-1])[0] + 1]
        group_start = np.repeat(start, np.diff(np.r_[start, n]))
        occ = np.empty(n, dtype=np.int64)
        occ[order] = np.arange(n) - group_start
        return occ

    pair = occurrences_before((prev + 1) * (codes.max() + 2) + codes)
    ctx = occurrences_before(prev + 1)
    return -np.log2((pair + 0.5) / (ctx + 1.0))


def budget_threshold(ts: np.ndarray, cost: np.ndarray, allowed: int, merge) -> float:
    """Smallest threshold such that the samples above it form at most
    `allowed` detections (flags closer than `merge` merged into one)."""
    top = np.argsort(cost)[::-1][: 20000]
    best = cost[top[0]]
    lo, hi = 0, len(top)  # number of top samples flagged
    while lo < hi:  # largest n with events(n) <= allowed
        mid = (lo + hi + 1) // 2
        t = np.sort(ts[top[:mid]])
        events = 1 + int(np.count_nonzero(np.diff(t) > merge)) if mid else 0
        if events <= allowed:
            lo = mid
        else:
            hi = mid - 1
    n = lo
    if n == 0:
        return float(best)
    if n >= len(top):
        return float(cost[top[-1]])
    return float(cost[top[n]])  # flag exactly the top n samples (ties aside)


def load_official_metrics(checkout: Path):
    """Import ESA-ADB's metric modules (ESAScores, ChannelAwareFScore, ADTQC)
    from a checkout, unmodified, as a standalone package."""
    import importlib
    import shutil
    src = checkout / "timeeval" / "metrics"
    pkg = Path(tempfile.mkdtemp()) / "esaadb_metrics"
    pkg.mkdir()
    for f in ("ESA_ADB_metrics.py", "metric.py", "utils.py", "latency_metrics.py", "ranking_metrics.py"):
        shutil.copy(src / f, pkg / f)
    shutil.copytree(src / "affiliation_based_metrics_repo", pkg / "affiliation_based_metrics_repo")
    (pkg / "__init__.py").write_text("")
    sys.path.insert(0, str(pkg.parent))
    esa = importlib.import_module("esaadb_metrics.ESA_ADB_metrics")
    rank = importlib.import_module("esaadb_metrics.ranking_metrics")
    lat = importlib.import_module("esaadb_metrics.latency_metrics")
    return esa.ESAScores, rank.ChannelAwareFScore, lat.ADTQC


def change_list(intervals, lo, hi):
    """[(start, end)) intervals -> ESA-ADB's (timestamp, is_anomaly) list over [lo, hi]."""
    iv = sorted(intervals)
    merged = []
    for a, e in iv:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([a, e])
    out = [[lo, 0]]
    for a, e in merged:
        out += [[max(a, lo), 1], [min(e, hi), 0]]
    out.append([hi, 0])
    return np.array([[pd.Timestamp(t), v] for t, v in out], dtype=object)


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


def write_report(path, rule, rule_name, data, labels, lab, channel_flags, to_events, muted_channels, hi):
    """Per test event: detected or not, lead/lag of the first flag, channels flagged. Then every
    detection overlapping no labelled event in any channel, ranked by evidence: the largest excess
    of a sample's cost over the channel's threshold, in bits (under the Kraft bound a calibrated
    model exceeds b + t bits with probability at most 2^-t)."""
    q, factor, mute, slow, timed = rule
    muted = muted_channels(q, factor, SPLIT, slow, timed) if mute else set()
    flags = {}  # channel -> list of (start, end, peak excess in bits over the threshold)
    for ch, (ts, cost, _sl, thr, _kind) in data.items():
        if ch in muted:
            continue
        key = (pd.Timestamp(SPLIT), q, "fast")
        th = thr.get(key, 0.0) * factor if not timed else None
        out = []
        for a, e in to_events(channel_flags(ch, q, factor, SPLIT, SPLIT, hi, slow, timed)):
            i, j = np.searchsorted(ts, a), np.searchsorted(ts, e, "right")
            peak = float(cost[i:j].max()) - (th if th is not None else 0.0)
            out.append((pd.Timestamp(a), pd.Timestamp(e), peak, float(cost[i:j].max())))
        flags[ch] = out
    lines = [f"# Event report, rule {rule_name}", "",
             "## Test events (target channels)", "",
             "| Event | Category | Start | End | Detected | First flag vs start | Labelled channels | Flagged labelled channels |",
             "|---|---|---|---|---|---:|---:|---|"]
    test = lab[lab["EndTime"] > SPLIT]
    for eid, g in test.groupby("ID", sort=False):
        cat = g["Category"].iloc[0]
        if cat not in ("Anomaly", "Rare Event"):
            continue
        s0, e0 = g["StartTime"].min(), g["EndTime"].max()
        firsts, hit_ch = [], []
        for r in g.itertuples():
            for a, e, _p, _c in flags.get(r.Channel, []):
                if a <= r.EndTime and e >= r.StartTime:
                    firsts.append(a)
                    hit_ch.append(r.Channel.replace("channel_", ""))
        # Any target channel flagging inside the event window counts for "detected" (as the global score).
        any_hit = [a for fl in flags.values() for a, e, _p, _c in fl if a <= e0 and e >= s0]
        det = "yes" if any_hit else "no"
        lead = f"{(min(any_hit) - s0).total_seconds() / 60:+.0f} min" if any_hit else ""
        lines.append(f"| {eid} | {cat} | {s0} | {e0} | {det} | {lead} | {g['Channel'].nunique()} | "
                     f"{', '.join(sorted(set(hit_ch), key=int)) or '-'} |")
    lab_all = labels[labels["EndTime"] > SPLIT]
    cand = []
    for ch, fl in flags.items():
        for a, e, peak, c in fl:
            near = lab_all[(lab_all["StartTime"] <= e) & (lab_all["EndTime"] >= a)]
            if near.empty:
                cand.append((peak, a, e, ch, c))
    cand.sort(key=lambda x: -x[0])
    lines += ["", "## Detections that overlap no labelled event in any channel", "",
              f"{len(cand)} channel-level detections; ranked by peak excess over the threshold.", "",
              "| Rank | Channel | Start | End | Peak cost (bits) | Excess over threshold (bits) | Other channels flagging within 1 h |",
              "|---:|---|---|---|---:|---:|---|"]
    for k, (peak, a, e, ch, c) in enumerate(cand, 1):
        others = sorted({o.replace("channel_", "") for o, fl in flags.items() if o != ch
                         for a2, e2, _p, _c in fl if a2 <= e + pd.Timedelta(hours=1) and e2 >= a - pd.Timedelta(hours=1)},
                        key=int)
        lines.append(f"| {k} | {ch.replace('channel_', '')} | {a} | {e} | {c:.1f} | {peak:+.1f} | "
                     f"{', '.join(others) or '-'} |")
    Path(path).write_text("\n".join(lines) + "\n")
    print(f"report written to {path}: {len(cand)} unlabelled detections", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mission_zip", type=Path)
    ap.add_argument("--channels", nargs="+", type=int, required=True)
    ap.add_argument("--quantiles", nargs="*", type=float, default=[0.99999, 0.999999, 1.0])
    ap.add_argument("--kraft", nargs="*", default=[],
                    help="also try training-free thresholds of b + t bits, b the channel's code width: a "
                         "calibrated model exceeds b + t bits with probability at most 2^-t (Kraft). Values of "
                         "t, or 'auto' for t = ceil(log2(test samples over all channels)), i.e. at most one "
                         "expected false sample-alarm in the whole test set if the model is calibrated")
    ap.add_argument("--merge-minutes", type=float, default=10.0)
    ap.add_argument("--budgets", nargs="*", type=float, default=[],
                    help="also try thresholds that allow at most this many detections per year in the "
                         "nominal training data (an operational false-alarm budget)")
    ap.add_argument("--factors", nargs="+", type=float, default=[1.0],
                    help="threshold multipliers to try (chosen on validation)")
    ap.add_argument("--resample", default=None,
                    help="resample each channel to this grid with zero-order hold before scoring, as ESA-ADB's "
                         "preprocessing does (e.g. 30s); default: original samples")
    ap.add_argument("--official", type=Path, default=None,
                    help="path to a checkout of github.com/kplabs-pl/ESA-ADB: also score the rule chosen on "
                         "validation with ESA-ADB's own metric code (all its metrics), unmodified")
    ap.add_argument("--persist", action="store_true",
                    help="score each sample by min(cost of it, cost of the next sample): an isolated spike "
                         "(e.g. a resampling artefact) vanishes, a lasting anomaly does not (one sample of delay)")
    ap.add_argument("--time-aware", action="store_true",
                    help="also try thresholds per kind of interval since the previous sample "
                         "(shorter than usual, usual, gap), each fitted on training")
    ap.add_argument("--slow", action="store_true",
                    help="also try adding the never-forgetting transition-rarity detector (OR-combined)")
    ap.add_argument("--mute", action="store_true",
                    help="also try muting channels that raised a false alarm in the 3 months before the evaluated period")
    ap.add_argument("--kraft-cusum", action="store_true",
                    help="also try the cumulative Kraft rule: per channel, CUSUMs of log2((1-e) + e 2^(cost-b)) "
                         "for e in 2^-1, 2^-4, 2^-8, 2^-12; alarm when any exceeds t + 2 bits, t = "
                         "ceil(log2(test samples over all channels)). Each increment is an e-value under a "
                         "calibrated model, so the expected number of false alarms is at most 1, as for --kraft "
                         "auto, but evidence from several moderately surprising samples adds up")
    ap.add_argument("--cusum-offsets", nargs="*", type=float, default=[0.0],
                    help="with --kraft-cusum: also try thresholds t + offset (bits); validation picks")
    ap.add_argument("--self-calibrate", action="store_true",
                    help="Kraft rules only: each channel estimates online, from its own past and no labels, how "
                         "overconfident its model is: D = max over margins m in 4..24 (step 4) of "
                         "log2(past rate of cost >= b + m) + m, over margins seen at least 10 times, floored at 0. "
                         "Costs are lowered by D before the Kraft tests (the bound with a model off by D bits is "
                         "2^(D - t))")
    ap.add_argument("--min-cost", action="store_true",
                    help="score each sample by the cheaper of the flight profile's two models (both are evaluated "
                         "on every sample; the codec uses one). Still a valid Kraft score: min <= each code length")
    ap.add_argument("--report", type=Path, default=None,
                    help="write, for the rule chosen on validation, every test event (detected or not, first "
                         "flag relative to its start, channels flagged) and every detection that overlaps no "
                         "labelled event in any channel, ranked by its evidence in bits")
    ap.add_argument("--attribute", action="store_true",
                    help="with --official: once a detection fires, also name every channel whose cost reaches "
                         "b + t_attr bits within the merge window around it, t_attr = log2(samples examined in "
                         "that window over all channels): at most one expected false channel per detection "
                         "under the Kraft bound (no training, no tuning)")
    ap.add_argument("--split", default="2007-01-01", help="train/test split (Mission 2: 2001-10-01)")
    ap.add_argument("--validation", default="2006-10-01", help="validation start (Mission 2: 2001-07-01)")
    args = ap.parse_args()
    global SPLIT, VALIDATION, MIN_COST
    SPLIT, VALIDATION = pd.Timestamp(args.split), pd.Timestamp(args.validation)
    MIN_COST = args.min_cost

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
    med_dt = {}
    merge_ns = np.timedelta64(int(args.merge_minutes * 60e9), "ns")
    for ch in names:
        s = load(z, f"{root}/channels/{ch}.zip")
        if args.resample:
            # As ESA-ADB's data preparation: a regular grid from the floor of
            # the first timestamp to the ceiling of the last, forward-filled
            # (zero-order hold), first sample kept.
            rule = pd.Timedelta(args.resample)
            grid = pd.date_range(s.index[0].floor(rule), s.index[-1].ceil(rule), freq=rule)
            first = s.iloc[0]
            s = s[~s.index.duplicated(keep="last")].reindex(grid, method="ffill")
            s.iloc[0] = first
        b = surprise(s)
        code_bits = max(1, (min(len(np.unique(s.to_numpy().astype(np.float32))), 65536) - 1).bit_length())
        if args.persist:
            b = np.minimum(b, np.r_[b[1:], b[-1:]])
        ts = s.index.values.astype("datetime64[ns]")
        in_event = np.zeros(len(ts), dtype=bool)
        for r in lab[lab["Channel"] == ch].itertuples():
            a, e = np.searchsorted(ts, np.datetime64(r.StartTime)), np.searchsorted(ts, np.datetime64(r.EndTime), "right")
            in_event[a:e] = True
        sl = slow_surprise(s) if args.slow else None
        n_samples = len(ts)
        del s
        # Thresholds need the training part only once: compute them for every
        # fit boundary used below, then keep only the samples that can raise a
        # detection (from 3 months before validation onwards) to save memory.
        thr = {}
        for fit_end in (VALIDATION - pd.DateOffset(months=3), VALIDATION, SPLIT):
            fit = (ts < np.datetime64(fit_end)) & ~in_event
            for q in args.quantiles:
                for key, arr in (("fast", b), ("slow", sl)):
                    if arr is not None:
                        thr[(fit_end, q, key)] = np.quantile(arr[fit], q) if q < 1 else arr[fit].max()
            for k in args.budgets:
                years = (ts[fit][-1] - ts[fit][0]) / np.timedelta64(365 * 86400, "s")
                for key, arr in (("fast", b), ("slow", sl)):
                    if arr is not None:
                        thr[(fit_end, -k, key)] = budget_threshold(ts[fit], arr[fit], int(k * years), merge_ns)
        for t in (float(v) for v in args.kraft if v != "auto"):
            for fit_end in (VALIDATION - pd.DateOffset(months=3), VALIDATION, SPLIT):
                thr[(fit_end, 1000 + t, "fast")] = code_bits + t  # no training data used
        thr["code_bits"] = code_bits
        kcost = b
        if args.self_calibrate:
            n_i = np.arange(len(b), dtype=np.float64)
            dhat = np.zeros(len(b))
            for m in (4, 8, 12, 16, 20, 24):
                cnt = np.concatenate(([0], np.cumsum(b >= code_bits + m)[:-1])).astype(np.float64)
                with np.errstate(divide="ignore", invalid="ignore"):
                    lr = np.where(cnt >= 10, np.log2(cnt / np.maximum(n_i, 1.0)) + m, 0.0)
                dhat = np.maximum(dhat, lr)
            kcost = b - dhat
            thr["dhat_test_median"] = float(np.median(dhat[ts >= np.datetime64(SPLIT)])) if (ts >= np.datetime64(SPLIT)).any() else 0.0
            del n_i
        if args.kraft_cusum:
            # S_i = max(0, S_{i-1} + x_i) = C_i - min(0, min_{j<=i} C_j), C = cumsum(x)
            score = np.full(len(b), -np.inf)
            for e in (2.0 ** -1, 2.0 ** -4, 2.0 ** -8, 2.0 ** -12):
                x = np.log2((1 - e) + e * np.exp2(np.minimum(kcost - code_bits, 1000.0)))
                cum = np.cumsum(x)
                score = np.maximum(score, cum - np.minimum(np.minimum.accumulate(cum), 0.0))
            thr["cusum"] = score - 2.0  # union over 4 values of e
        # Kind of interval since the previous sample: 0 shorter than usual,
        # 1 usual, 2 gap (relative to the channel's median interval).
        dt = np.diff(ts, prepend=ts[:1]).astype(np.int64)
        med = np.median(dt[1:]) if len(dt) > 1 else 1
        kind = np.where(dt < 0.75 * med, 0, np.where(dt > 2 * med, 2, 1)).astype(np.int8)
        kind[0] = 1
        if args.time_aware:
            for fit_end in (VALIDATION - pd.DateOffset(months=3), VALIDATION, SPLIT):
                fit = (ts < np.datetime64(fit_end)) & ~in_event
                for q in args.quantiles:
                    for kd in (0, 1, 2):
                        sel = fit & (kind == kd)
                        thr[(fit_end, q, "fast", kd)] = ((np.quantile(b[sel], q) if q < 1 else b[sel].max())
                                                        if sel.any() else np.inf)
        keep = ts >= np.datetime64(VALIDATION - pd.DateOffset(months=3))
        if "cusum" in thr:
            thr["cusum"] = thr["cusum"][keep].astype(np.float32)
        if args.self_calibrate:
            thr["kcost"] = kcost[keep].astype(np.float32)
            print(f"{ch}: self-calibration D (test median) {thr['dhat_test_median']:.2f} bits", file=sys.stderr)
        data[ch] = (ts[keep], b[keep].astype(np.float32), None if sl is None else sl[keep].astype(np.float32), thr,
                    kind[keep])
        med_dt[ch] = np.timedelta64(int(med), "ns")
        del b, sl, in_event
        print(f"{ch}: {n_samples:,} samples", file=sys.stderr, flush=True)

    test_end = max(d[0][-1] for d in data.values())
    kraft_t = [float(v) for v in args.kraft if v != "auto"]
    if "auto" in args.kraft:
        n_test = sum(int((d[0] >= np.datetime64(SPLIT)).sum()) for d in data.values())
        t_auto = float(np.ceil(np.log2(n_test)))
        print(f"Kraft auto: {n_test:,} test samples over all channels -> t = {t_auto:g} bits", file=sys.stderr)
        kraft_t.append(t_auto)
        for d in data.values():
            for fit_end in (VALIDATION - pd.DateOffset(months=3), VALIDATION, SPLIT):
                d[3][(fit_end, 1000 + t_auto, "fast")] = d[3]["code_bits"] + t_auto
    if args.kraft_cusum:
        n_test = sum(int((d[0] >= np.datetime64(SPLIT)).sum()) for d in data.values())
        t_cusum = float(np.ceil(np.log2(n_test)))
    full_range = (SPLIT, pd.Timestamp(test_end))
    y_true = lab[lab["EndTime"] > SPLIT].copy()
    y_true["StartTime"] = y_true["StartTime"].clip(lower=SPLIT)
    merge = np.timedelta64(int(args.merge_minutes * 60e9), "ns")

    events_iv = {ch: P.Interval(*[P.closed(r.StartTime, r.EndTime) for r in lab[lab["Channel"] == ch].itertuples()])
                 for ch in data}
    all_events = P.Interval(*[P.closed(r.StartTime, r.EndTime) for r in lab.itertuples()])

    def channel_flags(ch, q, factor, fit_end, lo, hi, slow=False, timed=False):
        ts, b, sl, thr, kind = data[ch]
        win = (ts >= np.datetime64(lo)) & (ts < np.datetime64(hi))
        if timed:
            per_kind = np.array([thr[(pd.Timestamp(fit_end), q, "fast", kd)] * factor for kd in (0, 1, 2)],
                                dtype=np.float32)
            flag = b > per_kind[kind]
        elif q >= 2000:
            flag = thr["cusum"] >= np.float32(q - 2000)
        elif q >= 1000 and "kcost" in thr:
            flag = thr["kcost"] > np.float32(thr[(pd.Timestamp(fit_end), q, "fast")] * factor)
        else:
            flag = b > np.float32(thr[(pd.Timestamp(fit_end), q, "fast")] * factor)
        if slow:
            flag |= sl > np.float32(thr[(pd.Timestamp(fit_end), q, "slow")] * factor)
        return ts[win & flag]

    def to_events(flag_t):
        if len(flag_t) == 0:
            return []
        brk = np.nonzero(np.diff(flag_t) > merge)[0]
        return list(zip(flag_t[np.r_[0, brk + 1]], flag_t[np.r_[brk, len(flag_t) - 1]]))

    def muted_channels(q, factor, lo, slow=False, timed=False):
        """Channels with a false detection in the 3 months before `lo` (thresholds fitted before them)."""
        pre = lo - pd.DateOffset(months=3)
        out = set()
        for ch in data:
            for a, e in to_events(channel_flags(ch, q, factor, pre, pre, lo, slow, timed)):
                if (P.closed(pd.Timestamp(a), pd.Timestamp(e)) & all_events).empty:
                    out.add(ch)
                    break
        return out

    def detect(q, factor, mute, fit_end, lo, hi, slow=False, timed=False):
        """Thresholds fitted on nominal samples before fit_end; detections in [lo, hi)."""
        muted = muted_channels(q, factor, lo, slow, timed) if mute else set()
        iv = []
        for ch in data:
            if ch in muted:
                continue
            iv += [P.closed(pd.Timestamp(a), pd.Timestamp(e))
                   for a, e in to_events(channel_flags(ch, q, factor, fit_end, lo, hi, slow, timed))]
        return P.Interval(*iv), len(muted)

    rules = [(q, f, m, sl, tm) for q in list(args.quantiles) + [-k for k in args.budgets] + [1000 + t for t in kraft_t]
             + ([2000 + t_cusum + o for o in args.cusum_offsets] if args.kraft_cusum else [])
             for f in args.factors
             for m in ([False, True] if args.mute else [False]) for sl in ([False, True] if args.slow else [False])
             for tm in ([False, True] if args.time_aware and 0 <= q < 1000 else [False])]
    name = lambda r: ((f"cumulative Kraft, t={r[0] - 2000:g} bits (no training)" if r[0] >= 2000  # noqa: E731
                       else f"Kraft b+{r[0] - 1000:g} bits (no training)" if r[0] >= 1000
                       else f"q={r[0]}" if r[0] >= 0 else f"budget {-r[0]:g}/year")
                      + (f", x{r[1]}" if r[1] != 1 else "") + (", mute" if r[2] else "")
                      + (", +slow memory" if r[3] else "") + (", time-aware" if r[4] else ""))

    # Choose the rule on the validation months only (thresholds fitted before them).
    y_val = lab[(lab["EndTime"] > VALIDATION) & (lab["StartTime"] < SPLIT)].copy()
    y_val["StartTime"] = y_val["StartTime"].clip(lower=VALIDATION)
    y_val["EndTime"] = y_val["EndTime"].clip(upper=SPLIT)
    n_val = y_val[y_val["Category"].isin(["Rare Event", "Anomaly"])]["ID"].nunique()
    val_f = {}
    for r in rules:
        ev, _ = detect(r[0], r[1], r[2], VALIDATION, VALIDATION, SPLIT, r[3], r[4])
        val_f[r] = esa_event_scores(y_val, ev, (VALIDATION, SPLIT))["f05"] if n_val else float("nan")
    # Ties go to the more conservative rule (higher quantile, higher factor, muting).
    best = max(rules, key=lambda r: (val_f[r] if val_f[r] == val_f[r] else -1, r[0], r[1], r[2], not r[3], not r[4]))
    print(f"Validation ({VALIDATION.date()} to {SPLIT.date()}, {n_val} events): F0.5 per rule "
          + ", ".join(f"{name(r)}: {v:.3f}" for r, v in val_f.items()) + f"; chosen: {name(best)}\n")

    print("| Rule | Muted channels | Detections | TP | FP | FN | "
          "Corrected precision | Recall | **Corrected event-wise F0.5** | Alarming precision |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rules:
        events, n_muted = detect(r[0], r[1], r[2], SPLIT, SPLIT, pd.Timestamp(test_end) + pd.Timedelta(seconds=1),
                                 r[3], r[4])
        res = esa_event_scores(y_true, events, full_range)
        mark = " (chosen on validation)" if r == best else ""
        print(f"| {name(r)}{mark} | {n_muted} | {len(list(events))} | {res['tp']} | {res['fp']} | {res['fn']} | "
              f"{res['precision']:.3f} | {res['recall']:.3f} | **{res['f05']:.3f}** | {res['alarming']:.3f} |",
              flush=True)


    if args.report is not None:
        write_report(args.report, best, name(best), data, labels, lab, channel_flags, to_events, muted_channels,
                     pd.Timestamp(test_end) + pd.Timedelta(seconds=1))

    if args.official is not None:
        ESAScores, ChannelAwareFScore, ADTQC = load_official_metrics(args.official)
        # Test labels exactly as ESA-ADB builds them: target channels, events
        # entirely inside the test period, anomaly-type columns attached.
        test_lo = pd.Timestamp(min(d[0][np.searchsorted(d[0], np.datetime64(SPLIT))] for d in data.values()))
        test_hi = pd.Timestamp(test_end)
        yt = labels[labels["Channel"].isin(names)]
        yt = yt[(yt["StartTime"] >= test_lo) & (yt["EndTime"] <= test_hi)].drop(columns=["Category"])
        cols = list(types.columns[-4:])
        yt = yt.merge(types[["ID"] + cols], on="ID", how="left")
        chans = pd.read_csv(io.BytesIO(z.read(f"{root}/channels.csv")))
        subsystems = {sub: [*v] for sub, v in chans[chans["Channel"].isin(names)].groupby("Subsystem")["Channel"]}
        q, factor, mute, slow, timed = best
        muted = muted_channels(q, factor, SPLIT, slow, timed) if mute else set()
        per_channel = {}
        for ch in names:
            ts = data[ch][0]
            iv = []
            if ch not in muted:
                flag_t = channel_flags(ch, q, factor, SPLIT, SPLIT, test_hi + pd.Timedelta(seconds=1), slow, timed)
                for a, e in to_events(flag_t):
                    k = np.searchsorted(ts, e, "right")
                    end = ts[k] if k < len(ts) else e + med_dt[ch]  # a flag covers [t, next sample)
                    iv.append((pd.Timestamp(a), pd.Timestamp(end)))
            per_channel[ch] = iv
        glob = change_list([(a, e) for ch in names for a, e in per_channel[ch]], test_lo, test_hi)
        if args.attribute:
            # Kraft attribution: the global detections are fixed; around each one, count the samples
            # examined (all channels, +-merge window) and name the channels whose cost reaches
            # b + log2(that count). Expected false channels per detection <= 1 if the model is calibrated.
            pad = pd.Timedelta(minutes=args.merge_minutes)
            union = P.Interval(*[P.closed(a, e) for ch in names for a, e in per_channel[ch]])
            added, t_used = 0, []
            for atom in union:
                lo, hi = np.datetime64(atom.lower - pad), np.datetime64(atom.upper + pad)
                wins = {}
                for ch in names:
                    if ch in muted:
                        continue
                    ts, cost, _sl, thr_ch, _k = data[ch]
                    i, j = np.searchsorted(ts, lo), np.searchsorted(ts, hi, "right")
                    wins[ch] = (i, j)
                n = sum(j - i for i, j in wins.values())
                if n == 0:
                    continue
                t_attr = float(np.log2(n))
                t_used.append(t_attr)
                for ch, (i, j) in wins.items():
                    ts, cost, _sl, thr_ch, _k = data[ch]
                    hit = np.nonzero(cost[i:j] >= thr_ch["code_bits"] + t_attr)[0]
                    if len(hit) == 0:
                        continue
                    a, e = ts[i + hit[0]], ts[i + hit[-1]]
                    k = np.searchsorted(ts, e, "right")
                    end = ts[k] if k < len(ts) else e + med_dt[ch]
                    if not any(pd.Timestamp(a) <= y and pd.Timestamp(end) >= x for x, y in per_channel[ch]):
                        per_channel[ch].append((pd.Timestamp(a), pd.Timestamp(end)))
                        added += 1
            print(f"Kraft attribution: {added} channel intervals added around {len(t_used)} detections "
                  f"(t_attr median {np.median(t_used) if t_used else float('nan'):.1f} bits)", file=sys.stderr)
        per_channel = {ch: change_list(sorted(iv), test_lo, test_hi) for ch, iv in per_channel.items()}
        sel = {"Category": ["Rare Event", "Anomaly"]}
        out = {}
        import contextlib  # ESA-ADB's affiliation code prints debug lists; keep stdout clean
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        out.update({f"ESA {k}": v for k, v in ESAScores(betas=0.5, select_labels=sel).score(
            yt.drop(columns=["Channel"]), glob).items()})
        out.update({f"ChannelAware {k}": v for k, v in ChannelAwareFScore(beta=0.5, select_labels=sel).score(
            yt.copy(), dict(per_channel), subsystems).items()})
        ytg = yt.copy()
        ytg["Channel"] = "global"
        out.update({f"ADTQC {k}": v for k, v in ADTQC(select_labels=sel).score(ytg, {"global": glob}).items()})
        quiet.__exit__(None, None, None)
        n_ev = yt[yt["Category"].isin(sel["Category"])]["ID"].nunique()
        print(f"\nESA-ADB's own metric code, rule chosen on validation ({name(best)}), {n_ev} test events:\n")
        print("| Metric | Value |\n|---|---:|")
        for k, v in out.items():
            print(f"| {k} | {v:.3f} |" if isinstance(v, float) else f"| {k} | {v} |")



if __name__ == "__main__":
    main()
