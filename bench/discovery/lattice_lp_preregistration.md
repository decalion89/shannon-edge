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

## Result (run once; `bench/results/data/lattice_lp.csv`)

```
297 series; predictor chosen: {'ar': 112, 'plain': 111, 'o1': 67, 'o2': 5, 'o3': 2}
L1 pooled reduction vs the current protocol = 3.5% (needs >= 10%): REFUTED
L2 smooth domains (46 series): median drop = -0.207 bit/sample (needs >= 0.5): REFUTED
L3 share of series below the Kolmogorov-Gaussian rate: 55% -> 54% (needs >= 65%): REFUTED
             plain_bps  lp_bps  predicted  gap_plain  gap_lp
ds                                                          
CATSv2           1.373   1.080      0.316      1.057   0.764
Daphnet          2.273   2.274      6.042     -3.768  -3.768
Exathlon         2.113   2.114      3.196     -1.151  -1.151
IOPS             1.745   1.760      2.345     -0.551  -0.556
LTDB             2.775   2.718      3.206     -0.387  -0.387
MGAB             1.326   1.327      0.520      0.807   0.807
MITDB            1.916   1.818      1.747      0.292   0.071
MSL              2.825   2.827      4.360     -1.897  -1.890
NAB              1.715   1.719      1.800      0.136   0.147
NEK              2.304   2.408      1.643      0.751   0.766
OPPORTUNITY      2.577   2.652      2.829     -0.259  -0.256
Power            1.997   2.029      2.009     -0.012   0.020
SMAP             2.631   2.316      2.919     -0.181  -0.603
SMD              1.987   1.908      3.760     -1.625  -1.697
SVDB             1.943   1.955      2.906     -0.986  -0.963
Stock            1.662   1.663      3.003     -1.305  -1.305
TAO              2.762   2.764      9.128     -6.366  -6.365
TODS             1.699   1.779      1.641      0.135   0.138
UCR              1.838   1.805      1.601      0.340   0.342
WSD              1.903   1.874      3.440     -1.387  -1.396
YAHOO            1.830   2.077      0.506      1.269   1.579
```

**All three are refuted:**
* L1: pooled reduction 3.5%, against ≥ 10%.
* L2: on the smooth domains the median bit/sample **rose** by 0.21.
  YAHOO got worse: the predictor chosen on the prefix did not hold on
  the rest of the series.
* L3: 54% of series below Kolmogorov, against ≥ 65%.

**The diagnosis was wrong.** Missing linear prediction is **not** why
the protocol sits above Kolmogorov's rate on smooth signals:
* MGAB is unchanged;
* only CATSv2 (−0.29), MITDB (−0.10) and SMAP (−0.32) gain anything.

**Post hoc, not a result: the more likely reason is a mismatch in the
yardstick.**
* Kolmogorov's formula is a rate-distortion function for **mean-squared
  error** D = δ²/3.
* The protocol guarantees a **maximum** error δ on every sample. That is
  a much stronger promise, whose limit is Kolmogorov's other quantity,
  the ε-entropy.
* At low rates, ~0.5 bit/sample on smooth signals, the MSE criterion
  can let individual samples err far beyond δ. The guarantee cannot.
* So the "gap" on smooth signals is at least partly the price of the
  guarantee, not waste in the coder.
* A fair limit for the protocol needs ε-entropy (L∞) bounds, which have
  no closed form for general processes.
