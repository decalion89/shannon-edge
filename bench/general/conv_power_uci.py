"""UCI Individual household electric power consumption (CC BY 4.0) -> 18-byte records.

Usage: python3 -I conv_power_uci.py household_power_consumption.txt OUT.bin

One record per minute (2,075,259), in file order:
  u32 time      seconds since 1970-01-01 of the logged local clock time
                (the file gives naive local time; we encode it as if UTC,
                no DST/timezone adjustment, so it is exactly reversible)
  u16 active    Global_active_power, kW   x 1000 (file has 3 decimals)
  u16 reactive  Global_reactive_power, kW x 1000
  u16 voltage   Voltage, V                x 1000 -> does not fit u16, so x 100
                after checking every value has <= 2 significant decimals
  u16 intensity Global_intensity, A       x 10 (checked: <= 1 decimal)
  u16 sub1..3   Sub_metering_1..3, Wh     x 1  (checked: integers)
Missing values ('?' in the file, 1.25% of rows) -> 0xFFFF in every field
(checked not to collide with a real value). Each scale is the smallest
power of ten that makes every value an exact integer (verified), so the
conversion is lossless with respect to the published text.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from common import fixed_decimal, write

src, out = sys.argv[1], sys.argv[2]
df = pd.read_csv(src, sep=";", dtype=str, na_values=["?"], keep_default_na=False)
t = pd.to_datetime(df["Date"] + " " + df["Time"], format="%d/%m/%Y %H:%M:%S")
secs = t.dt.as_unit("s").astype("int64").to_numpy()  # explicit unit (pandas 3 defaults to us)
# exact: the seconds give back the parsed timestamp (the file writes days and
# months without zero padding, e.g. 1/1/2007, so compare values, not text)
assert (pd.to_datetime(secs, unit="s") == pd.DatetimeIndex(t)).all()
assert (np.diff(secs) == 60).all()  # one record per minute, no gaps
assert secs.min() >= 0 and secs.max() < 2**32
cols = [
    ("Global_active_power", "active_kW_x1000", 3),
    ("Global_reactive_power", "reactive_kW_x1000", 3),
    ("Voltage", "voltage_V_x100", 2),
    ("Global_intensity", "intensity_A_x10", 1),
    ("Sub_metering_1", "sub1_Wh", 0),
    ("Sub_metering_2", "sub2_Wh", 0),
    ("Sub_metering_3", "sub3_Wh", 0),
]
fields = [["time_s", "<u4"]] + [[n, "<u2"] for _, n, _ in cols]
arr = np.zeros(len(df), dtype=np.dtype([(n, t) for n, t in fields]))
arr["time_s"] = secs
miss = df[cols[0][0]].isna().to_numpy()
# Sub_metering_3 is an empty field rather than '?' on missing rows
for src_col, name, d in cols:
    c = df[src_col]
    cm = (c.isna() | (c == "")).to_numpy()  # '?' or empty field
    assert (cm == miss).all(), (src_col, int(cm.sum()), int(miss.sum()))  # missing rows coincide
    v = fixed_decimal(c[~miss], d, src_col)
    assert v.min() >= 0 and v.max() < 0xFFFF, (src_col, v.min(), v.max())
    col = np.full(len(df), 0xFFFF, dtype=np.int64)
    col[~miss] = v
    arr[name] = col
    print(src_col, "max", v.max())
print("rows", len(df), "missing", int(miss.sum()))
write(
    out,
    arr,
    fields,
    "https://archive.ics.uci.edu/dataset/235 (CC BY 4.0), doi:10.24432/C58K54",
    "1-min smart-meter readings of one house, Dec 2006 - Nov 2010; decimals as exact scaled integers; missing = 0xFFFF.",
)
