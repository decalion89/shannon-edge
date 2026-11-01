# Fast packet profile: Venus Express

`shannon_edge::packet_fast::FastPacketSession`: for every byte, one
adaptive binary decision "same as the byte above?" (one probability per
column and small context: run length, left neighbour changed, column
changed last time; no hashing, no mixing); for each changed byte, **one
symbol** — its delta from the byte above — from an adaptive frequency
table per column (Fenwick tree; two tables per column, by whether the left
neighbour changed). Multi-symbol coding on sedge's binary arithmetic coder
(`Encoder::encode_freq`), integer-only, golden-pinned.

Why it should work: 64% of Venus Express bytes repeat, and the ideal cost
of an adaptive per-column delta model for the changed bytes was estimated
at 3.56 MB before writing any code (Python); the codec reaches 3.85 MB in
total, flags included.

## Venus Express, 151,200 packets × 90 bytes, every packet verified

Speeds: one desktop core, compression only, measured inside the process
for both codecs. CCSDS 124: the open C implementation (tanagraspace,
built with its `-O3 -flto`), time inside `ccsds124_compress_packet` only
(`bench/c/ccsds124_loss.c`); sedge: the whole `compress` call, allocation
included (`examples/packet_fast_bench.rs`).

| Codec | Memory | Bytes | vs best CCSDS 124 | Compress | Decompress |
|---|---:|---:|---:|---:|---:|
| CCSDS 124, best of sweep (R=0, pt=14, ft=10⁵, rt=10⁶) | < 1 KiB | 5,289,939 | — | 26 MB/s | — |
| CCSDS 124, R=2 (robust) | < 1 KiB | 5,679,592 | +7.4% | 25 MB/s | — |
| **sedge fast profile** | 193 KiB | **3,845,622** | **−27.3%** | **~50 MB/s** | ~31 MB/s |
| sedge packet profile v2, 2^12 | 372 KiB | 3,350,925 | −36.7% | 7.0 MB/s | 6.0 MB/s |
| sedge packet profile v2, 2^18 | 6.0 MiB | 2,999,548 | −43.3% | 5.2 MB/s | 4.8 MB/s |

The fast profile is the first sedge codec that is both smaller **and**
faster than CCSDS 124 on this data (~1.9x at compression). It needs more
memory (193 KiB vs a few hundred bytes), and the CCSDS 124 implementation
measured is an open reference implementation, not necessarily the fastest
flight code. Not timed on flight hardware.

Parameter sweep (frequency increment / halving limit): 16/2^13 3,857,702;
16/2^15 3,863,204; 16/2^16 3,900,180; 24/2^16 3,879,521; 32/2^13
3,929,713; **32/2^15 3,845,622**; 32/2^16 3,866,483; 48/2^15 3,852,883.
Variants not kept: delta tables also split by the size of the column's
last change (3,827,607, −0.5%, twice the memory); a second "same"
estimate by bytes changed so far (3,836,807, −0.2%, slower).

## Under packet loss (fast profile + erasure code)

`SEDGE_PACKET_FAST=1 examples/packet_fec` (same setup as `venus_fec.md`):

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

Best against best: 0.1% loss −24.4% vs CCSDS 124 R=1; 1% loss −23.4% vs
R=2; 5% loss −16.7% vs R=3; all with 100% of the packets recovered.

## Held-out inputs and learning curve

| Input | Best CCSDS 124 R=0 | fast | v2 2^14 |
|---|---:|---:|---:|
| housekeeping.bin | 133,187 | 19,476 | 17,363 |
| hiro.bin | 367 | 289 | 189 |
| simple.bin | 367 | 289 | 189 |
| edge-cases.bin | 4,267 | 203 | 507 |

Venus Express, first N packets: 100 → 3,591; 300 → 10,382; 1,000 →
30,797; 10,000 → 260,341 bytes (v2 2^14: 3,126 / 8,846 / 26,024 /
224,425).

## The ground thinks, the spacecraft executes: learned context recipes

The spacecraft has a small CPU; the ground has unlimited compute and the
whole history. So the ground chooses, for every column, which context
the delta tables use — a *recipe* (`packet_fast::recipe`): left neighbour
changed (default), size/sign of the left neighbour's delta, of the
column's last delta, high nibble of the byte above, or left-changed ×
last delta. `FastPacketSession::learn_recipes` scores every recipe on the
history by ideal cost and keeps the cheapest per column; the result is
one byte per column to uplink, and the encoder's work per byte does not
change.

Venus Express, recipes learned on the first 10% (15,120 packets, 0.09 s),
both ends primed with that history, measured on the other 136,080 packets
(`SEDGE_FAST_RECIPES=1 examples/packet_fast_bench`):

| Fast profile, test 90% | Memory | Bytes | Compress |
|---|---:|---:|---:|
| default recipes | 193 KiB | 3,463,245 | ~47–51 MB/s |
| **learned recipes** | 808 KiB | **3,237,111 (−6.5%)** | ~46 MB/s |
| (CCSDS 124 R=0, same packets) | < 1 KiB | 4,772,219 | ~26 MB/s |

Learned recipes: 35 columns left-changed, 8 left-delta, 22 last-delta,
20 above-high, 5 combined. On these packets the fast profile with learned
recipes is −32.2% vs CCSDS 124 R=0, at ~1.8x its speed. The estimate
before writing code (Python, `per-column recipe chosen on the first 10%`)
was −8.0% on the changed bytes; the codec got −6.5% overall.

## Cross-channel dependencies: a negative result

A spacecraft is one physical system: a heater switching on moves several
temperatures, currents and voltages at once. The idea was to let the
ground learn a dependency map between columns (each column's best
predictor, by mutual information, à la Chow–Liu) and code each column with
its *parent's* change in the same packet as context — a different coding
order and one parent per column to uplink, same encoder work per byte.
Scripts: `bench/analysis/parents.py`, `recipes2.py`, `flags.py`.

* Static estimate (empirical conditional entropy, parents chosen on the
  first 10%, measured on the other 90%): 205.7 bits/packet with the left
  neighbour as context, 194.4 with the chosen parent (−5.5%). In 72 of 90
  columns the best predictor is not the neighbouring column: the
  cross-channel structure is real.
* But adaptive models already capture most of it. Ideal adaptive cost on
  the test 90%: changed bytes 2,950,712 → 2,940,658 bytes with parent
  recipes added to the learned recipes (−0.3%); "same?" decisions 260,163
  → 245,866 bytes with "parent changed" added (−5.5% of the flags). About
  −0.7% of the total: not worth a reordered coding loop. Not implemented.
