"""General-purpose baselines on a fixed-record file, every result verified.

Usage: nice -n 10 python3 -I baselines.py DATA.bin WORKDIR [--skip-stream]

Reads DATA.json (written by the converters) for the record length and field
layout. Single-threaded throughout (-T1). Methods:
  zstd19L     zstd -19 --long=27 -T1 on the file
  xz9e        xz -9e -T1
  bzip2_9     bzip2 -9
  planes+zstd / planes+xz   byte planes: the N x L record matrix transposed
              (all byte 0s, then all byte 1s, ...), then zstd -19 --long / xz -9e
  fdelta+planes+zstd / +xz  "smart engineer": per field, integers replaced by
              their wrapping difference from the previous record (zigzag),
              floats by XOR with the previous record's bits (Gorilla-style),
              then byte planes, then zstd / xz. Uses the known field layout.
  zstd19_stream  per-record streaming: one zstd -19 stream, flushed after
              every record (FLUSH_BLOCK), every record decoded and checked;
              this is the like-for-like competitor of sedge's per-packet
              payloads (as in bench/ccsds124.py).
Writes WORKDIR/<name>.baselines.json and prints one line per method.
"""
import hashlib
import json
import os
import subprocess
import sys
import time

import numpy as np

path, work = sys.argv[1], sys.argv[2]
skip_stream = "--skip-stream" in sys.argv
meta = json.load(open(path[:-4] + ".json"))
L = meta["record_len"]
name = os.path.basename(path)[:-4]
raw = open(path, "rb").read()
assert len(raw) % L == 0
N = len(raw) // L
dt = np.dtype([(n, t) for n, t in meta["fields"]])
assert dt.itemsize == L
os.makedirs(work, exist_ok=True)
res = {"name": name, "bytes": len(raw), "record_len": L, "records": N}


def run_cli(tag, data, comp, decomp, ext):
    """Compress `data` with a CLI (stdin->stdout), time it, verify."""
    src = os.path.join(work, f"{name}.{tag}.in")
    out = src + ext
    with open(src, "wb") as f:
        f.write(data)
    t = time.perf_counter()
    with open(src, "rb") as fi, open(out, "wb") as fo:
        subprocess.run(comp, stdin=fi, stdout=fo, check=True)
    ct = time.perf_counter() - t
    t = time.perf_counter()
    back = subprocess.run(decomp, stdin=open(out, "rb"), stdout=subprocess.PIPE, check=True).stdout
    dt_ = time.perf_counter() - t
    assert hashlib.sha256(back).digest() == hashlib.sha256(data).digest(), tag
    size = os.path.getsize(out)
    os.remove(src)
    os.remove(out)
    return size, ct, dt_


CODECS = {
    "zstd": (["zstd", "-19", "--long=27", "-T1", "-q", "-c"], ["zstd", "-d", "--long=27", "-q", "-c"], ".zst"),
    "xz": (["xz", "-9e", "-T1", "-c"], ["xz", "-d", "-c"], ".xz"),
    "bzip2": (["bzip2", "-9", "-c"], ["bzip2", "-d", "-c"], ".bz2"),
}


def record(tag, size, ct, dt_, extra=""):
    res[tag] = {"size": size, "ratio": len(raw) / size, "comp_MBps": len(raw) / ct / 1e6, "decomp_MBps": len(raw) / dt_ / 1e6}
    print(f"{name} {tag}: {size} bytes ({len(raw)/size:.3f}x), compress {len(raw)/ct/1e6:.2f} MB/s, decompress {len(raw)/dt_/1e6:.1f} MB/s, verified {extra}", flush=True)


# --- transforms (with inverses, checked) ---------------------------------
def planes(b):
    return np.frombuffer(b, np.uint8).reshape(N, L).T.tobytes()


def unplanes(b):
    return np.frombuffer(b, np.uint8).reshape(L, N).T.tobytes()


UINT = {1: np.uint8, 2: np.uint16, 4: np.uint32, 8: np.uint64}
SINT = {1: np.int8, 2: np.int16, 4: np.int32, 8: np.int64}


def fdelta(b):
    a = np.frombuffer(b, dt)
    o = np.empty(N, dt)
    for n in dt.names:
        ft = dt[n]
        w = ft.itemsize
        u = a[n].view(UINT[w]).astype(UINT[w])
        if ft.kind == "f":
            d = u.copy()
            d[1:] = u[1:] ^ u[:-1]
        else:
            d = u.copy()
            d[1:] = u[1:] - u[:-1]  # wrapping
            s = d.view(SINT[w])
            d = ((s << 1) ^ (s >> (8 * w - 1))).view(UINT[w])  # zigzag
        o[n] = d.view(ft)
    return o.tobytes()


def unfdelta(b):
    a = np.frombuffer(b, dt)
    o = np.empty(N, dt)
    for n in dt.names:
        ft = dt[n]
        w = ft.itemsize
        d = a[n].view(UINT[w]).astype(UINT[w])
        if ft.kind == "f":
            u = np.bitwise_xor.accumulate(d)
        else:
            s = (d >> 1).view(SINT[w]) ^ -(d & 1).view(SINT[w])  # unzigzag
            u = np.cumsum(s.view(UINT[w]), dtype=UINT[w])
        o[n] = u.view(ft)
    return o.tobytes()


t = time.perf_counter()
pl = planes(raw)
tp = time.perf_counter() - t
assert unplanes(pl) == raw
t = time.perf_counter()
fd = planes(fdelta(raw))
tf = time.perf_counter() - t
assert unfdelta(unplanes(fd)) == raw
print(f"transforms: planes {len(raw)/tp/1e6:.0f} MB/s, fdelta+planes {len(raw)/tf/1e6:.0f} MB/s (both inverted and checked)")

for tag, data, tt in [("", raw, 0.0), ("planes+", pl, tp), ("fdelta+planes+", fd, tf)]:
    for c in (["zstd", "xz", "bzip2"] if not tag else ["zstd", "xz"]):
        comp, decomp, ext = CODECS[c]
        size, ct, dt_ = run_cli((tag + c).replace("+", "_"), data, comp, decomp, ext)
        record(tag + {"zstd": "zstd19L", "xz": "xz9e", "bzip2": "bzip2_9"}[c], size, ct + tt, dt_ + tt)

if not skip_stream:
    import zstandard

    c = zstandard.ZstdCompressor(level=19).compressobj()
    d = zstandard.ZstdDecompressor().decompressobj()
    mv = memoryview(raw)
    total = 0
    tc = td = 0.0
    for i in range(N):
        p = mv[i * L : (i + 1) * L]
        t = time.perf_counter()
        z = c.compress(p) + c.flush(zstandard.COMPRESSOBJ_FLUSH_BLOCK)
        t2 = time.perf_counter()
        ok = d.decompress(z) == p
        td += time.perf_counter() - t2
        tc += t2 - t
        assert ok, i
        total += len(z)
    record("zstd19_stream", total, tc, td, "(per record)")

json.dump(res, open(os.path.join(work, f"{name}.baselines.json"), "w"), indent=1)
