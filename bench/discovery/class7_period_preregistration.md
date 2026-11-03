# Does the "invisible" class_7 recur with a fixed period? Pre-registration

Committed before the test onsets were examined. The script is
`bench/discovery/class7_period.py`.

**Why.** Mission 1's class_7 is invisible to every local statistic
tried: surprise, fine-scale activity, balance, coupling, sampling
mode and telecommands (`hidden_metadata.md`). The hypothesis is that it
is defined by **when** it happens.

**Exploration (training onsets only, before 2006-10-01, n = 20).**
* Inter-onset intervals cluster near 69–70 days and near 30 days.
* A Rayleigh periodogram over 10–200 days peaks at **P = 34.85 days**,
  R = 0.635.
* Corrected for scanning the period grid, a permutation test over
  random onset times gives p = 0.093: suggestive, **not significant**.

**Test (fixed, no further search).**
* P = 34.85 days.
* Phases are measured from 2000-01-01; the mean phase is fixed from the
  training onsets.
* The class_7 onsets from 2007-01-01 (test period, never examined)
  should cluster at that phase.
* **C1:** V-test (Rayleigh test with a known mean direction), one-sided
  p < 0.01.

**Risk stated now.** The test spans 2007–2014, about 80 cycles. A
period error of 0.05 day drifts the phase by 4 days (0.11 cycle), so a
slightly wrong period weakens the test. That makes it conservative.

**Meaning.**
* **If C1 holds:** the anomaly no statistic sees is predictable **in
  time**. Its signature is a ~35-day cycle, i.e. operational or
  orbital context, not anything in the signal's shape. A detector could
  then watch the predicted windows.
* **If it fails:** the apparent period was a coincidence of the
  training sample.
