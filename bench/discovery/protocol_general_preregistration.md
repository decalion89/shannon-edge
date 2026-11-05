# Does the noise-scale protocol generalise beyond spacecraft? Pre-registration

Committed before the run. The script is
`bench/discovery/protocol_general.py`.

**Why.** On ESA Missions 1 and 2 the noise-scale protocol needs 39% and
27% of the CCSDS 121 standard (`protocol_preregistration.md`). Two
missions from one agency do not make a general method. This tests it on
**TSB-AD-M-Eva**: 180 multivariate real-world series from 17 domains,
including medicine, industry, servers, energy and spacecraft.

**Method.** Identical to `protocol.py`, per channel:
* **B1:** CCSDS 121 on the lossless value codes.
* **B2:** CCSDS 121 on the noise-scale lattice indices.
* **P:** the flight profile on the lattice indices.
* σ comes from the benchmark's normal prefix (`tr_N`).
* Channels with σ = 0, indices over 16 bits or a failed bound go
  lossless.
* Alarms are omitted: they are tens of bytes.

From our census, about 15% of series have σ = 0 (discrete signals).
They gain nothing, and they stay in the totals.

**Hypotheses (pooled over all bytes of the 180 series):**
* **G1.** protocol / CCSDS 121 lossless ≤ 0.50.
* **G2.** protocol / CCSDS 121 at the noise scale ≤ 0.85.
* **G3 (breadth).** In ≥ 50% of the domains, the domain's pooled
  protocol / CCSDS 121 ratio is ≤ 0.50.

All are reported per series and per domain, whatever they show.

## Result (run once; `bench/results/data/protocol_tsbad_m.csv`)

```
180 series, 17 domains
G1 pooled protocol / CCSDS 121 lossless = 0.277 (needs <= 0.50): HOLDS
G2 pooled protocol / CCSDS 121 at noise scale = 0.675 (needs <= 0.85): HOLDS
G3 domains where the protocol needs <= half of CCSDS 121: 71% of 17 (needs >= 50%): HOLDS
median per-series protocol / CCSDS 121 = 0.387
ds
CreditCard     0.101
CATSv2         0.168
Exathlon       0.215
PSM            0.215
SMD            0.280
TAO            0.349
MSL            0.358
SVDB           0.372
OPPORTUNITY    0.398
GECCO          0.423
GHL            0.427
MITDB          0.476
SWaT           0.518
LTDB           0.538
SMAP           0.552
Genesis        0.615
Daphnet        0.618
```

* **G1 holds:** pooled over the 180 series, the protocol needs **27.7%**
  of CCSDS 121's bytes.
* **G2 holds:** it is 32.5% smaller than CCSDS 121 on the same
  noise-scale indices.
* **G3 holds:** in 12 of 17 domains (71%), the protocol needs at most
  half of the standard. The per-series median is 0.387.

The weakest domains are Daphnet (0.62), Genesis (0.62), SMAP (0.55),
LTDB (0.54) and SWaT (0.52). They are mostly discrete or low-noise
signals, where σ = 0 or there is little sub-noise detail. Their gain
comes from the coder alone.

**Caveats:**
* Alarms are not included (tens of bytes).
* TSB-AD values are the benchmark's stored floats, some normalised.
  "Noise scale" is the robust σ of the normal prefix as stored.
* 1σ error is a design choice that each user must accept.
