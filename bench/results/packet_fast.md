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

## How far from the strongest known compressor?

The reference is paq8px v217 `-8` (Mahoney et al.; built from
github.com/hxim/paq8px), the strongest known general compressor family. It
compresses the whole 13.6 MB Venus Express file offline, at roughly 3 KB/s
on this machine.

The first run stopped at 96.2% of the input, after writing 2,301,952
bytes. The process ended without an error message; the cause is unknown.
Extrapolated at the same rate, the whole file comes to about **2.39 MB**.
A second run is in progress to confirm the final size and the round trip.

| Codec | Setting | Bytes | vs paq8px (≈2.39 MB) |
|---|---|---:|---:|
| paq8px -8 | whole file, offline, ~3 KB/s | ≈2,392,000 (extrapolated) | — |
| sedge CM (`sedge bench -b 0 -t 1 -r 90`) | whole file, 0.4 MB/s, verified | 2,849,785 | +19% |
| sedge packet v2, 2^18 | packet by packet, 5 MB/s | 2,999,548 | +25% |
| sedge packet v2, 2^12 | packet by packet, 7 MB/s, 372 KiB | 3,350,925 | +40% |
| sedge fast | packet by packet, ~50 MB/s, 193 KiB | 3,845,622 | +61% |
| CCSDS 124, best of sweep | packet by packet, 26 MB/s | 5,289,939 | +121% |

**There is real headroom.** Even sedge's whole-file model is about 19%
above what the strongest known model reaches, so the remaining bits are not
all noise. The earlier noise-floor analysis (`side_information.md`) bounded
only per-field first-order structure. Coding packet by packet in flight
costs only another ~5%: v2 2^18 against sedge CM on the whole file. The
rest of the gap is model capacity, bought at about 1,000 times the work per
byte.

### Where the gap is: column by column

Each of the 90 columns, compressed as its own 151,200-byte time series:

| | Total over 90 columns |
|---|---:|
| sedge CM | 3,269,020 |
| paq8px -8 | 3,024,998 (−7.5%) |

Cross-column context is worth about 13% to sedge CM: 2,849,785 on the
whole file. The column gap is concentrated. Ten columns carry 65% of it,
and on a few of them paq8px is 1.5–2.5x smaller:

| Column | sedge CM | paq8px | xz -9e | Changed vs previous |
|---:|---:|---:|---:|---:|
| 59 | 27,980 | 11,236 | 35,028 | 36% |
| 63 | 28,877 | 12,183 | 38,320 | 51% |
| 71 | 57,269 | 38,585 | 70,864 | 60% |
| 67 | 45,714 | 30,787 | 61,324 | 59% |
| 60 | 130,374 | 104,463 | 129,852 | 98% |

Hypotheses tested and rejected:
* **Delta-history contexts.** Columns 59, 63 and 67 contain slow ramps
  with fractional slopes, e.g. steps of 3, 3, 3, 4. The ideal adaptive
  cost given the last three deltas (or the last three non-zero deltas) is
  *higher* than given the last delta alone, because the contexts are too
  sparse.
* **Long exact repeats.** xz and zstd do worse than sedge on these
  columns.
* **Audio or linear prediction.** paq8px's block detection classifies
  the streams as generic binary (`default`), so its audio and image models
  are not involved.

paq8px wins with its generic model mix, not a special-purpose model.
Finding which of its components matters is the next step (ablation of its
open-source models). Scripts and data: session scratchpad (`cols/`), not in
the repository.

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

## Numeric fields: a negative result

The Venus Express packets carry multi-byte numbers: a CCSDS primary header
(APID 212, sequence count +2 per packet), a time field at bytes 6–9 (+4
per packet), and many 24- and 32-bit big-endian values. Every model here,
like CCSDS 124, sees bytes; a value crossing a 256 boundary changes two
bytes. `bench/analysis/fields.py` finds the field layout from history
alone (18 fields of 2–4 bytes, all big-endian) and estimates −2.9% from
coding numeric deltas. (No packet error control field: the last bytes
are constant.)

Measured instead with a reversible transform — every field replaced by its
numeric delta from the previous packet, zigzag-coded so small changes give
small numbers and carries disappear — and the real codecs:

| Input | Fast profile | v2, 2^14 |
|---|---:|---:|
| original packets | 3,845,622 | 3,251,718 |
| field deltas, zigzag | 3,866,563 (+0.5%) | 3,577,483 (+10.0%) |
| field deltas, plain | 4,082,276 (+6.2%) | 3,683,399 (+13.3%) |

Worse: the models already predict each byte from the byte above, and the
delta transform removes the absolute value that the transition model
("which value follows which") uses. Carries are rare enough not to
matter.

## Work per byte, not only bits: coding classes, and instruction counts

Wall-clock speeds on this shared machine vary by ±30% between identical
runs, so speed is also measured as **instructions executed per input byte**
(valgrind/callgrind, x86-64), which does not depend on machine load and is
closer to what matters on simple in-order flight processors (about one
instruction per cycle).

**Coding classes** (`packet_fast::class`, chosen by the ground with
`learn_classes` from the change rate of each column in the history, one
byte per column to uplink like the recipes):

* `STATIC` (changes in < 1% of packets): all static columns share one "any
  changed?" decision per packet and cost nothing else when none changed;
* `ALWAYS` (changes in > 90%): the delta is coded directly, 0 included,
  without a separate decision;
* `NORMAL`: as before.

Venus Express, layout learned on the first 10%, measured on the other 90%
(sizes) and on all packets (instructions in `compress`, priming included):

| Fast profile | Bytes (test 90%) | Instructions / byte |
|---|---:|---:|
| default | 3,463,245 | 181.4 |
| learned recipes | 3,237,111 | 183.6 |
| learned recipes + classes (static < 1%, always > 90%: 39 static, 20 always) | 3,250,871 (+0.4%) | **153.2 (−16.6%)** |
| learned recipes + classes (static < 0.2%, always > 95%: 29 static, 12 always) | **3,234,200 (−0.1%)** | 163.5 (−11.0%) |

**Against CCSDS 124.** The open C implementation compiled from source with
`-O3` (no LTO, so the compressor can be isolated), callgrind restricted to
`ccsds124_compress_packet` on the same 136,080 test packets: **1,288
instructions per byte**, 7–8x more than the fast profile. In wall-clock
time on a desktop core the gap is only ~2x (26 vs ~50 MB/s), because its
word-level bit-vector loops run at a much higher instructions-per-cycle on
an out-of-order x86 than our branchy model code does. On an in-order flight
CPU the instruction count should matter more, but this has not been
measured on one; it is also an open reference implementation, not
necessarily the fastest CCSDS 124 code that flies. One caveat on our side
for a flight port: `encode_freq` divides 64-bit integers, which 32-bit
flight CPUs (LEON3) do in software; a 32-bit range-coder formulation
(`range / total` once per symbol) would avoid it.

Reproduce: `SEDGE_FAST_RECIPES=1 SEDGE_FAST_ONLY=<0|1|2>
SEDGE_FAST_CLASSES=0.01,0.9 valgrind --tool=callgrind
--toggle-collect='*FastPacketSession*::compress'
target/release/examples/packet_fast_bench venus-express.ccsds 90`; for
CCSDS 124, build `bench/c/ccsds124_loss.c` with the library sources and
`--toggle-collect=ccsds124_compress_packet`.

### Measured on RISC-V

RISC-V is the ISA of ESA's next flight processor family (Gaisler NOEL-V,
RV64). Both codecs were cross-compiled for `riscv64gc-unknown-linux-gnu`
(sedge: Rust release build; CCSDS 124: the library sources with
`riscv64-linux-gnu-gcc -O3`), run under `qemu-riscv64`, and every executed
guest instruction counted from QEMU's execution log
(`bench/analysis/qemu_count.awk`; this QEMU build has no plugins, and its
`instret` counter follows the host clock, so it could not be used).
Drivers: `examples/packet_fast_count.rs`, `bench/c/ccsds124_count.c`
(compress only; runs with 0, 500 and 1,000 packets, the difference taken
so that start-up and file reading cancel out). The RISC-V build of sedge
produces exactly the same bytes as on x86 (58,221 bytes for the first
2,000 packets).

| Venus Express, packets 500–1,000 | Instructions | Per input byte |
|---|---:|---:|
| CCSDS 124 (R=0, pt=14, ft=10⁵, rt=10⁶) | 26,541,506 | **590** |
| sedge fast profile (default layout) | 8,759,961 | **195** |

On RISC-V the fast profile executes **3.0x fewer instructions per byte**
than the open CCSDS 124 implementation while producing 27% fewer bytes.
That is much less than the 7–8x counted on x86 (where gcc compiled the
CCSDS 124 bit-vector code into many more instructions): the ratio depends
on the ISA and the compiler, which is why it had to be measured on the
relevant one. Still not measured: cycles on real NOEL-V or LEON hardware
(caches, multiply/divide latency), and the learned-layout variant on
RISC-V. RV64 has hardware 64-bit division, so `encode_freq` is not a
problem there; on 32-bit LEON3 it would be.

### Two speed ideas that did not pay (recorded)

* **Code the change mask as a whole.** A packet's change mask (which
  bytes differ from the previous packet) is rarely repeated (55,449
  distinct masks in 151,199 packets; even a 256-entry cache finds only
  19%), but it differs from the previous mask in only ~6 of 90 positions.
  Coding just those flips as gaps would replace ~90 decisions by ~6
  symbols, but loses the per-column probabilities: 416,178 bytes (gaps in
  a ground-learned column order) or 519,888 (natural order) against
  ~260,000 for the per-column decisions on the test packets, about +5% in
  total. With coding classes, only ~31 columns still pay a decision, so
  the remaining speed-up would be small.
* **Learn in batches.** Counting with one increment and rebuilding a
  coding table normalised to 2^15 every few symbols removes both 64-bit
  divisions and the Fenwick walks from the encoder (the interval is scaled
  by a shift). But rebuilding a 255-symbol table costs about what the tree
  saved: rebuilding every 16 symbols ran no faster than the Fenwick
  version and was +0.27% larger (3,855,796 bytes); every 32 symbols,
  somewhat faster but +0.46%. For 256-symbol alphabets updated at this
  rate, the Fenwick tree is already close to the best.


## 32-bit arithmetic for 32-bit flight CPUs

`Encoder::encode_freq` used two 64-bit divisions per symbol, which a
32-bit flight processor such as LEON3 performs in software. It now uses
the classic range-coder form: one 32-bit division per symbol,
r = (x2 − x1) / total, the symbol taking [x1 + r·cum, x1 + r·(cum + freq)),
leaving the top (x2 − x1) mod total values of the interval unused. Cost on
Venus Express: 3,845,622 → **3,846,435** bytes (+0.02%); with learned
recipes on the held-out 90%, 3,237,111 → 3,237,712. The fast profile's
golden stream changed accordingly. Tables above measured before this
change (frame and packet loss, instruction counts) differ by about 0.02% in
size; the RISC-V instruction count was measured with the 64-bit version.

Re-measured on RISC-V after the change (same method, packets 500–1,000):
8,596,351 instructions, **191 per byte** (was 195), i.e. 3.1x fewer than
CCSDS 124's 590. The RISC-V build again produces the same bytes as x86
(58,229 bytes for the first 2,000 packets).
