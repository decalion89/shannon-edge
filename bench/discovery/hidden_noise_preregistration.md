# Is the noise really noise? Pre-registration

Committed before the run. The script is
`bench/discovery/hidden_noise.py`.

## The assumption everyone makes

The floor for sending a sensor with a per-sample guarantee,
log2(√(2πe)·σ/2δ) (`bench/discovery/limit/README.md`), assumes that
what lies below σ is **white noise**: no structure, no information.
* Every error-bounded scheme throws that part away unexamined:
  JPEG-LS, CCSDS 123 near-lossless, and our protocol.

**If it is not white,** two things follow:
1. the real floor is lower than believed;
2. the discarded part may carry hidden information. Examples:
   interference from other subsystems, thermal patterns, converter
   artefacts.

## Test (fixed)

**Data.** ESA whole missions, 2,000,000 consecutive samples from each
test split:
* Mission 1, channels 41–46;
* Mission 2, channels 18–20. Channels 21–28 have σ = 0 or
  floating-point jitter.

**The discarded part.** For each channel, e_t = v_t − y_t, with y_t
the 1σ lattice reconstruction of the protocol, so |e_t| ≤ δ.
* It is quantised to 64 equal levels over [−δ, δ].
* Under the white-noise assumption it is i.i.d.

**Online KT code lengths, in bits per sample:**
* **order 0:** no context, i.e. the white-noise assumption;
* **order 1:** the previous discarded symbol as context;
* **cross:** the concurrent discarded symbol of another channel of the
  same mission, taking the best other channel. Channels must share
  timestamps.

## Hypotheses

* **N1 (structure in time).** For ≥ 50% of the channels, order 1
  reduces the code length of the discarded part by ≥ 5% compared with
  order 0.
* **N2 (hidden common information).** For at least one channel, the
  cross context reduces it by ≥ 5%.

## Meaning

* **If N1 holds:** the "noise" is not white. The guarantee floor for
  real sensors is lower than the white-noise formula, and part of what
  every error-bounded scheme throws away is predictable.
* **If N2 holds:** the discarded parts of different channels share
  information, such as common-mode interference. The noise of one
  channel would then carry information about others, which no
  error-bounded scheme looks at.
* **If both fail:** the white-noise assumption stands for these
  sensors, and the floor is the real limit.

## Result (run once; `bench/results/data/hidden_noise.csv`)

```
ESA-Mission1 ch41: order-0 4.474 | order-1 3.455 (+22.8%) | cross 3.281 with ch44 (+26.7%)  [uniform would be 6.000] bit/sample
ESA-Mission1 ch42: order-0 5.086 | order-1 4.511 (+11.3%) | cross 4.072 with ch45 (+19.9%)  [uniform would be 6.000] bit/sample
ESA-Mission1 ch43: order-0 4.495 | order-1 3.443 (+23.4%) | cross 3.429 with ch46 (+23.7%)  [uniform would be 6.000] bit/sample
ESA-Mission1 ch44: order-0 4.879 | order-1 4.291 (+12.1%) | cross 3.684 with ch41 (+24.5%)  [uniform would be 6.000] bit/sample
ESA-Mission1 ch45: order-0 4.525 | order-1 3.505 (+22.5%) | cross 3.513 with ch42 (+22.4%)  [uniform would be 6.000] bit/sample
ESA-Mission1 ch46: order-0 4.995 | order-1 4.433 (+11.3%) | cross 3.928 with ch43 (+21.4%)  [uniform would be 6.000] bit/sample
ESA-Mission2 ch18: order-0 5.884 | order-1 5.283 (+10.2%) | cross 5.764 with ch20 (+2.0%)  [uniform would be 6.000] bit/sample
ESA-Mission2 ch19: order-0 5.895 | order-1 5.482 (+7.0%) | cross 5.882 with ch20 (+0.2%)  [uniform would be 6.000] bit/sample
ESA-Mission2 ch20: order-0 5.630 | order-1 4.833 (+14.2%) | cross 5.510 with ch18 (+2.1%)  [uniform would be 6.000] bit/sample

N1 channels whose discarded part is >= 5% compressible from its own past: 100% (needs >= 50%): HOLDS
N2 some channel's discarded part >= 5% predictable from another channel's: HOLDS
```

**N1 holds:** on 9 of 9 channels, the discarded part is 7–23% predictable
from its own past. **N2 holds:** in Mission 1, each channel's discarded
part is 20–27% predictable from its twin (41↔44, 42↔45, 43↔46). In
Mission 2 the cross gain is only ~2%.

**The white-noise assumption is false for these sensors.** What every
error-bounded scheme throws away has structure.

### Diagnostics (post hoc, not tested; first 3,000,000 samples per channel)

| Channel | robust σ | white σ from lag-1 of differences | lag-1 corr. of differences |
|---|---:|---:|---:|
| M1 41–46 | 1.6–2.7·10⁻³ | 1.3–1.5x robust σ | −0.47 to −0.49 |
| M2 18 / 19 / 20 | 3.2 / 7.1 / 5.0·10⁻⁵ | 29x / 3.7x / 18.5x | −0.67 / −0.33 / −0.67 |

* **The noise is not Gaussian.** It is mostly small steps of one or two
  quantisation levels, plus rare large one-sample spikes, with
  "spikes" defined as |difference| > 5 robust σ.
  * Spikes are 3–5% of samples.
  * In Mission 2 they dominate the variance: the white σ is 18–29x the
    robust σ.
  * The Gaussian floor log2(√(2πe)·σ/2δ) therefore overstates their
    entropy, because for a given variance the Gaussian has the maximum
    entropy.
* **Spikes coincide across channels** far more than chance:
  * Mission 1 twins: 15–18x chance, with sample-to-sample differences
    correlated **+0.66 to +0.69**;
  * other Mission 1 pairs: 8.6–10x, with differences correlated
    **−0.44 to −0.46**;
  * Mission 2 pairs: 5.8–14x; differences of channels 18 and 20 are
    correlated −0.48.
* **Reading:**
  * The twin channels share most of their fine-scale fluctuation.
    Either they measure the same physical quantity, or common
    electronics inject the same disturbance.
  * The **anti-correlated** fine-scale fluctuations between groups look
    like a balance constraint: one quantity rises when another falls,
    as with currents sharing a fixed total.
  * Both are information hidden below the noise floor, which no
    per-channel error-bounded scheme exploits.

**Next tests.** Both must be pre-registered before running.
1. **Joint coding of the discarded parts.** Code twin channels' sub-σ
   parts jointly, one given the other, and measure the bytes saved.
2. **Hidden balance laws.** Look for linear combinations of channels
   whose fine-scale differences have near-zero variance. Those would be
   conservation laws visible only below the noise floor.
