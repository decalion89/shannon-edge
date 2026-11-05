"""MetroPT-3 float64 records -> 26-byte records of value codes + a codebook (lossless).

Usage: python3 -I conv_metropt_codes.py metropt.bin OUT.bin

Each analog channel has only 1,809-5,257 distinct float64 values (a
quantized sensor printed through float arithmetic). Every value is replaced
by its index in the channel's sorted list of distinct values (u16); the
codebook (all distinct float64s, exact bits) is written to OUT.codebook and
its size must be ADDED to every codec's output when comparing (it is the
same for every codec). Record: u32 time, 7 x u16 codes, 8 x u8 digital.
Inverse checked: codebook[code] reproduces the original bits.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from common import write

src, out = sys.argv[1], sys.argv[2]
m = json.load(open(src[:-4] + ".json"))
dt = np.dtype([(n, t) for n, t in m["fields"]])
r = np.fromfile(src, dt)
fields = [[n, "<u2" if t == "<f8" else t] for n, t in m["fields"]]
o = np.zeros(len(r), np.dtype([(n, t) for n, t in fields]))
book = []
for n, t in m["fields"]:
    if t == "<f8":
        bits = r[n].view("<u8")
        u, inv = np.unique(bits, return_inverse=True)
        assert len(u) < 65536
        assert (u[inv] == bits).all()
        o[n] = inv
        book.append(u)
        print(n, len(u), "distinct")
    else:
        o[n] = r[n]
cb = np.concatenate(book).astype("<u8").tobytes()
open(out[:-4] + ".codebook", "wb").write(cb)
print("codebook bytes", len(cb))
write(out, o, fields, m["source"],
      f"MetroPT-3 with analog float64 values replaced by u16 indices into a per-channel sorted codebook of exact float64 bits ({len(cb)} bytes, add to every codec).")
