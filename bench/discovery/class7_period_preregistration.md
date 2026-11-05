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

## Result (run once)

```
training onsets 20, mean phase 0.561 cycles; test onsets 23
test: resultant length R = 0.189; mean phase 0.970
C1 V-test toward the training phase: u = -1.08, one-sided p = 0.86 (needs p < 0.01): REFUTED
test phases (cycles): [0.04 0.12 0.12 0.19 0.2  0.22 0.23 0.32 0.35 0.37 0.54 0.63 0.66 0.7
 0.71 0.75 0.83 0.85 0.89 0.9  0.92 0.94 0.96]
```

**C1 is refuted** (p = 0.86).
* The 23 test onsets are spread over the cycle (R = 0.19), and their
  mean phase is 0.97, not 0.56.
* The 34.85-day period found on the training onsets was a coincidence
  of that sample, as the look-elsewhere p = 0.093 had warned.
* class_7 is not explained by a fixed period either.
