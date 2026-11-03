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
