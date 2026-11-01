"""Shared helpers for the converters: write records + a layout JSON.

Layout JSON: {"record_len": L, "fields": [[name, numpy_dtype_str], ...],
"source": ..., "notes": ...}. The numpy dtypes are little-endian ("<i2",
"<f4", ...); the record is the packed concatenation of the fields, no padding.
"""
import json
import hashlib
import numpy as np


def write(out_bin, arr, fields, source, notes):
    dt = np.dtype([(n, t) for n, t in fields])
    assert arr.dtype == dt, (arr.dtype, dt)
    raw = arr.tobytes()
    with open(out_bin, "wb") as f:
        f.write(raw)
    meta = {
        "record_len": dt.itemsize,
        "records": int(arr.shape[0]),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "fields": fields,
        "source": source,
        "notes": notes,
    }
    with open(out_bin[:-4] + ".json", "w") as f:
        json.dump(meta, f, indent=1)
    print(json.dumps({k: meta[k] for k in ("record_len", "records", "bytes", "sha256")}))


def fixed_decimal(col, scale_digits, name):
    """Exact integer value of decimal strings with at most `scale_digits`
    fractional digits, i.e. int(s * 10**scale_digits). Raises if any string
    has more fractional digits than that (would not be exact)."""
    import pandas as pd

    s = col.astype(str)
    neg = s.str.startswith("-")
    body = s.str.lstrip("-")
    parts = body.str.split(".", n=1, expand=True)
    ip = parts[0]
    fp = parts[1].fillna("") if parts.shape[1] > 1 else pd.Series([""] * len(s), index=s.index)
    fp = fp.str.rstrip("0")
    bad = fp.str.len() > scale_digits
    if bad.any():
        raise ValueError(f"{name}: {int(bad.sum())} values have > {scale_digits} decimals, e.g. {s[bad].iloc[0]!r}")
    fp = fp.str.ljust(scale_digits, "0") if scale_digits else fp
    v = (ip + fp).astype(np.int64)
    return np.where(neg, -v, v)
