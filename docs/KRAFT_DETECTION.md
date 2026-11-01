# Compression as training-free anomaly detection: the Kraft bound

A note on the result in `bench/results/esa_adb.md` ("Training-free
thresholds"). The statement is elementary: it rests on the Kraft
inequality (1949). Its use is new to us. Every lossless compressor
becomes an anomaly detector whose false-alarm rate is fixed by a formula
before any data is seen, with no training. We do not know of prior work
that uses it this way for on-board telemetry, but have not searched
exhaustively. Related ideas: likelihood-ratio and e-value tests,
minimum-description-length tests, and Barron's no-hypercompression
inequality.

## Setting

A sequential lossless code assigns sample *i*, given everything before it,
a length ℓᵢ(x) in bits for every possible value x of an alphabet of at most
2^b values. Any uniquely decodable code satisfies Kraft:
Σₓ 2^(−ℓᵢ(x)) ≤ 1. So Qᵢ(x) = 2^(−ℓᵢ(x)) is a (sub-)probability. For an
arithmetic coder, ℓᵢ is the cost actually paid, the "surprise".

Alarm on sample *i* when ℓᵢ(xᵢ) ≥ b + t.

## Statement

Let Pᵢ be the true conditional distribution of sample *i* given the past.
Let Dᵢ = log₂ maxₓ Pᵢ(x)/Qᵢ(x) be the Rényi max-divergence of the truth
from the code (Dᵢ = 0 when the code is exact).

1. **Per sample:** P(alarm on sample *i* | past) ≤ 2^(Dᵢ − t).
2. **Over any run:** the expected number of false alarms in N samples is
   at most Σᵢ 2^(Dᵢ − t). If Dᵢ ≤ D for all *i*, that is N·2^(D − t).
   There is no independence or stationarity assumption: the bound is
   conditional on the past and adds up by linearity of expectation.

**Proof.** Let Sₜ = {x : ℓᵢ(x) ≥ b + t} = {x : Qᵢ(x) ≤ 2^(−b−t)}. It has at
most 2^b elements. Then

Pᵢ(Sₜ) = Σ_{x∈Sₜ} Pᵢ(x) ≤ 2^(Dᵢ) Σ_{x∈Sₜ} Qᵢ(x) ≤ 2^(Dᵢ) · 2^b · 2^(−b−t) = 2^(Dᵢ − t).

Part 2 is the sum of part 1 over *i*. ∎

So choosing t = log₂(N / k) + D gives at most k expected false alarms in N
samples. With D = 0 (a calibrated model) and k = 1 this is the `--kraft
auto` rule: t = ⌈log₂ N⌉.

## What the data says

* **Is the model calibrated enough (D ≤ 0 in effect)?** On ESA-AD
  Mission 1 channels 41–46, 45.8 M nominal training samples
  (`bench/analysis/kraft_calibration.py`), the observed rate of
  ℓ ≥ b + t is below 2^(−t) at every t up to 20, by a factor of 10 to
  400 at t = 4–16. Above that, one sample in 7.6 M on one channel
  exceeds it, which chance explains. The flight model behaves as if
  D ≤ 0: it is conservative, not overconfident.
* **Does it detect?** Corrected event-wise F0.5 on ESA-ADB, with t fixed
  by the formula before scoring and no training:
  * Mission 1 lightweight: 0.705 (trained rule 0.690).
  * Mission 1 full: 0.576 (trained rule 0.279; best published 0.061).
  * Mission 2 lightweight: 0.200 (trained rule 0.725).

## What it does not say

The bound fixes the false-alarm rate, not the miss rate. Choosing k (how
many false alarms an operator accepts) is a decision about risk, not a
consequence of the theorem. On Mission 2, k = 1 over the whole test set is
far too strict: most of its 350 short labelled events stay below b + 26
bits. Detection power depends on how far anomalies push the cost above
the model's normal range. That is a property of the data, which no bound
can promise.

## Why it matters

* **A new spacecraft, sensor or patient** can be monitored from the first
  sample, with a false-alarm guarantee, before any history exists.
* **Thresholds are in bits for every channel**: the same rule for a
  temperature, a voltage or a heart rate, and no per-channel tuning.
* **The detector is the compressor.** It costs nothing extra on board,
  and sender and receiver compute the same value.
