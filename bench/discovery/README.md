# Compression-gap microscope

Can a compressor find a law nobody told it about, and then write it down?

* **Where to look:** the code-length gap between nested adaptive models.
* **What the law is:** sparse regression, only in the region the gap points to.

Prior art:
* The gap is transfer entropy (Schreiber 2000).
* Law-writing by sparse regression is SINDy (Brunton et al. 2016).
* MDL pattern selection: e.g. Ibrahim et al. 2016.

Software that rediscovers known laws exists (Eureqa, SINDy, AI Feynman). A
convincing *new* law from real experimental data has not been shown. The
missing piece this tests is *where to look*: compression localises the
region, and regression only works there.

## Phase 1: synthetic positive and negative controls (`microscope.py`)

**The hidden law.** y[t] = 0.6·y[t−1] + 0.5·(x[t−7] − 0.5) + noise, and
only when x[t−7] > 0.5. The noise has standard deviation 0.4. x is an AR(1)
process.

**The negative control** is the same data with no law.

**The instrument knows nothing:**
* the gap is computed for every lag from 0 to 20;
* it is compared with 20 circular time shifts of x, which destroy any
  lagged relation;
* the regime is where knowing x pays for its own learning cost (net gain
  > 0 bits, an MDL rule);
* the law is fitted by thresholded least squares over
  [1, y[t−1], x, x², x³].

Five seeds, 60,000 samples each:

| Seed | Lag found | Law found vs null | Regime found | Law written | Negative control |
|---:|---:|---|---|---|---|
| 0 | **7** | yes | x[t−7] ≥ 1.14 | 0.607·y[t−1] + 0.209·x + 0.076·x² | nothing found |
| 1 | **7** | yes | x[t−7] ≥ 1.15 | −0.271 + 0.589·y[t−1] + 0.520·x | nothing found |
| 2 | **7** | yes | x[t−7] ≥ 1.08 | −0.252 + 0.601·y[t−1] + 0.499·x | nothing found |
| 3 | **7** | yes | x[t−7] ≥ 1.07 | −0.274 + 0.602·y[t−1] + 0.513·x | nothing found |
| 4 | **7** | yes | x[t−7] ≥ 1.08 | −0.251 + 0.614·y[t−1] + 0.489·x | nothing found |

Truth: −0.25 + 0.6·y[t−1] + 0.5·x[t−7], for x[t−7] > 0.5.

* **Detection and lag: 5 of 5.** No false finding in 5 of 5 negative
  controls.
* **The law, written unaided: 4 of 5 exact to within ±0.03 in every
  coefficient.** Seed 0 wrote an equivalent polynomial over the narrow
  regime, where x and x² are nearly collinear.
* **The regime is found conservatively:** a threshold of about 1.1, not
  0.5. Where the effect is weaker than the richer model's learning cost,
  MDL does not count it as a law, by design. Weak laws need more data.
* **Limits:**
  * one synthetic law;
  * two channels;
  * a fixed function library;
  * about 30 s per run in Python.
  The next phases are known physics on real data (it must rediscover only
  what is known) and then real telemetry.
