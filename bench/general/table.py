"""Collect results/<name>.log, <name>.baselines.json, <name>.stream.log into a markdown table.

Usage: python3 -I table.py RESULTS_DIR name ...
"""
import json
import os
import re
import sys

rd, names = sys.argv[1], sys.argv[2:]
rows = []
for n in names:
    log = open(os.path.join(rd, n + ".log")).read()
    b = json.load(open(os.path.join(rd, n + ".baselines.json")))
    raw = b["bytes"]
    r = {"name": n, "L": b["record_len"], "N": b["records"], "bytes": raw}
    m = re.search(r"-> (\d+) bytes .*fast profile, memory (\d+) KiB, compress ([\d.]+) MB/s, decompress ([\d.]+)", log)
    r["fast"] = int(m[1]); r["fast_mem"] = m[2]; r["fast_c"] = m[3]; r["fast_d"] = m[4]
    for tb in ("16", "12"):
        m = re.search(rf"-> (\d+) bytes .*tables 2\^{tb}, v2, memory (\d+) KiB, compress ([\d.]+) MB/s, decompress ([\d.]+)", log)
        r["v2_" + tb] = int(m[1]); r[f"v2_{tb}_mem"] = m[2]; r[f"v2_{tb}_c"] = m[3]; r[f"v2_{tb}_d"] = m[4]
    d = re.search(r"default recipes: test \d+ packets -> (\d+) bytes", log)
    l = re.search(r"learned recipes: test \d+ packets -> (\d+) bytes", log)
    c = re.search(r"learned recipes \+ classes: test \d+ packets -> (\d+) bytes.*compress ([\d.]+) MB/s", log)
    r["recipe_gain"] = int(l[1]) / int(d[1]) - 1
    r["classes_gain"] = int(c[1]) / int(d[1]) - 1
    for k, v in b.items():
        if isinstance(v, dict):
            r[k] = v["size"]; r[k + "_c"] = v["comp_MBps"]
    sp = os.path.join(rd, n + ".stream.log")
    if os.path.exists(sp):
        s = open(sp).read()
        m = re.search(r"fast one-stream: (\d+) bytes", s); r["fast_1s"] = int(m[1]) if m else None
        m = re.search(r"v2 2\^16 one-stream: (\d+) bytes", s); r["v2_1s"] = int(m[1]) if m else None
    cm = os.path.join(rd, n + ".cm.log")
    if os.path.exists(cm):
        m = re.search(r"\.bin\s+(\d+)\s+(\d+)\s", open(cm).read())
        r["cm"] = int(m[2]) if m else None
    rows.append(r)

def x(r, k):
    v = r.get(k)
    return f"{r['bytes']/v:.2f}" if v else "—"

cols = [("zstd -19 --long", "zstd19L"), ("xz -9e", "xz9e"), ("bzip2 -9", "bzip2_9"),
        ("planes+zstd", "planes+zstd19L"), ("planes+xz", "planes+xz9e"),
        ("fieldΔ+planes+zstd", "fdelta+planes+zstd19L"), ("fieldΔ+planes+xz", "fdelta+planes+xz9e"),
        ("zstd -19 per record", "zstd19_stream"),
        ("**sedge fast**", "fast"), ("**sedge v2 2^12**", "v2_12"), ("**sedge v2 2^16**", "v2_16"),
        ("sedge fast, 1 stream", "fast_1s"), ("sedge v2 2^16, 1 stream", "v2_1s"),
        ("sedge CM -b 0 (whole file)", "cm")]
print("Compression ratio (original / compressed; higher is better). Every result decompressed and verified.\n")
print("| Dataset | L | records | MB | " + " | ".join(c for c, _ in cols) + " |")
print("|---|---:|---:|---:|" + "---:|" * len(cols))
for r in rows:
    print(f"| {r['name']} | {r['L']} | {r['N']:,} | {r['bytes']/1e6:.1f} | " + " | ".join(x(r, k) for _, k in cols) + " |")
print("\nBytes:\n")
print("| Dataset | " + " | ".join(c for c, _ in cols) + " |")
print("|---|" + "---:|" * len(cols))
for r in rows:
    print(f"| {r['name']} | " + " | ".join(f"{r[k]:,}" if r.get(k) else "—" for _, k in cols) + " |")
print("\nSpeed (MB/s, one core, nice 10, shared machine):\n")
print("| Dataset | sedge fast c/d | v2 2^12 c/d | v2 2^16 c/d | zstd -19 --long c | xz -9e c | fieldΔ+planes+zstd c | fast learned recipes vs default (test 90%) | + classes |")
print("|---|---|---|---|---:|---:|---:|---:|---:|")
for r in rows:
    print(f"| {r['name']} | {r['fast_c']}/{r['fast_d']} ({r['fast_mem']} KiB) | {r['v2_12_c']}/{r['v2_12_d']} ({r['v2_12_mem']} KiB) | {r['v2_16_c']}/{r['v2_16_d']} ({r['v2_16_mem']} KiB) | {r['zstd19L_c']:.1f} | {r['xz9e_c']:.1f} | {r['fdelta+planes+zstd19L_c']:.1f} | {100*r['recipe_gain']:+.1f}% | {100*r['classes_gain']:+.1f}% |")
best_b = ["zstd19L", "xz9e", "bzip2_9", "planes+zstd19L", "planes+xz9e", "fdelta+planes+zstd19L", "fdelta+planes+xz9e"]
print("\nsedge v2 2^16 (per record) vs best whole-file baseline, and vs zstd per record:\n")
for r in rows:
    bb = min(best_b, key=lambda k: r[k])
    print(f"- {r['name']}: v2 {r['v2_16']:,} vs best {bb} {r[bb]:,} ({100*(r['v2_16']/r[bb]-1):+.1f}%); vs zstd per record {100*(r['v2_16']/r['zstd19_stream']-1):+.1f}%; "
          f"per-record flush tax est. (v2 - v2 one stream)/N = {((r['v2_16']-r['v2_1s'])/r['N']) if r.get('v2_1s') else float('nan'):.2f} B/record; "
          f"one-stream v2 vs best {100*(r['v2_1s']/r[bb]-1) if r.get('v2_1s') else float('nan'):+.1f}%")
