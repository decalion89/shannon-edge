"""UCI MetroPT-3 air compressor (CC BY 4.0) -> 68-byte records.

Usage: python3 -I conv_metropt.py "MetroPT3(AirCompressor).csv" OUT.bin

1,516,948 rows (about one every 10 s, Feb-Sep 2020), in file order:
  u32 time        seconds since 1970 of the logged timestamp (naive, as UTC)
  f64 x 7         TP2, TP3, H1, DV_pressure, Reservoirs, Oil_temperature,
                  Motor_current: the analog channels. The CSV prints them
                  as float64 with up to 17 significant digits (e.g.
                  -0.0120000000000004), i.e. a float64 dump; we store the
                  exact IEEE-754 float64 bits (Python float() of the text,
                  which round-trips: repr(x) parses back to the same bits).
                  Not quantized, not narrowed to float32.
  u8 x 8          COMP, DV_eletric, Towers, MPG, LPS, Pressure_switch,
                  Oil_level, Caudal_impulses: the digital channels; every
                  value is exactly 0.0 or 1.0 (checked), stored as 0/1.
The leading unnamed index column is dropped (checked: it is 10 * row).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from common import write

src, out = sys.argv[1], sys.argv[2]
df = pd.read_csv(src, dtype=str)
idx = df.columns[0]
assert (df[idx].astype(np.int64).to_numpy() == 10 * np.arange(len(df))).all()
analog = ["TP2", "TP3", "H1", "DV_pressure", "Reservoirs", "Oil_temperature", "Motor_current"]
digital = ["COMP", "DV_eletric", "Towers", "MPG", "LPS", "Pressure_switch", "Oil_level", "Caudal_impulses"]
assert list(df.columns[1:]) == ["timestamp"] + analog + digital, list(df.columns)
t = pd.to_datetime(df["timestamp"], format="%Y-%m-%d %H:%M:%S")
fields = [["time_s", "<u4"]] + [[c, "<f8"] for c in analog] + [[c, "u1"] for c in digital]
arr = np.zeros(len(df), dtype=np.dtype([(n, t) for n, t in fields]))
secs = t.dt.as_unit("s").astype("int64").to_numpy()  # explicit unit (pandas 3 defaults to us)
assert (pd.to_datetime(secs, unit="s").strftime("%Y-%m-%d %H:%M:%S") == df["timestamp"].to_numpy()).all()
arr["time_s"] = secs
for c in analog:
    s = df[c]
    v = np.array([float(x) for x in s], dtype=np.float64)
    # exactness: the text is the shortest repr of the stored double, so the
    # text can be regenerated from the bits (bijective, nothing lost)
    mism = sum(repr(x) != s_ for x, s_ in zip(v.tolist(), s))
    print(c, "values whose text != repr(float64):", mism)
    arr[c] = v
for c in digital:
    s = df[c]
    assert s.isin(["0.0", "1.0"]).all(), (c, s.unique()[:5])
    arr[c] = (s == "1.0").to_numpy().astype(np.uint8)
print("rows", len(df))
write(
    out,
    arr,
    fields,
    "https://archive.ics.uci.edu/dataset/791 (CC BY 4.0), doi:10.24432/C5VW3R",
    "Metro train air-production unit: 7 analog float64 (exact bits) + 8 digital 0/1 + u32 time.",
)
