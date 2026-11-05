# Packet profile v2: Venus Express

Every number: 151,200 Venus Express packets of 90 bytes (CCSDS 124 test
vectors), coded one by one, every packet decompressed and verified
(`examples/packet_bench.rs`, `SEDGE_PACKET_V2=1` for v2). Speeds on one
desktop core, compress and decompress measured separately. Memory from
`PacketSession::memory_bytes`.

## Final comparison

| Profile | Tables | Memory | Bytes | Compress | Decompress |
|---|---:|---:|---:|---:|---:|
| v1 | 2^12 | 81 KiB | 4,026,696 | 3.6 MB/s | 3.5 MB/s |
| v2 | 2^12 | 372 KiB | 3,350,925 | 7.0 MB/s | 6.0 MB/s |
| v1 | 2^14 | 321 KiB | 3,650,124 | 3.6 MB/s | 3.4 MB/s |
| v2 | 2^14 | 648 KiB | 3,251,718 | 6.8 MB/s | 6.2 MB/s |
| v1 | 2^16 | 1,281 KiB | 3,449,157 | 3.5 MB/s | 3.0 MB/s |
| v2 | 2^16 | 1,752 KiB | 3,127,144 | 6.2 MB/s | 5.4 MB/s |
| v1 | 2^18 | 5,121 KiB | 3,238,198 | 2.9 MB/s | 2.9 MB/s |
| v2 | 2^18 | 6,168 KiB | 2,999,548 | 5.2 MB/s | 4.8 MB/s |

At about equal memory: v2 2^12 (372 KiB) vs v1 2^14 (321 KiB): −8.2%, 1.9x
faster to compress; v2 2^14 vs v1 2^16: −5.7% with half the memory; v2
2^16 vs v1 2^18: −3.4% with a third of the memory. v2 2^18 is −6.3% vs the
full general-purpose model (lean session + record model, ~70 MiB,
3,202,177 bytes). Against the best CCSDS 124 configuration (5,289,939):
−36.7% (2^12) to −43.3% (2^18).

## What was tried, in order (tables 2^14 unless stated)

| Step | Bytes | Kept? |
|---|---:|---|
| v1 | 3,650,124 | baseline |
| + "same as above" decision (contexts: column run length; left changed + column changed last time; bytes changed so far) | 3,480,979 | yes (1.7–1.8x faster) |
| + context: the byte to the right as it was (carry announcement) | 3,480,933 | no (no gain, slower) |
| changed bytes: one mixed model of the zigzag delta (6 contexts) instead of choosing transition/residual per column | 3,618,481 | no |
| changed bytes: one mixed model of the value (6 contexts) | 4,004,201 | no |
| compare the two bit models on 1 packet in 4 / 2 / 8 / 16 / 64 instead of every packet | 3,403,088 / 3,431,711 / 3,390,210 / **3,384,399** / 3,390,028 | 16 |
| + SSE on the transition model (column, bit position) | 3,293,223 | yes |
| SSE context + "prefix so far equals the byte above" (+ that bit of the byte above) | 3,264,084 | yes, smaller variant |
| + SSE on the residual model | 3,239,210 | yes |
| + SSE on the "same" decision | 3,227,444 | yes |
| SSE tables shrunk from ~760 KiB to ~285 KiB (fewer contexts) | 3,251,718 | yes (memory) |

Why comparing the models less often *helped*: in v1 the model not chosen
for a column still ran on every byte to track its cost, and so was also
trained on it; running it on one packet in 16 keeps the choice informed
while its tables learn mostly from the bytes it actually codes.

## Held-out checks

Tuned only on Venus Express. The other CCSDS 124 test inputs (synthetic,
90-byte packets) were not used for tuning:

| Input | Best CCSDS 124 R=0 (sweep) | v1 2^14 | v2 2^14 |
|---|---:|---:|---:|
| housekeeping.bin (10,000 packets) | 133,187 | 20,616 | 17,363 |
| hiro.bin (100) | 367 | 245 | 189 |
| simple.bin (100) | 367 | 245 | 189 |
| edge-cases.bin (500) | 4,267 | 1,078 | 507 |

Learning curve on Venus Express (first N packets, 2^14):

| Packets | v1 | v2 |
|---:|---:|---:|
| 100 | 2,946 | 3,126 |
| 300 | 8,869 | 8,846 |
| 1,000 | 27,254 | 26,024 |
| 3,000 | 79,720 | 74,272 |
| 10,000 | 246,111 | 224,425 |

Limitation: v2 starts slower (more models to learn; priming removes this),
and on the test suite's synthetic stream — four columns of random values
that change in every packet, 1,000 packets — v2 is larger (1,603 vs 1,448
bytes in the golden tests).

## Under packet loss (v2 + erasure code)

`SEDGE_PACKET_V2=1 examples/packet_fec` (tables 2^16, same setup as
`venus_fec.md`):

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

Best against best: 0.1% loss −37.5% vs CCSDS 124 R=1 (v1: −31.7%); 1%
loss −36.2% vs R=2 (v1: −30.5%); 5% loss −29.5% vs R=3 (v1: −23.7%), all
with 100% of the packets recovered.

## v2_lp: numeric prediction (`PacketSession::v2_lp`, opt-in)

The paq8px ablation (`packet_fast.md`) identified numeric prediction as
the main model sedge lacked. `src/packet_lp.rs` adds it to packet profile
v2, integer-only and deterministic. Three pieces:
* **14 predictors per column:** polynomial extrapolations (W, 2W−WW,
  3W−3WW+WWW, …), a fixed-point order-4 OLS on deltas, and 16-bit pair
  predictors. The pair predictors are not in paq8px: they predict one byte
  of a 16-bit field from the other, carry included, in both byte orders.
* **Residual histograms:** 256 bins of (actual − predicted) per predictor,
  selected by the predictor's recent error. P(bit) is computed from the
  counts still compatible with the bits already coded, as in paq8px's
  newer version.
* **Per-column mixer weights.**

v2's own golden stream is unchanged. v2_lp has its own golden stream:
1,500 bytes, 0xb8f7_c747_4286_a508. All results are whole files with
every round trip verified:

| Dataset | v2 | **v2 + LP** | Change |
|---|---:|---:|---:|
| Venus Express, 2^16 | 3,127,144 | **2,986,557** | −4.50% |
| Venus Express, 2^18 | 2,999,548 | **2,874,663** | −4.16% |
| ecg_incart (24 B) | 40,064,022 | 38,295,682 | −4.41% |
| power_uci (18 B) | 6,416,625 | 6,304,260 | −1.75% |
| ais_tracks (34 B) | 12,177,958 | 11,493,156 | −5.62% |
| metropt_codes (26 B) | 5,184,963 | 4,874,806 | −5.98% |

* On Venus Express, v2_lp 2^18 is **45.7% smaller than the best CCSDS 124
  configuration** (5,289,939).
* It closes about 21% of the distance to paq8px (≈2.39 MB), 125 KB of
  607 KB. Column 59's in-file cost goes from 20,652 to 14,357 bytes;
  paq8px alone on that column gets 11,236.
* **Costs:** about 3x slower (Venus: 1.5 MB/s compress, 1.4 MB/s
  decompress, against 5 MB/s) and about 1.2 MB more memory (7.4 MB at
  2^18).

**What did not matter.**
* OLS order (2–8), forgetting rate and ridge all stay within ±0.1%, so
  the 32-tap OLS is not where paq8px's lead comes from.
* SSE on the best predictor, feeding predictor error into the flag, and
  changing histogram ageing all stay under 0.1%.

**Still open.**
* ~~Speed: computing histograms only for the 2–3 best predictors of each
  column.~~ Done, see below.
* Choosing the pair predictors from a known field layout rather than
  trying both byte orders.
* The C port.

## v2_lp with ground-learned predictor subsets (`v2_lp_with_subsets`)

`PacketSession::learn_lp_subsets(history, len, table_bits, k)` picks, per
column, up to `k` of the 14 predictors by greedy forward selection with the
codec itself. It primes on the first half of `history` and measures each
column's ideal cost on the second, held-out half. Each round tries every
predictor in every column at once (14 passes, run in parallel). A column
keeps the predictor that lowers its cost most, and stops when none does.
The k = 2 and k = 3 subsets are prefixes of the k = 4 ones.
`PacketSession::v2_lp_with_subsets(len, table_bits, &subsets)` then
computes histograms, mixer inputs, error tracking and OLS updates only
for the chosen predictors. A column with none skips the LP state update
entirely. This is its own stream, pinned at 1,713 bytes,
0x1ecf_e8ef_f2a7_a617.

Setup: subsets learned on the first 10% of the packets, then every packet
compressed from a fresh session, every round trip verified
(`examples/lp_subset_bench.rs`). "Kept" is the share of v2_lp's gain over
v2 that remains. Bytes are on the whole file; the held-out last 90% gives
the same percentages within ±2 points.

| Dataset | v2 | v2_lp | k = 2 | k = 3 | **k = 4** | learn |
|---|---:|---:|---:|---:|---:|---:|
| Venus 2^16 | 3,127,144 | 2,986,557 | 3,019,072 (77%) | 3,002,062 (89%) | **2,996,042 (93%)** | 28 s |
| Venus 2^18 | 2,999,548 | 2,874,663 | 2,897,365 (82%) | 2,882,590 (94%) | **2,879,055 (96%)** | 42 s |
| ecg_incart | 40,064,022 | 38,295,682 | 38,965,057 (62%) | 38,668,952 (79%) | **38,503,765 (88%)** | 288 s |
| power_uci | 6,416,625 | 6,304,260 | 6,325,855 (81%) | 6,312,943 (92%) | **6,305,579 (99%)** | 37 s |
| ais_tracks | 12,177,958 | 11,493,156 | 11,787,489 (57%) | 11,710,967 (68%) | **11,542,542 (93%)** | 97 s |
| metropt_codes | 5,184,963 | 4,874,806 | 5,038,308 (47%) | 4,981,325 (66%) | **4,935,014 (81%)** | 26 s |

**Speed.** Callgrind instructions on 15,000 Venus packets (2^18, compress
plus decompress): v2 3.38 G, v2_lp 12.27 G, k = 2 6.51 G, k = 3 6.90 G,
k = 4 7.17 G. Compression speed in MB/s; the machine is shared, so take
these within ±15%:

| Dataset | v2 | v2_lp | k = 2 | k = 3 | k = 4 |
|---|---:|---:|---:|---:|---:|
| Venus 2^18 | 4.3 | 1.5 | 2.6 | 2.6 | 2.5 |
| ecg_incart | 5.9 | 1.1 | 2.2 | 2.1 | 1.9 |
| power_uci | 8.0 | 2.5 | 4.9 | 4.8 | 4.5 |
| ais_tracks | 12.7 | 4.2 | 7.4 | 5.6 | 5.5 |
| metropt_codes | 10.2 | 2.4 | 4.7 | 4.3 | 4.1 |

**Memory** is unchanged (the histogram pool stays 2^11 × 512 B): 7.4 MB at
2^18, 2.6–2.7 MB at 2^16. `pool=10` saves 512 KiB at about +0.1%.

**v2_lp itself is 11% fewer instructions, with the same bytes** (the
golden streams of v2 and v2_lp are unchanged, and the whole-file sizes
above match the earlier table exactly):
* Each bit's residual window is a half of the previous bit's, so one
  prefix-sum lookup per predictor and bit replaces three.
* Per-predictor state is packed into one array, without bounds checks.
* The bit loop is specialised on the number of mixer inputs.
* `ratio` skips the normalising shift, which is always 0 below 2^13
  counts.
* `Io::bit` is inlined again.

What remains costs per bit whatever the predictors: two mixers, three
squashes, and the APM. That is why k = 0 (the LP mixers with no predictor)
is already 1.3x v2's instructions, and also 1% smaller than v2.

**What did not help:** dropping `mix2` in subset mode (+0.3%, about 6% of
the gain); a 0.2–1% minimum gain per added predictor (slightly larger,
barely faster); 16-bit hints for the weight update (no change).

