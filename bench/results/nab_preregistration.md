# Pre-registration: detector combination on NAB (written before any NAB result)

**Hypothesis.** On the UCR archive (`ucr_anomaly.md`), a per-file choice
between two training-free detectors raised top-1 accuracy from 134/250
(matrix profile alone) to 141/250. That rule was designed *after* a
first rule failed, so it needs an out-of-sample test. The detectors are:
* the compressor's per-sample surprise (flight profile);
* the matrix-profile discord.

**Data.** The Numenta Anomaly Benchmark (NAB): every data file with at
least one labelled anomaly window (`labels/combined_windows.json`),
fetched from raw.githubusercontent.com/numenta/NAB. It is used for
measurement only.

**Protocol, fixed now.**
* Training prefix: the first 15% of each series (NAB's "probationary
  period"). Test: the rest. Windows that end inside the prefix are
  ignored. Files with no window in the test part are skipped.
* Window m: the period estimated on the prefix, exactly as in
  `bench/ucr_anomaly.py` (first autocorrelation peak, clipped to
  10..500).
* Methods:
  * *surprise*: the flight profile on rank codes, top sample in the test
    part;
  * *mp*: stumpy discord with window m, centre of the top subsequence in
    the test part;
  * *combined*: per file, the method with the larger *training margin*,
    i.e. its top test score divided by its maximum on the prefix
    (surprise: the prefix after its first 10%, as in UCR).
* A prediction is correct if it falls inside any labelled window of the
  test part.

**Success criterion.** The combination beats the matrix profile alone on
the number of correct files. A tie or a loss counts as a failure of the
rule, and will be reported as such.

## Result (run after the protocol above was committed, unchanged)

`python3 bench/nab_combination.py NAB/data NAB/labels/combined_windows.json`

| Method | Correct files (52) |
|---|---:|
| Random test point (expected, from window coverage) | 5.8 (0.111) |
| Compressor surprise | 15 (0.288) |
| Matrix-profile discord | 16 (0.308) |
| **Combination by training margin (pre-registered)** | **23 (0.442)** |
| Either one correct (oracle, not a method) | 28 (0.538) |

**The success criterion is met.** The combination beats the matrix
profile alone by 7 files (+44% relative) and captures 23 of the 28 files
where either detector is right. Both detectors are about 2.6–2.8x the
random baseline, and the combination about 4x.

Taken with UCR (141/250 against 134/250), this supports the rule out of
sample. Each detector's own anomaly-free training range calibrates its
evidence well enough to choose between them, with no training and no
information from other series. The strength of the claim is bounded by
NAB's size (52 files) and by its known label issues.
