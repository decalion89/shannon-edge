# Training-free arrhythmia detection on MIT-BIH: a negative result

`bench/ecg_kraft.py` takes the Kraft rule that works on ESA-AD Mission 1
(`docs/KRAFT_DETECTION.md`) to electrocardiograms.

**Data.** PhysioNet MIT-BIH Arrhythmia Database v1.0.0 (Moody & Mark,
2001; Goldberger et al., 2000), Open Data Commons Attribution License v1.0:
44 half-hour records (the four paced records excluded, as in AAMI EC57),
first lead, raw 11-bit ADC codes, 360 Hz.

**Protocol, fixed before any result was seen.**
* The flight profile starts empty on every record: no training, and no
  other patient's data.
* A sample alarms when its cost reaches b + t bits, with b = 11.
* A beat is flagged if any sample nearest to it alarms.

    python3 bench/ecg_kraft.py mitdb/ --t auto 4 8 12 16 20

| t | Abnormal beats flagged (sensitivity) | SVEB | VEB | F | Normal beats flagged (FPR) | False alarm episodes per hour | Alarm samples / bound N*2^-t |
|---|---:|---:|---:|---:|---:|---:|---:|
| auto (ceil log2 N per record) | 0.000 (1/10608) | 0.000 (0/2781) | 0.000 (1/7009) | 0.000 (0/803) | 0.0001 (5/90125) | 0.23 | 6 / 44.0 |
| 4 | 0.141 (1495/10608) | 0.239 (665/2781) | 0.093 (650/7009) | 0.218 (175/803) | 0.1931 (17404/90125) | 640.57 | 20,195 / 1,787,500.0 |
| 8 | 0.007 (79/10608) | 0.009 (26/2781) | 0.007 (50/7009) | 0.004 (3/803) | 0.0092 (825/90125) | 36.80 | 926 / 111,718.8 |
| 12 | 0.001 (8/10608) | 0.002 (5/2781) | 0.000 (3/7009) | 0.000 (0/803) | 0.0007 (63/90125) | 2.85 | 74 / 6,982.4 |
| 16 | 0.000 (3/10608) | 0.001 (2/2781) | 0.000 (1/7009) | 0.000 (0/803) | 0.0002 (14/90125) | 0.63 | 17 / 436.4 |
| 20 | 0.000 (1/10608) | 0.000 (0/2781) | 0.000 (1/7009) | 0.000 (0/803) | 0.0001 (5/90125) | 0.23 | 6 / 27.3 |

**The bound holds and the detector is blind.**
* Alarming samples stay far below the guarantee at every t. For example,
  at t = 12 there are 74 alarming samples against a bound of 6,982; with
  t = auto there are 6 in 44 records, against a bound of 44.
* Almost no abnormal beat is flagged: 1 of 10,608 with t = auto.
* Only with t = 4 do some flags appear (14% of abnormal beats), and then
  they flag 19% of normal beats as well, which is no better than chance.

**Why: the evidence is spread over the beat, not concentrated in a
sample.** A premature ventricular beat has a different *shape*, built
from ~100 samples. Each sample is still close to the previous one, so the
model predicts each one well. Nothing in a single sample is surprising;
the beat as a whole is. In spacecraft telemetry most labelled anomalies
are abrupt jumps that one sample reveals, which is why the per-sample test
works there (and why it misses the slow events id_155 and id_159).

**What it implies.** The per-sample Kraft test has power only against
anomalies that are surprising sample by sample. Shape or slow anomalies
need evidence accumulated over a window. The way to keep a training-free
guarantee there is to compare two codes. For a calibrated code Q and any
other sequential code R, the bits R saves over Q,
Σᵢ (ℓ_Q(xᵢ) − ℓ_R(xᵢ)), form the logarithm of a nonnegative
supermartingale (E_Q[R/Q] ≤ 1). Ville's inequality then bounds the
probability that it *ever* exceeds t by 2^−t: monitoring is continuous,
with no fixed horizon. This is the next experiment, with R a code that
predicts each beat from the previous one. It is not done yet; nothing here
shows that it works.
