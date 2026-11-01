# The cost of robustness for a learning compressor

**Question.** A source emits packets carrying H bits of information on
average; each packet is lost independently with probability p; the
receiver must get every packet back, waiting at most about G packets.
How many bits per packet must be sent, and how close does sedge (packet
profile + Reed–Solomon erasure code, `venus_fec.md`) get?

**What theory says.** With unlimited delay, compress to H and add the
channel's minimum redundancy: H/(1−p), i.e. an overhead of p/(1−p) (1.01%
at p = 1%). With a finite block, the finite-blocklength law (Polyanskiy,
Poor and Verdú, IEEE Trans. IT 2010) adds a term that shrinks like
Q⁻¹(ε)·√(p(1−p)/n) for a block of n units: small blocks need a large
safety margin. Learning compressors add a constraint of their own: a lost
packet that is never recovered desynchronises the model, so every packet
must come back.

## Where our overhead went

Venus Express, packet profile v2 (2^16, primed, epochs of 4096), payload
sizes of the 136,080 test packets (`SEDGE_SIZES_OUT`); parity chosen so
that fewer than 0.1 groups are expected to fail over the whole stream
(`bench/analysis/overhead.py`):

**packet loss 1.0%: asymptotic minimum overhead p/(1-p) = 1.01%**
| G | m | groups failing (expected) | parity overhead: padded RS (ours) | if parity = mean payload | m/G (no padding, ideal symbols) |
|---:|---:|---:|---:|---:|---:|
| 16 | 4 | 0.012 | 35.0% | 27.4% | 25.0% |
| 32 | 5 | 0.008 | 23.3% | 17.1% | 15.6% |
| 64 | 6 | 0.015 | 14.9% | 10.3% | 9.4% |
| 128 | 7 | 0.076 | 9.4% | 6.0% | 5.5% |
| 256 | 10 | 0.050 | 7.4% | 4.3% | 3.9% |
| 1024 | 22 | 0.067 | 5.5% | 2.4% | 2.1% |
| 4096 | 60 | 0.088 | 6.0% | 1.6% | 1.5% |


Two separate costs:

1. **The finite-block margin** (the m/G column): with groups of 64
   packets, 6 parity packets (9.4%) are needed to make failures rare at 1%
   loss; it falls towards p as groups grow (2.1% at 1,024).
2. **Padding — the hidden one.** Our Reed–Solomon parity packets are as
   long as the *longest* payload of their group (plus a 2-byte length).
   With groups of 64 that costs 1.6x the ideal; with large groups the
   longest payload grows and padding eats the gain from the smaller
   margin (5.5% at 1,024 instead of 2.1%, 6.0% at 4,096).

A byte-chunked code without padding was simulated
(erasures in chunks of 4–8 bytes): it needs the lengths of lost packets,
and sending a 1-byte length per packet costs 4.8% by itself — no better.
So the practical fix is the simple one: **larger groups**, up to the
GF(2^8) limit G + m ≤ 256.

## Measured with larger groups

`SEDGE_PACKET_V2=1 examples/packet_fec` and `SEDGE_PACKET_FAST=1` (every
packet verified, i.i.d. loss of data and parity packets):

| Loss | Best CCSDS 124 | v2 + RS, groups of 64 (before) | **v2 + RS, large groups** | fast + RS, large groups |
|---:|---|---:|---:|---:|
| 0.1% | R=1: 4,976,442, 99.89% | 3,108,186 (−37.5%) | **G=250, m=2: 2,886,474, 100% (−42.0%)** | 3,526,322, 100% (−29.1%) |
| 1% | R=2: 5,123,900, 99.02% | 3,268,004 (−36.2%) | **G=240, m=8: 3,022,098, 100% (−41.0%)** | 3,665,454, 100% (−28.5%) |
| 5% | R=3: 5,241,460, 95.04% | 3,692,702 (−29.5%) | **G=226, m=30: 3,547,406, 100% (−32.3%)** | 4,204,490, 100% (−19.8%) |

Overhead over the unprotected v2 stream (2,843,306 bytes): 1.5% at 0.1%
loss, 6.3% at 1%, 24.8% at 5% (theoretical minimum with unlimited delay:
0.1%, 1.0%, 5.3%). **The price is latency.** After a loss the receiver waits for the group's
parity: up to G + m packets (248 at 1% loss) instead of 70. Without loss,
nothing waits. This is the finite-blocklength trade-off in plain terms:
lower overhead costs delay. Remaining gap to the theoretical minimum at 1%
loss: 6.3% vs 1.0%, from the finite block (3.3% for m/G at G = 240) and
padding (the rest). Not tried: Reed–Solomon over GF(2^16) for groups of
thousands of packets (still limited by padding), or codes over transfer
frames, where real links actually lose data and padding disappears.

The full tables: v2 and fast with all group sizes, below.

### v2
| Group G | Parity m | sedge + parity: bytes | CCSDS 124 R=0 + same parity: bytes | Decoded at 0.1% loss | 1% | 5% |
|---:|---:|---:|---:|---:|---:|---:|
| 16 | 1 | 3092332 | 5172099 | 97.62% | 25.72% | 1.45% |
| 16 | 2 | 3341358 | 5571979 | 100.00% | 91.50% | 7.81% |
| 16 | 3 | 3590384 | 5971859 | 100.00% | 100.00% | 25.51% |
| 32 | 2 | 3108186 | 5191259 | 100.00% | 66.73% | 2.51% |
| 32 | 3 | 3240626 | 5400779 | 100.00% | 99.54% | 7.67% |
| 32 | 4 | 3373066 | 5610299 | 100.00% | 100.00% | 26.65% |
| 32 | 6 | 3637946 | 6029339 | 100.00% | 100.00% | 82.53% |
| 32 | 8 | 3902826 | 6448379 | 100.00% | 100.00% | 100.00% |
| 64 | 3 | 3055655 | 5100056 | 100.00% | 89.29% | 2.53% |
| 64 | 4 | 3126438 | 5209335 | 100.00% | 96.68% | 4.89% |
| 64 | 6 | 3268004 | 5427893 | 100.00% | 100.00% | 23.72% |
| 64 | 10 | 3551136 | 5865009 | 100.00% | 100.00% | 94.27% |
| 64 | 12 | 3692702 | 6083567 | 100.00% | 100.00% | 100.00% |
| 128 | 7 | 3110797 | 5173781 | 100.00% | 100.00% | 5.90% |
| 128 | 8 | 3149010 | 5231147 | 100.00% | 100.00% | 10.03% |
| 250 | 2 | 2886474 | 4834735 | 100.00% | 8.48% | 0.38% |
| 250 | 3 | 2908058 | 4865993 | 100.00% | 25.71% | 0.37% |
| 240 | 8 | 3022098 | 5031491 | 100.00% | 100.00% | 1.09% |
| 240 | 10 | 3066796 | 5096309 | 100.00% | 100.00% | 2.82% |
| 240 | 12 | 3111494 | 5161127 | 100.00% | 100.00% | 5.59% |
| 232 | 24 | 3395234 | 5573675 | 100.00% | 100.00% | 98.64% |
| 226 | 30 | 3547406 | 5800889 | 100.00% | 100.00% | 100.00% |

### fast
| Group G | Parity m | sedge + parity: bytes | CCSDS 124 R=0 + same parity: bytes | Decoded at 0.1% loss | 1% | 5% |
|---:|---:|---:|---:|---:|---:|---:|
| 16 | 1 | 3753963 | 5172099 | 97.62% | 25.72% | 1.45% |
| 16 | 2 | 4025896 | 5571979 | 100.00% | 91.50% | 7.81% |
| 16 | 3 | 4297829 | 5971859 | 100.00% | 100.00% | 25.51% |
| 32 | 2 | 3764002 | 5191259 | 100.00% | 66.73% | 2.51% |
| 32 | 3 | 3904988 | 5400779 | 100.00% | 99.54% | 7.67% |
| 32 | 4 | 4045974 | 5610299 | 100.00% | 100.00% | 26.65% |
| 32 | 6 | 4327946 | 6029339 | 100.00% | 100.00% | 82.53% |
| 32 | 8 | 4609918 | 6448379 | 100.00% | 100.00% | 100.00% |
| 64 | 3 | 3703541 | 5100056 | 100.00% | 89.29% | 2.53% |
| 64 | 4 | 3777378 | 5209335 | 100.00% | 96.68% | 4.89% |
| 64 | 6 | 3925052 | 5427893 | 100.00% | 100.00% | 23.72% |
| 64 | 10 | 4220400 | 5865009 | 100.00% | 100.00% | 94.27% |
| 64 | 12 | 4368074 | 6083567 | 100.00% | 100.00% | 100.00% |
| 128 | 7 | 3757767 | 5173781 | 100.00% | 100.00% | 5.90% |
| 128 | 8 | 3797158 | 5231147 | 100.00% | 100.00% | 10.03% |
| 250 | 2 | 3526322 | 4834735 | 100.00% | 8.48% | 0.38% |
| 250 | 3 | 3548468 | 4865993 | 100.00% | 25.71% | 0.37% |
| 240 | 8 | 3665454 | 5031491 | 100.00% | 100.00% | 1.09% |
| 240 | 10 | 3711310 | 5096309 | 100.00% | 100.00% | 2.82% |
| 240 | 12 | 3757166 | 5161127 | 100.00% | 100.00% | 5.59% |
| 232 | 24 | 4047398 | 5573675 | 100.00% | 100.00% | 98.64% |
| 226 | 30 | 4204490 | 5800889 | 100.00% | 100.00% | 100.00% |
