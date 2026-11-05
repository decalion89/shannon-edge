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
with no fixed horizon. 
## First attempt with two codes: also negative (`bench/ecg_ville.py`)

Setup:
* Q, "the rhythm repeats": each sample is predicted from the same offset
  after the R peak of the last unflagged beat, and the residual is coded
  with a discrete Laplace law.
* R: the flight profile.
* Beat evidence S = Σ(ℓ_Q − ℓ_R); alarm when S ≥ t.

| t (bits) | Abnormal beats flagged (sensitivity) | SVEB | VEB | F | Normal beats flagged (FPR) | False beat alarms per hour | Bound: beats * 2^-t |
|---|---:|---:|---:|---:|---:|---:|---:|
| auto (ceil log2 beats per record) | 0.999 (10601/10608) | 0.999 (2779/2781) | 0.999 (7005/7009) | 0.999 (802/803) | 0.9990 (90031/90125) | 4079.73 | 44.0 |
| 4 | 0.999 (10601/10608) | 0.999 (2779/2781) | 0.999 (7005/7009) | 0.999 (802/803) | 0.9990 (90031/90125) | 4079.73 | 6,295.8 |
| 8 | 0.999 (10601/10608) | 0.999 (2779/2781) | 0.999 (7005/7009) | 0.999 (802/803) | 0.9990 (90031/90125) | 4079.73 | 393.5 |
| 16 | 0.999 (10601/10608) | 0.999 (2779/2781) | 0.999 (7005/7009) | 0.999 (802/803) | 0.9990 (90031/90125) | 4079.73 | 1.5 |
| 32 | 0.999 (10601/10608) | 0.999 (2779/2781) | 0.999 (7005/7009) | 0.999 (802/803) | 0.9990 (90031/90125) | 4079.73 | 0.0 |

Every beat is flagged, normal ones included, at every t. The 44 expected
false alarms become 90,031. **The guarantee did not fail; its premise
did.** The bound holds only if the data follow Q, and here Q is a poor
code even for normal beats. Beat-to-beat residuals carry baseline wander
and ±1-sample jitter on the steep QRS, so the flight profile's
sample-to-sample prediction beats Q on every beat. Then S is large
everywhere.

Lesson: in the two-code test, the training-free guarantee is only as good
as the "normal" code Q, which must be at least as good as the general
code on normal data. Building such a Q for ECG morphology, without
training, is the open problem. It is not solved here.

## Second two-code attempt: better, still not calibrated (`--design delta`)

Q now codes each sample's *change* by the mean change at the same offset
over the last 8 unflagged beats. This makes it insensitive to baseline
wander. Q also uses a per-offset Laplace scale, and pays log2(5) bits to
choose the best ±2-sample alignment, which keeps it a valid code.

| t (bits) | Abnormal beats flagged (sensitivity) | SVEB | VEB | F | Normal beats flagged (FPR) | False beat alarms per hour | Bound: beats * 2^-t |
|---|---:|---:|---:|---:|---:|---:|---:|
| auto (ceil log2 beats per record) | 0.943 (10002/10608) | 0.862 (2397/2781) | 0.999 (7000/7009) | 0.735 (590/803) | 0.7042 (63465/90125) | 2875.90 | 44.0 |
| 0 | 0.951 (10092/10608) | 0.891 (2478/2781) | 0.999 (7001/7009) | 0.745 (598/803) | 0.7538 (67934/90125) | 3078.41 | 100,733.0 |
| 8 | 0.949 (10063/10608) | 0.883 (2457/2781) | 0.999 (7000/7009) | 0.736 (591/803) | 0.7285 (65654/90125) | 2975.09 | 393.5 |
| 16 | 0.941 (9981/10608) | 0.857 (2384/2781) | 0.999 (7000/7009) | 0.725 (582/803) | 0.6946 (62598/90125) | 2836.61 | 1.5 |

Ventricular beats are now caught almost all (0.999), and so are 86% of
supraventricular beats. But 70% of normal beats are flagged as well, far
above the 44 expected false alarms. **Q is still not calibrated:** on
most normal beats it codes worse than the flight profile, which is a
strong general model.

The open problem is unchanged: a training-free code of a normal heartbeat
that is at least as good as a strong general compressor on normal beats.
Two hand-built codes failed. A plausible route, not tried, is to build the
template into the general model itself, as a context of the flight
profile, so that Q ⊇ R by construction.

## Third attempt: a beat-shape code and the per-sample bound (`--design kraft`)

There is no second code this time. The beat-shape code Q of the delta
design (shift 0, so strictly sequential) is used on its own. A sample
alarms when its cost under Q reaches b + t bits (b = 11). The Kraft bound
needs only that Q is not overconfident. A model that *expects* the normal
shape turns a deformed beat into per-sample surprise. Q's residual law is a
Laplace with a small wide component of weight w (8x the scale) for heavy
tails.

**Protocol.** The first exploratory runs looked at all 44 records. From
then on, the standard inter-patient split of de Chazal et al. (2004) was
used. w and t were chosen on DS1 (22 records) and DS2 (22 records) was
evaluated once.

* DS1, t = 8: w = 0 flags 64% of VEB at 5.5% normal-beat FPR, but it is
  overconfident. w = 0.05 is calibrated but blind (1% of VEB).
* w = 1e-4 was chosen: it matches w = 0 in power (63.5% VEB, 4.9% FPR)
  and stays within the bound.

**DS2, held out, evaluated once:**

| t (bits) | Abnormal beats flagged (sensitivity) | SVEB | VEB | F | Normal beats flagged (FPR) | False beat alarms per hour | Bound: beats * 2^-t |
|---|---:|---:|---:|---:|---:|---:|---:|
| auto (ceil log2 beats per record) | 0.001 (4/5453) | 0.000 (0/1837) | 0.001 (4/3221) | 0.000 (0/388) | 0.0000 (1/44259) | 0.09 | 22.0 |
| 8 | 0.541 (2951/5453) | 0.023 (43/1837) | 0.854 (2752/3221) | 0.394 (153/388) | 0.0265 (1173/44259) | 106.31 | 55,859.4 |

* **t = 8, no training, no data from any other patient: 85.4% of
  ventricular beats are flagged, with 2.65% of normal beats flagged.**
  For orientation only: de Chazal et al.'s *supervised* classifier,
  trained on DS1, reported VEB sensitivity 77.7% and positive
  predictivity 81.9% on DS2. Ours flags "abnormal", not a class, so the
  two are not directly comparable. Our VEB positive predictivity is about
  0.67.
* Supraventricular beats are not seen (2%). Their shape is normal; what is
  abnormal is their timing, which this code does not model.
* With t = auto, a guarantee of one expected false alarm per record, it is
  blind (4 of 5,453).

**Why a strict guarantee is blind here: the rarity limit.** In the
records rich in ventricular beats, they are not rare: 34% of beats in 208,
32% in 200, 27% in 233, 26% in 106, 22% in 119 and 15% in 203. A calibrated
adaptive model learns them, and assigns each one roughly the probability of
its frequency. A sample that recurs at frequency f cannot cost much more
than log₂(1/f) plus the bits of its shape. So a detector that guarantees
false-alarm rate α can only flag events that are about as rare as α, under
the patient's own law. Clinical abnormality is defined by medical
knowledge, not by rarity. **A training-free statistical guarantee and a
clinical definition of abnormal are different targets.** A frequent
abnormality can be detected only by a code that has *not* learned it,
which means bringing in prior knowledge of what a normal beat is.

Where that is acceptable, a loose bound at t = 8 gives a useful,
training-free detector of ventricular beats. That bound allows up to
N·2^-8 false sample-alarms, and observed false alarms are far below it.
