# Compression and loss protection, separated: Venus Express

Shannon's separation principle says that, for a point-to-point link,
compressing as well as possible and then adding exactly the redundancy the
channel needs loses nothing compared with designing both together.
CCSDS 124 (POCKET+) builds loss tolerance into the compressor (robustness
level R repeats mask changes over R+1 packets); our earlier attempts did the
same (epochs, key packets; `venus_robustness.md`) and lost most of the
compression advantage. Here the packet profile runs at full strength (every
packet teaches the model) and a packet-level Reed–Solomon erasure code
(`shannon_edge::fec`) protects the compressed payloads: each group of G
payloads gets m parity packets, and any m lost packets of the group, data
or parity, are rebuilt exactly.

**Setup.** Venus Express housekeeping packets of the CCSDS 124 test
vectors; the first 10% (15,120 packets) prime the model, the remaining
136,080 packets (12,247,200 bytes) are the test link. Tables 2^16, epochs of
4096 packets from the primed origin (to recover from a group the parity
cannot rebuild). Every packet on the link, data or parity, is lost i.i.d.
"Decoded" is the fraction of all test packets the receiver ends up with,
each verified byte for byte; lost packets rebuilt from parity count as
decoded. Sizes include all parity bytes. Produced by
`cargo run --release --example packet_fec -- venus-express.ccsds 90 16 sizes.txt`.

## sedge packet profile + erasure code

| Group G | Parity m | sedge + parity: bytes | CCSDS 124 R=0 + same parity: bytes | Decoded at 0.1% loss | 1% | 5% |
|---:|---:|---:|---:|---:|---:|---:|
| 16 | 1 | 3382924 | 5172099 | 97.62% | 25.72% | 1.45% |
| 16 | 2 | 3644498 | 5571979 | 100.00% | 91.50% | 7.81% |
| 16 | 3 | 3906072 | 5971859 | 100.00% | 100.00% | 25.51% |
| 32 | 2 | 3396454 | 5191259 | 100.00% | 66.73% | 2.51% |
| 32 | 3 | 3534006 | 5400779 | 100.00% | 99.54% | 7.67% |
| 32 | 4 | 3671558 | 5610299 | 100.00% | 100.00% | 26.65% |
| 32 | 6 | 3946662 | 6029339 | 100.00% | 100.00% | 82.53% |
| 32 | 8 | 4221766 | 6448379 | 100.00% | 100.00% | 100.00% |
| 64 | 3 | 3341430 | 5100056 | 100.00% | 89.29% | 2.53% |
| 64 | 4 | 3414790 | 5209335 | 100.00% | 96.68% | 4.89% |
| 64 | 6 | 3561510 | 5427893 | 100.00% | 100.00% | 23.72% |
| 64 | 10 | 3854950 | 5865009 | 100.00% | 100.00% | 94.27% |
| 64 | 12 | 4001670 | 6083567 | 100.00% | 100.00% | 100.00% |

"CCSDS 124 R=0 + same parity": the same erasure code applied to the
per-packet outputs of CCSDS 124 at its most compact setting (R=0, pt=14,
ft=10⁵, rt=10⁶; sizes from `bench/c/ccsds124_loss.c`). For CCSDS 124 its
built-in robustness is the better option (below).

## CCSDS 124 under the same loss

Measured with `bench/c/ccsds124_loss.c` (open C implementation,
tanagraspace/ccsds124): packet-by-packet compression with the automatic
parameter schedule of `ccsds124_compress`, the same i.i.d. loss generator
and seed as `examples/packet_robust.rs`, the decompressor told about every
gap (`ccsds124_decompressor_notify_packet_loss`), and every output compared
with the original. CCSDS 124 cannot rebuild a lost packet, so the ceiling
is the fraction of packets received (99.9%, 99.02%, 95.04%).

| CCSDS 124 configuration | Bytes | Correct at 0.1% loss | 1% | 5% |
|---|---:|---:|---:|---:|
| R=0, pt=14, ft=10⁵, rt=10⁶ (most compact) | 4,772,219 | 0.82% | 0.03% | — |
| R=1, pt=20, ft=10⁵, rt=10⁶ | 4,976,442 | 99.89% | 14.99% | 0.59% |
| R=2, pt=20, ft=10⁵, rt=10⁶ | 5,123,900 | 99.89% | 99.02% | 91.66% |
| R=2, pt=20, ft=10³, rt=10³ | 5,137,524 | — | 99.02% | 94.29% |
| R=3, pt=50, ft=10⁵, rt=10⁶ | 5,241,460 | — | — | 95.04% |

(R=1 at 1% loss: after the first two consecutive losses, decoding stops
until the next uncompressed packet. R=3–7 all reach 95.04% at 5% loss;
R=3, pt=50 is the smallest of those tried.)

## Best against best, at each loss rate

| Loss | CCSDS 124, smallest config at its ceiling | sedge + erasure code, smallest config at 100% | Difference |
|---:|---|---|---:|
| 0.1% | R=1: 4,976,442 bytes, 99.89% | G=32, m=2: 3,396,454 bytes, 100.00% | **−31.7%** |
| 1% | R=2: 5,123,900 bytes, 99.02% | G=64, m=6: 3,561,510 bytes, 100.00% | **−30.5%** |
| 5% | R=3: 5,241,460 bytes, 95.04% | G=64, m=12: 4,001,670 bytes, 100.00% | **−23.7%** |

The no-loss advantage (−34.9% vs CCSDS 124 R=0 on this split) survives
loss almost intact, and the receiver also gets back the packets that were
lost, which CCSDS 124 by design cannot.

## Costs and limits, stated plainly

* **Latency on loss.** Without loss nothing waits (the code is systematic).
  When a packet is lost, the receiver must wait for the group's parity:
  up to G + m packets (76 packets for G=64, m=12) before decoding resumes.
  CCSDS 124 decodes the next received packet immediately.
* **i.i.d. loss only.** Bursts longer than m packets defeat a group; real
  links would interleave groups, or size G and m from the link's measured
  loss statistics. Not evaluated here.
* **Parity overhead depends on the longest payload in a group** (symbols
  are padded); the totals above count it.
* **Epochs** (4096) cover the rare unrecoverable group; their cost is
  included (3,121,350 bytes without parity vs 3,108,861 without epochs).
* **Speed and memory** are those of the packet profile (1.2–1.7 MB/s,
  ~1.3 MiB at 2^16) against CCSDS 124's ~15 MB/s and a few hundred bytes.
* The erasure code is a textbook Cauchy Reed–Solomon code, not new; what
  is measured here is the combination: a learning compressor that cannot
  tolerate loss on its own, made loss-proof by separate channel coding.
* Observation, not yet investigated: with R=0–2 at high loss, the open
  implementation's `ccsds124_decompress_packet_checked` sometimes reported
  an output as accuracy-guaranteed that did not match the original (e.g.
  4,591 packets for R=2 at 5% loss). This may be a misuse of the API in our
  harness; it does not affect the "correct" columns, which compare with
  the original data.
