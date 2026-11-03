# The limit for transmitting a sensor with a per-sample error guarantee

**Problem.** Send a source X so that every reconstructed sample obeys
|X − Y| ≤ δ. What is the minimum rate R∞(δ) any method can achieve?
This is Kolmogorov's ε-entropy with a sup-norm (per-sample) criterion.

## 1. The floor (Shannon lower bound for a max-error criterion)

The error X − Y lies in [−δ, δ], so its entropy is at most log2(2δ).
Therefore

    R∞(δ) ≥ I(X;Y)/n ≥ h(X) − log2(2δ)    (bits/sample, h = differential entropy rate)

Every sensor has noise. For X = S + N with N independent white noise,
h(X) ≥ h(N): adding an independent variable never lowers entropy. With
Gaussian noise of standard deviation σ_N:

    R∞(δ) ≥ log2( sqrt(2πe) · σ_N / (2δ) ),   so at δ = σ_N:  R∞ ≥ log2(sqrt(2πe)/2) = 1.047 bits/sample

**No method can send a sensor with white Gaussian noise σ, guaranteeing
every sample within σ, for less than about 1.05 bits per sample.** The
floor does not depend on the sensor, the domain or the technology.

## 2. The exact limit, computed (`eps_entropy.py`)

Blahut–Arimoto with a hard constraint minimises I(X;Y) over channels
supported on |x − y| ≤ δ, for an i.i.d. source on a fine grid. The
discrete Shannon bound is h − log2(2δ + dx).

| Source | δ | Shannon floor | Exact ε-entropy | Uniform lattice (step 2δ) | Lattice excess |
|---|---:|---:|---:|---:|---:|
| Gaussian | 0.5σ | 2.047 | 2.047 | 2.105 | +0.058 |
| Gaussian | **1σ** | **1.047** | **1.047** | **1.241** | **+0.194 (+18.5%)** |
| Gaussian | 2σ | 0.047 | 0.18 | 0.312 | +0.13 |
| Laplace | 0.5σ | 1.943 | 1.946 | 2.014 | +0.07 |

**Notes on the computation:**
* The exact values are the grid computation corrected by the
  discretisation term log2(1 + dx/2δ).
* At δ = 1σ the exact value equals the discrete Shannon bound at
  dx = 0.02 (1.0328 vs 1.0327) and dx = 0.01 (1.0400 vs 1.0399). The
  continuous limit is therefore 1.047 to within about 10⁻⁴.

**Findings:**
* **At the noise scale (δ ≤ σ), the Shannon floor is essentially tight
  for Gaussian noise.** The limit is known in closed form:
  log2(√(2πe)·σ/2δ).
* **The uniform lattice pays a "lattice tax" of 0.19 bit/sample (18.5%)
  at δ = σ.** The lattice is what near-lossless standards use (JPEG-LS,
  CCSDS 123.0-B-2) and what our protocol uses.
  * The tax is small at δ = 0.5σ (0.06) and rises in the coarse regime.
  * It can be recovered in principle by block (vector) coding that
    reaches the ε-entropy. That is an engineering target, not yet
    built.

## 3. Where real data sit

On 297 TSB-AD-U series at δ = robust σ, the protocol spends a median of
1.88 bit/sample (`kolmogorov_limit_preregistration.md`). That is about
0.8 bit above the 1.05 noise floor:
* about 0.19 is the lattice tax;
* the rest is the signal's own innovation (what it says beyond noise)
  plus coder overhead.

The floor uses the true noise σ_N. Our robust σ is estimated from
first differences and can include signal innovation, so for real
series the floor is indicative.

**Prior art.** ε-entropy goes back to Kolmogorov and Tikhomirov (1959)
and Posner, Rodemich and Rumsey (1967, 1971). The Shannon lower bound
for difference distortions is textbook. What is assembled here is its
use as a universal floor for noise-scale telemetry, the numerical
tightness at δ = σ, and the size of the lattice tax.
