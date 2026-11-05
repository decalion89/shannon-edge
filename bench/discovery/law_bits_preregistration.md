# How many bits of communication is a law of nature worth? Pre-registration

Committed before the run. The script is
`bench/discovery/law_bits.py`. Only the data were downloaded
beforehand; nothing was computed on them.

## Question

The floor for sending a sensor with a guarantee
(`bench/discovery/limit/README.md`) leaves five levers. One is to
reduce "what the world says that is new" by sharing a better model of
the world.

By Solomonoff and Kolmogorov, compressing is explaining. So every law
of nature known to both ends should remove bits from the link for
ever. **How many?** No measurement of this on real telemetry was found.

## Data

NOAA CO-OPS station 9414290, San Francisco: 6-minute water levels,
verified, metres with 1 mm resolution, downloaded through the public
API.
* 2022: training.
* 2023: test.

## The law

The astronomical tide.
* Water level = Z0 + Σ over 29 standard constituents (M2, S2, N2, K1,
  O1 and others) of a_k cos(ω_k t) + b_k sin(ω_k t).
* The angular speeds ω_k are fixed by celestial mechanics.
* Amplitudes and phases are fitted by least squares on 2022.
* Nodal corrections are ignored.
* Both ends compute the tide from the same float32 coefficients, so it
  is exactly shared.

## Encodings

Each encoding guarantees |error| ≤ δ on every 2023 sample, with
δ = robust σ of the 2022 first differences, as in the noise-scale
protocol.
* **A, protocol alone:** lattice of step 2δ on the level, flight
  profile.
* **B, protocol + law:** the same lattice on the residual
  (level − tide), flight profile, plus the one-time cost of the
  coefficients.
* **L, lossless reference:** millimetre codes, flight profile.

## Hypotheses

* **T1.** The law saves ≥ 20% of the protocol's bytes: B ≤ 0.80·A.
* **T2.** Protocol + law needs ≤ 25% of the lossless stream.

**Also reported:** bits per sample the law is worth, and the variance
the tide explains.

## Meaning

**If T1 holds:** a known law of nature measurably shrinks the link, and
we have a number for "how much communication a law is worth" on real
data. This makes concrete the claim that scientific knowledge is
communication capacity.

**If it fails:** the adaptive compressor already captures what the law
says. That is also informative: statistical learning would then make
explicit laws unnecessary for the link.

## Result (run once; `bench/results/data/law_bits.csv`)

```
test samples 87,600; delta = 19.9 mm; tide model explains 98.9% of 2022 variance
L lossless (mm codes):          69,332 B = 6.332 bit/sample
A protocol alone:               17,017 B = 1.554 bit/sample
B protocol + law (incl. 236 B of coefficients): 9,776 B = 0.893 bit/sample
bits per sample the law is worth: 0.661  (42.6% of the protocol's bytes)
T1 (law saves >= 20% of the protocol's bytes): HOLDS
T2 (protocol + law <= 25% of lossless): HOLDS  (ratio 0.141)
```

**T1 and T2 hold.**

| Encoding (2023, every sample within ±19.9 mm) | bit/sample | Share of lossless |
|---|---:|---:|
| Lossless millimetres | 6.332 | 100% |
| Noise-scale protocol alone | 1.554 | 24.5% |
| **Protocol + the law of the tides** | **0.893** | **14.1%** |

* **The law is worth 0.66 bit per sample:** 42.6% of what the protocol
  alone sends. The adaptive compressor learns a lot, but not what
  celestial mechanics already knows.
* **The law costs 236 bytes once** (59 float32 coefficients). It saves
  7,241 bytes in the first year, about **30 times its own
  description**, and keeps saving for as long as the law holds.
* Lossless → noise scale → plus the law: 6.33 → 1.55 → 0.89 bit/sample,
  a factor of 7 overall with a guarantee on every sample.

**What it means:** on real telemetry, a shared law of nature is
measurable link capacity, here 43% of the remaining bytes. This makes
literal "compressing is explaining": the better both ends understand
the world, the less they need to say.

**Caveats:**
* One station, one law that is known to be very strong (98.9% of the
  variance).
* δ here is the robust σ of 6-minute differences, which includes waves
  and seiches.
* Nodal corrections were omitted. Including them would only improve
  the law's share.
