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
