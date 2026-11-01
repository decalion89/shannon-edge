# Beyond space: everyday fixed-length records

Do sedge's packet codecs help outside spacecraft telemetry? Five public
datasets from different domains (seven binary files, 37–139 MB each)
were converted faithfully into fixed-length binary records:
* integers keep their native encoding;
* decimals are stored as exact scaled integers, each value checked;
* floats keep their exact bits.

Every sedge and baseline output was decompressed and checked to be
byte-identical. Scripts: `bench/general/`, converters `conv_*.py`. Usage
is described below.

## Datasets

| Name | Domain | Source (licence) | Record | Records × bytes |
|---|---|---|---|---|
| ecg_incart | Medical ECG | PhysioNet INCART 1.0.0, records I01–I10 (ODC-By 1.0) | native 12 × i16 frame, 257 Hz | 4,626,000 × 24 |
| power_uci | Smart meter | UCI #235 household power (CC BY 4.0) | u32 time + 7 × u16 scaled exact decimals | 2,075,259 × 18 |
| metropt | Industrial compressor | UCI #791 MetroPT-3 (CC BY 4.0) | u32 time + 7 × float64 (exact bits) + 8 × u8 | 1,516,948 × 68 |
| metropt_codes | same | same | same values as u16 codebook indices (codebook 174,520 B not counted below) | 1,516,948 × 26 |
| can_aegis | Vehicle CAN | Zenodo 3267184 AEGIS, Driver1 trips 7–10 (CC BY 4.0) | f32 time + 103 × float32 (decoded CAN, GPS, IMU, 20 Hz) | 93,690 × 416 |
| ais_tracks / ais_feed | Ship GPS (AIS) | NOAA MarineCadastre AIS 2023-01-01, before 12:00 UTC (US federal data; NOAA states no access constraints but names no licence) | 34-byte position report; `tracks` sorted by ship and time, `feed` in file order | 4,076,512 × 34 |

## Compression ratio (higher is better)

Baselines:
* **planes**: the record matrix is transposed into byte planes.
* **fieldΔ**: each field is replaced by its zigzag difference from the
  previous record (an XOR for floats). This is the fair "smart engineer"
  baseline.
* **zstd per record**: one zstd stream flushed after every record, the
  like-for-like rival of sedge's per-record payloads.
* **One stream**: a measurement-only patched copy running one arithmetic
  coder across all records. It is not in the repository.

| Dataset | zstd -19 --long | xz -9e | fieldΔ+planes+xz | zstd -19 per record | **sedge fast** | **v2 2^12** | **v2 2^16** | v2 2^16, one stream | sedge CM, whole file |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| power_uci | 2.67 | 3.76 | **6.69** | 1.07 | 5.46 | 5.72 | 5.82 | 6.52 | **6.69** |
| can_aegis | 2.98 | 3.44 | 4.42 (planes+xz 4.54) | 2.56 | 4.27 | 4.33 | 4.50 | 4.52 | 4.35 |
| ecg_incart | 1.57 | 2.26 | 2.94 | 0.93 | 2.61 | 2.74 | 2.77 | 2.88 | **3.04** |
| metropt (float64) | 6.75 | 8.78 | 3.52 | 3.40 | 3.62 | 4.03 | 4.80 | 4.92 | **18.98** |
| metropt_codes | 3.18 | 3.98 | 8.84 | 1.42 | 6.56 | 7.44 | 7.61 | 8.44 | **9.23** |
| ais_tracks | 5.17 | 6.62 | 12.59 | 1.97 | 10.34 | 11.28 | 11.38 | **12.77** | 11.91 |
| ais_feed | 3.14 | **4.16** | 2.02 | 1.61 | 1.85 | 2.18 | 2.23 | 2.27 | 3.32 |

Speed (MB/s, one core, shared machine, about ±30%):
* sedge fast compresses at 30–69 MB/s (decompression 21–62) with
  39–896 KiB of state.
* v2: 3.5–15 MB/s.
* zstd -19 --long: 1.1–2.4 MB/s. xz -9e: 0.6–1.7 MB/s.
* fieldΔ+planes+zstd -3, numpy transform included, runs at 43–69 MB/s.
  It is 0–13% smaller than sedge fast on every dataset except CAN, where
  it is 2% larger.

Ground-learned recipes, learned on the first 10% and measured on the other
90%, shrink sedge fast's output on every dataset:

| Dataset | Smaller by |
|---|---:|
| CAN | 2.7% |
| power | 3.6% |
| ECG | 4.4% |
| AIS tracks | 6.8% |
| AIS feed | 8.8% |
| metropt_codes | 10.4% |
| metropt | 21.7% |

## Verdict

* **Where sedge wins: coding each record as it arrives.** This is the
  setting of a sensor, a meter, a vehicle or a medical device that sends
  readings one by one, with little memory and no batching. There the
  packet codecs produce **28–83% fewer bytes than zstd one record at a
  time** on every dataset. sedge fast is about 5x smaller than per-record
  zstd at 30–70 MB/s, and v2 saves another 4–10%.
* **sedge's general CM model is the best or tied-best archiver on 4 of 7
  files**: power, ECG, metropt and metropt_codes. On metropt as published
  (float64 dumps) it is 2.2x better than xz -9e (18.98 vs 8.78).
* **Where the packet codecs lose:**
  * Whole-file archiving against the smart baseline: they tie or lose by
    1–16%.
  * Interleaved streams (`ais_feed`: the previous record is a different
    ship): 87% worse than xz.
  * Raw float64 dumps with few distinct values: about 2x worse than xz.
    Whole 8-byte values repeat, which LZ copies and a byte-above model
    cannot.
* **What it points to:**
  * an optional one-stream mode, since the per-record boundary costs
    0.32–0.34 B/record on every dataset;
  * a context keyed by stream id, for interleaved sources;
  * numeric-field prediction: on ECG the byte models miss most of the
    16-bit structure, and a linear-prediction ECG codec would probably
    beat all of these (not measured).

## Reproduce

Scripts live in `bench/general/`. Use a working directory `G` containing:
* `build/`: a release build of this repository;
* `dl/<dataset>/`: the downloads;
* `data/`, `results/` and `work/`: outputs.

The converter usage lines are in each `conv_*.py`. To benchmark, run
`bash run_all.sh G [names]` (sedge and the baselines), then `run_extra.sh`
and `run_cm.sh`. `python3 -I table.py G/results <names>` prints the
tables. `run_extra.sh` also needs the one-stream measurement patch, which
is not in the repository.

## Ground-learned field relations (`bench/analysis/relations.py`)

A question prompted by the ECG data: are some fields an exact function of
others? In a 12-lead ECG, four leads are, by definition, combinations of
two others: Einthoven's III = II − I, and Goldberger's aVR, aVL and aVF.
The ground can discover such relations and upload them; the spacecraft or
device then sends only what cannot be deduced.

**How the relations are found.** On the first 10% of the records only,
for every integer field k, the script tries
r = x_k − ⌊(a·x_i + b·x_j)/2⌋ for pairs of other fields and a, b in −4..4.
It keeps the candidate whose residual has the lowest empirical entropy,
when that is below 2 bits. Targets are never used as predictors, so
decoding has a fixed order. The transform is exact and reversible; the
script verifies the inverse on every record.

**INCART ECG.** With no ECG knowledge given to it, the search finds three
relations:
* lead I from II and III, exact up to a per-record constant (the ADC
  offset);
* aVR from II and aVF (residual entropy 0.86 bits);
* aVL from II and III (0.57 bits).

All results are verified bit for bit:

| | Original | Relations | Relations + field delta (16-bit, zigzag, record by record) |
|---|---:|---:|---:|
| sedge v2 2^16, packet by packet | 40,064,022 (2.77x) | 30,840,871 (3.60x) | **29,372,154 (3.78x)** |
| sedge fast, packet by packet | 42,619,401 (2.61x) | **33,263,886 (3.34x)** | 34,707,406 (3.20x) |
| xz -9e, whole file | 49,144,136 (2.26x) | 40,841,060 (2.72x) | — |
| fieldΔ + planes + xz -9e, whole file | 37,822,840 (2.94x) | **28,905,944 (3.84x)** | — |

* The relations cut every codec by 17–24%. They are a property of the
  data, not of sedge.
* With the relations and a numeric field delta, sedge v2, coding packet by
  packet at about 5 MB/s, is within 1.6% of the best whole-file archiver,
  which runs at 1.4 MB/s and sees the whole file at once.
* The fast profile prefers the relations without the field delta.

**Other datasets.**
* Household power: no relation found.
* MetroPT-3 codebook file: four relations among identical digital
  signals, with no measurable effect (5,184,963 → 5,184,096 bytes). v2's
  cross-column contexts already capture identical columns.

Relations pay where the data carry physically derived signals, as in the
derived ECG leads. Elsewhere they cost nothing.

**Now in the codec: `shannon_edge::fields`.** `RecordTransform::learn`
finds the relations by least squares on up to 4096 history records, then
scores them by residual entropy on up to 65,536 records. It learns in
0.3 s instead of minutes, and finds the same three ECG relations. It also
picks per-field deltas when they lower the entropy.

The uplink is 60 bytes for the ECG (`docs/FORMAT.md`).
`examples/packet_transform_bench.rs` learns on the first 10%, transforms,
compresses packet by packet, decompresses, inverts and checks every record:

| Dataset (layout) | v2 2^16 | v2 + relations | v2 + relations + deltas | fast | fast + deltas | Best whole-file baseline |
|---|---:|---:|---:|---:|---:|---:|
| ECG (`i16le*12`) | 2.77x | 3.60x | **3.82x** | 3.34x (relations) | 3.25x | 2.94x (3.84x with the same relations) |
| power (`u32le,u16le*7`) | 5.82x | (none found) | **6.00x** | 5.46x | 4.83x | 6.69x |
| AIS tracks (34-byte report) | 11.38x | (none found) | **11.98x** | 10.34x | 9.63x | 12.59x |
| MetroPT codes (`u32le,u16le*7,u8*8`) | 7.61x | 7.61x | **7.97x** | 6.57x | 6.32x | 8.84x |

* Numeric field deltas help packet profile v2 on every dataset, by 3–6%.
* They *hurt* the fast profile: its "same as the byte above?" flag is
  what makes it fast and small, and zigzag deltas break that.
* The rule is therefore deltas for v2 and relations for both.
* The whole-file archivers stay ahead by 1–11%, except on ECG, where v2
  with relations and deltas is within 0.6% of the best of them while
  coding each record as it arrives.
