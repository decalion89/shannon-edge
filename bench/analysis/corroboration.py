#!/usr/bin/env python3
"""POST HOC analysis (designed after seeing that the windowed rule's false alarms are almost all
single-channel; not a confirmatory test). From the per-channel windowed e-value caches written by
bench/esa_chronological.py --window-hours 6 --cache DIR:

* single rule: a channel-window alarms when log2 M >= t_w (the pre-registered rule);
* corroborated rule: alarm when at least 2 channels reach t2 in the same 6-h window, with
  t2 = ceil((log2 W_time + log2 C(n, 2)) / 2): under independence between channels given the
  past, at most one expected false pair-window (W_time windows, n channels);
* union: either, each at one extra bit (budget split in two).

Detections are the flagged samples' intervals, grouped within 6 h, scored with the event-wise
logic of ESA-ADB's ESAScores (esa_event_scores, which reproduces the official values).

Usage: corroboration.py ESA-MissionN.zip CACHE_DIR START END [PAIR_DETECTIONS.csv]
"""
import io
import math
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import portion as P

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from anomaly_esaadb import esa_event_scores  # noqa: E402

W = 6 * 3600 * 10**9


def main():
    zpath, cache, start, end = sys.argv[1:5]
    z = zipfile.ZipFile(zpath)
    root = next(n.split("/")[0] for n in z.namelist() if n.endswith("labels.csv"))
    lab = pd.read_csv(io.BytesIO(z.read(f"{root}/labels.csv")))
    ty = pd.read_csv(io.BytesIO(z.read(f"{root}/anomaly_types.csv")))
    ch = pd.read_csv(io.BytesIO(z.read(f"{root}/channels.csv")))
    for c in ("StartTime", "EndTime"):
        lab[c] = pd.to_datetime(lab[c]).dt.tz_localize(None)
    lab = lab.merge(ty[["ID", "Category"]], on="ID")
    names = list(ch[ch.Target == "YES"].Channel)
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    d = {c: np.load(Path(cache) / f"{root}_{c}_w6.npz") for c in names}
    for c in names:
        x = d[c]
        sel = (x["t"] >= lo.value) & (x["t"] <= hi.value)
        d[c] = {k: x[k][sel] for k in ("t", "excess", "next_t")} | {"windows": x["windows"]}
    n_cw = sum(int(np.count_nonzero((x["windows"] >= lo.value // W) & (x["windows"] * W <= hi.value)))
               for x in d.values())
    w_time = int((hi.value - lo.value) // W) + 1
    n = len(names)
    t_w = math.ceil(math.log2(n_cw))
    t2 = math.ceil((math.log2(w_time) + math.log2(n * (n - 1) / 2)) / 2)
    yt = lab[lab.Channel.isin(names) & (lab.StartTime >= lo) & (lab.EndTime <= hi)]

    def detections(rule):
        flags = []
        if rule in ("single", "union"):
            t1 = t_w + (1 if rule == "union" else 0)
            for x in d.values():
                s = x["excess"] >= t1
                flags += list(zip(x["t"][s], x["next_t"][s]))
        if rule in ("pair", "union"):
            tp = t2 + (1 if rule == "union" else 0)
            per_win = {}
            for c, x in d.items():
                s = x["excess"] >= tp
                for wi in np.unique(x["t"][s] // W):
                    per_win.setdefault(wi, set()).add(c)
            good = {wi for wi, cs in per_win.items() if len(cs) >= 2}
            for x in d.values():
                s = (x["excess"] >= tp) & np.isin(x["t"] // W, list(good))
                flags += list(zip(x["t"][s], x["next_t"][s]))
        flags.sort()
        grouped = []
        for a, e in flags:
            a, e = pd.Timestamp(int(a)), pd.Timestamp(int(min(e, hi.value)))
            if grouped and a - grouped[-1][1] <= pd.Timedelta(hours=6):
                grouped[-1][1] = max(grouped[-1][1], e)
            else:
                grouped.append([a, e])
        return grouped

    print(f"{root}: {n} channels, {w_time:,} 6-h windows, {n_cw:,} channel-windows; t_w = {t_w}, t2 = {t2}\n")
    print("| Rule | Detections | TP | FP | FN | Corrected precision | Recall | Event-wise F0.5 |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for rule in ("single", "pair", "union"):
        g = detections(rule)
        r = esa_event_scores(yt, P.Interval(*[P.closed(a, e) for a, e in g]), (lo, hi))
        if len(sys.argv) > 5 and rule == "pair":
            pd.DataFrame(g, columns=["start", "end"]).to_csv(sys.argv[5], index=False)
        print(f"| {rule} | {len(g)} | {r['tp']} | {r['fp']} | {r['fn']} | {r['precision']:.3f} | {r['recall']:.3f} | "
              f"**{r['f05']:.3f}** |", flush=True)


if __name__ == "__main__":
    main()
