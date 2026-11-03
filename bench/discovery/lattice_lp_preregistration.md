# Closing the gap to Kolmogorov: linear prediction on the noise-scale lattice. Pre-registration

Committed before the run. The script is `bench/discovery/lattice_lp.py`.

**Why.** The Kolmogorov test (`kolmogorov_limit_preregistration.md`)
showed the protocol spends 0.8–1.3 bit/sample above the classical
Gaussian rate on smooth signals. Its coder has no linear prediction,
so it cannot follow a smooth trajectory that moves several lattice
steps per sample.

**Disclosure.** The "smooth" domains below were chosen **from that
result**: those with a median gap > +0.5 bit/sample, namely YAHOO,
CATSv2, MGAB and NEK. The test asks whether the diagnosed cause is the
real one.

**Method (fixed).**
* **Series:** the same 297 TSB-AD-U-Eva series and the same 1σ lattice.
* **Candidate predictors,** all causal on past indices:
  * none (the current protocol);
  * fixed polynomial predictors of order 1, 2 and 3;
  * a least-squares AR(8) fitted on the normal prefix.
* **Choice:** made on the **normal prefix only**, by real flight bytes.
* **Coding:** the whole series' zigzag residuals go through the flight
  profile, plus side information: 2 bytes, and 64 more for AR
  coefficients. The error bound is unchanged (prediction acts on exact
  integer indices).

**Hypotheses:**
* **L1.** Pooled bytes fall by ≥ 10% against the current protocol.
* **L2.** On the smooth domains, the median drop is ≥ 0.5 bit/sample.
* **L3.** The share of series below the Kolmogorov–Gaussian rate rises
  from 55% to ≥ 65%.
