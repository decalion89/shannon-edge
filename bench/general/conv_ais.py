"""NOAA/BOEM MarineCadastre AIS (US federal data) -> 34-byte position records.

Usage: python3 -I conv_ais.py AIS_2023_01_01.zip OUT_FEED.bin OUT_TRACKS.bin [HOUR_END=12]

Rows of 2023-01-01 with BaseDateTime before HOUR_END:00:00 UTC. Every value
is a decimal from the CSV stored as an exact scaled integer (the scale is
the CSV's own number of decimals, verified for every value; AIS itself
transmits these as integers: lat/lon in 1/10000 min, SOG/COG in 0.1):
  u32 mmsi
  u32 time_s       Unix seconds (UTC)
  i32 lat_1e5      LAT  x 1e5   (CSV has 5 decimals)
  i32 lon_1e5      LON  x 1e5
  i16 sog_x10      SOG knots x 10
  i16 cog_x10      COG deg   x 10
  u16 heading      Heading deg (511 = not available, as in AIS)
  u16 vessel_type  (0xFFFF = empty)
  u8  status       navigational status (0xFF = empty)
  u16 length_m     (0xFFFF = empty)
  u16 width_m      (0xFFFF = empty)
  u16 draft_x10    Draft m x 10 (0xFFFF = empty)
  u16 cargo        (0xFFFF = empty)
  u8  tclass       TransceiverClass A=0, B=1
Dropped: the three text columns VesselName, IMO, CallSign (static, per
vessel). Two orders of the same records are written:
  FEED   = file order (as published; close to a receiver's arrival order,
           all vessels interleaved),
  TRACKS = stable sort by (mmsi, time): one track after another, how a
           GPS-track store would hold them.
"""
import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from common import fixed_decimal, write

src, out_feed, out_tracks = sys.argv[1], sys.argv[2], sys.argv[3]
hour_end = int(sys.argv[4]) if len(sys.argv) > 4 else 12
cut = f"2023-01-01T{hour_end:02d}:00:00"
fields = [
    ["mmsi", "<u4"], ["time_s", "<u4"], ["lat_1e5", "<i4"], ["lon_1e5", "<i4"],
    ["sog_x10", "<i2"], ["cog_x10", "<i2"], ["heading", "<u2"], ["vessel_type", "<u2"],
    ["status", "u1"], ["length_m", "<u2"], ["width_m", "<u2"], ["draft_x10", "<u2"],
    ["cargo", "<u2"], ["tclass", "u1"],
]
dt = np.dtype([(n, t) for n, t in fields])
spec = [  # csv column, field, decimals, missing allowed
    ("MMSI", "mmsi", 0, False), ("LAT", "lat_1e5", 5, False), ("LON", "lon_1e5", 5, False),
    ("SOG", "sog_x10", 1, False), ("COG", "cog_x10", 1, False), ("Heading", "heading", 0, False),
    ("VesselType", "vessel_type", 0, True), ("Status", "status", 0, True),
    ("Length", "length_m", 0, True), ("Width", "width_m", 0, True),
    ("Draft", "draft_x10", 1, True), ("Cargo", "cargo", 0, True),
]
chunks = []
zf = zipfile.ZipFile(src)
with zf.open("AIS_2023_01_01.csv") as fh:
    for df in pd.read_csv(io.TextIOWrapper(fh), dtype=str, keep_default_na=False, chunksize=1_000_000):
        df = df[df["BaseDateTime"] < cut]
        a = np.zeros(len(df), dtype=dt)
        t = pd.to_datetime(df["BaseDateTime"], format="%Y-%m-%dT%H:%M:%S")
        secs = t.dt.as_unit("s").astype("int64").to_numpy()  # explicit unit (pandas 3 defaults to us)
        assert (pd.to_datetime(secs, unit="s").strftime("%Y-%m-%dT%H:%M:%S") == df["BaseDateTime"].to_numpy()).all()
        a["time_s"] = secs
        for col, f, d, opt in spec:
            s = df[col]
            miss = (s == "").to_numpy()
            assert opt or not miss.any(), col
            info = np.iinfo(dt[f])
            sentinel = info.max
            v = np.full(len(df), sentinel, dtype=np.int64)
            if (~miss).any():
                vv = fixed_decimal(s[~miss], d, col)
                assert vv.min() >= info.min and vv.max() < sentinel, (col, vv.min(), vv.max())
                v[~miss] = vv
            a[f] = v
        tc = df["TransceiverClass"]
        assert tc.isin(["A", "B"]).all()
        a["tclass"] = (tc == "B").to_numpy()
        chunks.append(a)
        print("chunk kept", len(a), flush=True)
arr = np.concatenate(chunks)
src_desc = ("https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2023/AIS_2023_01_01.zip "
            "(MarineCadastre.gov, NOAA OCM/BOEM, USCG receivers; US federal data, InPort: "
            "access constraints none, no explicit licence)")
write(out_feed, arr, fields, src_desc, f"AIS positions before {cut} UTC, file order.")
order = np.lexsort((arr["time_s"], arr["mmsi"]))
write(out_tracks, arr[order], fields, src_desc, f"AIS positions before {cut} UTC, sorted by (mmsi, time), stable.")
