# Do real anomalies break a balance law hidden below the noise floor? Pre-registration

Committed before the test. The script is
`bench/discovery/hidden_law.py`.

## The law (found on training data only, before this file)

On ESA Mission 1, with the first 4,000,000 training samples (before
2006-10-01), the sample-to-sample increments of channels 41, 43 and 45
nearly cancel:
* var(Δ41 + Δ43 + Δ45) is **0.178x** the sum of their variances.
* No other triple of channels 41–46 is below 0.30.
* Their levels do not sum to a constant: the balance holds for the
  fine, fast fluctuations, below the noise scale the protocol discards.
  It looks like a shared reference or supply.

The labels were not looked at.

## Test (fixed)

* **Violation statistic of a window:** mean of (Δ41 + Δ43 + Δ45)² in
  the window, divided by its training mean.
* **Events:** labelled events touching channels 41–46 that start in the
  test period (from 2007-01-01), excluding communication gaps and
  windows shorter than 2 samples.
* **Controls:** for each event, one unlabelled test-period window of
  the same length, drawn at random (seed 0).
* **On-board alarms:** the Kraft rule of `esa_edge_link.py` on channels
  41–46. An event is "missed" if no alarm falls in its window.

## Hypotheses

* **V1.** Events show more violation than controls: one-sided
  Mann–Whitney AUC ≥ 0.65 and p < 0.01.
* **V2.** On events the on-board detector misses, AUC ≥ 0.60 and
  p < 0.05. The hidden law would then see what surprise does not.

A breakdown by anomaly class is reported.

## Meaning

**If V1 and V2 hold:** a law found only in the "noise" detects real
anomalies, including ones the compressor's surprise misses. That turns
discarded noise into a new diagnostic channel.

**If they fail:** the balance is real, but anomalies do not show up in
it on this mission.
