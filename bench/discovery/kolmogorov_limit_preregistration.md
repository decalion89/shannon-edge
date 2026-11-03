# Does a 1956 formula predict the cost of noise-scale telemetry? Pre-registration

Committed before the run. The script is
`bench/discovery/kolmogorov_limit.py`.

## Old literature that never became engineering

* **MacKay (1950s)** split information into **structural** content
  (degrees of freedom, Gabor's "logon") and **metrical** content
  (precision, the "metron", a weight of evidence). The noise-scale
  protocol (`protocol_preregistration.md`) sends exactly the metrical
  content a sensor's noise permits. MacKay's framework stayed
  philosophical; see *Information, Mechanism and Meaning*, 1969.
* **Kolmogorov (1956)** gave the rate-distortion function of a
  stationary Gaussian process by **reverse water-filling** on its
  spectrum. It joins MacKay's two aspects in one number: how many
  frequencies rise above a "water level" set by the allowed error
  (structural), and by how much (metrical).
* **Shannon (1953)**, "The lattice theory of information", has been
  revived recently (Rioul et al., arXiv:2306.15540; Entropy 26(1), 86,
  2024). It is not used here.

**Question.** Does Kolmogorov's formula, computed from the normal part
of each real series, predict the bits per sample the protocol actually
spends? If yes, we know where the theoretical limit sits relative to
what we achieve, across domains.

## Fixed method

* **Series.** TSB-AD-U-Eva series with σ > 0 and the error bound held,
  from the bit-layers run: 297 series.
* **Measured rate.** 8·structure_B/n: the flight profile's real bytes on
  the 1σ lattice indices (`bench/results/data/bit_layers_tsbad.csv`,
  committed earlier).
* **Predicted rate.** Gaussian R(D) of the normal prefix's spectrum:
  * Welch's method: 256-sample Hann segments, linear detrend, two-sided,
    normalised to the prefix variance;
  * D = δ²/3, the mean-squared error of a uniform error in [−δ, δ],
    with δ = robust σ as in the protocol.
* **Expectations stated now:**
  * A uniform scalar lattice pays up to about 0.25 bit/sample over R(D)
    at high rate.
  * Real sources are not Gaussian. For a given spectrum the Gaussian is
    the **hardest** source, so a strong coder can fall below the
    Gaussian prediction.
  * Non-stationarity and short prefixes add error.

## Hypotheses

* **K1.** Spearman ρ(predicted, measured) ≥ 0.70 across the series.
* **K2.** The median of (measured − predicted) lies within ±0.5
  bit/sample.

Also reported: per-domain medians, the interquartile range (IQR) of the
gap, and the share of series where the protocol beats the Gaussian
prediction.

## Meaning

* **If both hold:** a 1956 formula, fed only with each sensor's normal
  spectrum and noise scale, predicts the cost of sending what the
  sensor knows. The protocol then runs near the classical limit, and
  the formula becomes a design rule: a link can be sized before
  launch from a sensor's spectrum and noise.
* **If K1 holds and K2 fails:** the formula ranks sensors correctly,
  but there is a systematic gap. Its sign says whether the protocol
  leaves bits on the table or exploits non-Gaussian structure.
* **If K1 fails:** the classical theory does not describe real sensors
  at their noise scale. That would itself be a finding worth
  explaining.

## Result (run once; `bench/results/data/kolmogorov_limit.csv`)

```
297 series
K1 Spearman rho(predicted, measured) = 0.585 (p = 1.3e-28; needs >= 0.70): REFUTED
K2 median (measured - predicted) = -0.108 bits/sample (needs within [-0.5, +0.5]): HOLDS
   medians: predicted 2.145, measured 1.882 bits/sample; IQR of the gap -1.012 .. +0.734
   share of series where the protocol is BELOW the Gaussian limit: 55%
              n  predicted  measured    gap
ds                                         
CATSv2        1      0.316     1.373  1.057
Daphnet       1      6.042     2.273 -3.768
Exathlon     12      3.196     2.113 -1.151
IOPS         15      2.345     1.745 -0.551
LTDB          8      3.206     2.775 -0.387
MGAB          8      0.520     1.326  0.807
MITDB         7      1.747     1.916  0.292
MSL           3      4.360     2.825 -1.897
NAB          21      1.800     1.715  0.136
NEK           7      1.643     2.304  0.751
OPPORTUNITY  24      2.829     2.577 -0.259
Power         1      2.009     1.997 -0.012
SMAP          3      2.919     2.631 -0.181
SMD          26      3.760     1.987 -1.625
SVDB         18      2.906     1.943 -0.986
Stock         8      3.003     1.662 -1.305
TAO           2      9.128     2.762 -6.366
TODS         13      1.641     1.699  0.135
UCR          69      1.601     1.838  0.340
WSD          20      3.440     1.903 -1.387
YAHOO        30      0.506     1.830  1.269
```

* **K1 is refuted:** ρ = 0.585, highly significant but below 0.70. The
  formula ranks sensors only moderately well.
* **K2 holds:** the median gap is −0.11 bit/sample. The 1956 formula
  predicts the **typical** cost of noise-scale telemetry almost exactly
  (2.15 predicted vs 1.88 measured, median bits/sample).
* The protocol beats the Gaussian prediction on 55% of series.

**The gap map (descriptive, not tested).** It shows where the two
depart:
* **Protocol well above the formula:** YAHOO (+1.27), CATSv2 (+1.06),
  MGAB (+0.81), NEK (+0.75), UCR (+0.34).
  * These are **smooth** signals, e.g. MGAB is the Mackey–Glass chaotic
    series. Kolmogorov says they need ~0.3–0.5 bit/sample at the noise
    scale, but the protocol spends 1.3–1.8.
  * The flight profile predicts from contexts of past indices. It has
    **no linear prediction**, so it cannot follow a smooth trajectory
    that moves several lattice steps per sample.
  * This is a concrete, measurable gap in our own coder: roughly
    0.8–1.3 bit/sample on smooth signals.
* **Protocol well below the formula:** TAO, Daphnet, MSL, SMD, WSD,
  Stock (−1.3 to −6).
  * Spikes, steps and discrete levels give a broad spectrum. The
    Gaussian formula reads that as information; a context coder sees
    through it.
  * For a given spectrum, the Gaussian is the hardest source, and these
    signals are far from Gaussian.

**What this gives.**
* A classical bound that predicts the median cost and so serves as a
  design rule for typical sensors.
* A per-domain diagnostic of where our coder is above the limit. Smooth
  signals point to the next improvement: linear prediction on the
  lattice, as the packet profile v2_lp already does.
