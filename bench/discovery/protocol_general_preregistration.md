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
