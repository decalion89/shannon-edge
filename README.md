# shannon-edge

**Technical report:** [`docs/TECHNICAL_REPORT.md`](docs/TECHNICAL_REPORT.md) — all results, methods, negative results, limitations and how to reproduce each figure.

**Lossless compression by prediction — pushing toward the Shannon limit.**

`sedge` is a context-mixing compressor written in Rust with zero dependencies.
It does not look for repeated strings the way gzip, zstd or xz do. Instead,
before every single bit it **predicts** what comes next, using a set of models
blended by small online neural networks, and an arithmetic coder stores only
the *surprise*. Better prediction means fewer bits, all the way down to the
entropy of the data.

> **Mission:** compression as smart as AI and as fast as zstd.
> v0.1 delivers the "smart" half. Speed is the next frontier — see the
> [roadmap](ROADMAP.md).

## At a glance

One codec, built on one principle: **predict well, send only the
surprise**. That surprise is also an anomaly score. Every number below is
verified bit for bit, or scored with the benchmark owner's own code. The
limits are linked next to the claims.

| What | Result | Details |
|---|---|---|
| Spacecraft packets vs the CCSDS 124 standard (Venus Express, lossless) | **27–46% smaller**: the fast profile, ~1.9x faster, up to v2 with numeric prediction (`v2_lp`) | `bench/results/packet_fast.md`, `bench/results/packet_v2.md` |
| Same, error-bounded (≤ 1 σ of sensor noise), rare values exact | **61% smaller than CCSDS 124**; keeping rare values exact costs 0.1% | `bench/results/near_lossless.md` |
| Rare-exact rule on ESA-labelled events | 90% of events contain exact values; 0.1% of all values are exact | `bench/results/near_lossless.md` |
| Anomaly detection on ESA-ADB, **no training**, false alarms bounded by a theorem | Mission 1 full: **0.576 vs best published 0.061**; Mission 2 full: **0.249 vs 0.079** | `docs/KRAFT_DETECTION.md`, `bench/results/esa_adb.md` |
| Same detector, thresholds trained on nominal data | first on both full sets under ESA-ADB's own metric code (0.284, 0.798) | `bench/results/esa_adb.md` |
| Field laws learned on the ground (12-lead ECG) | the derived leads found with no ECG knowledge: **2.77x → 3.82x** | `bench/results/general_data.md` |
| On board without Rust | C99 libraries for the fast and flight profiles, bit-exact with Rust on 157 M samples, no malloc or float, ASan/UBSan clean | `c/README.md` |
| Robustness | every decoder fuzzed; the one bug found (a lying header) is fixed | `fuzz/README.md` |

**Where it does not win** (measured, documented):
* single-signal shape anomalies: UCR archive 0.27–0.35 vs matrix profile
  0.54 (`bench/results/ucr_anomaly.md`);
* frequent clinical abnormalities: the rarity limit
  (`bench/results/ecg_kraft.md`);
* naming every affected channel;
* whole-file archiving against xz plus field transforms;
* about 19% of headroom remains against paq8px, at 1,000x the work.

## Results

Every `sedge` number below was decompressed and verified bit-for-bit.
Competitors run at their strongest standard settings. Smaller is better;
the best result in each row is in bold.

### Canterbury corpus (the classic benchmark)

| File | Original | gzip -9 | bzip2 -9 | xz -9e | zstd -19 | brotli -11 | **sedge** |
|---|---:|---:|---:|---:|---:|---:|---:|
| alice29.txt | 152,089 | 54,170 | 43,202 | 48,528 | 49,211 | 46,487 | **37,704** |
| asyoulik.txt | 125,179 | 48,778 | 39,569 | 44,592 | 45,137 | 42,712 | **35,111** |
| cp.html | 24,603 | 7,940 | 7,624 | 7,652 | 7,713 | 6,894 | **6,485** |
| fields.c | 11,150 | 3,115 | 3,039 | 3,032 | 3,015 | 2,717 | **2,461** |
| grammar.lsp | 3,721 | 1,222 | 1,283 | 1,292 | 1,211 | 1,124 | **1,019** |
| kennedy.xls | 1,029,744 | 207,029 | 130,280 | 51,868 | 64,825 | 61,498 | **22,050** |
| lcet10.txt | 426,754 | 144,439 | 107,706 | 119,488 | 121,336 | 113,416 | **91,658** |
| plrabn12.txt | 481,861 | 194,332 | 145,577 | 165,456 | 167,438 | 163,267 | **129,350** |
| ptt5 | 513,216 | 52,221 | 49,759 | 39,860 | 43,640 | 40,939 | **31,866** |
| sum | 38,240 | 12,838 | 12,909 | **9,500** | 11,107 | 10,144 | 10,147 |
| xargs.1 | 4,227 | 1,736 | 1,762 | 1,812 | 1,724 | **1,464** | 1,483 |
| **Total** | 2,810,784 | 727,820 (25.9%) | 542,710 (19.3%) | 493,080 (17.5%) | 516,357 (18.4%) | 490,662 (17.5%) | **369,334 (13.1%)** |

`sedge` wins 9 of 11 files and the total: its output is **25% smaller than
the best competitor** (brotli -11). On `kennedy.xls` (a spreadsheet) and
`ptt5` (a fax image) the **record model** switches on by itself: it detects
fixed-length records (13-byte spreadsheet records, 216-byte scanlines) and
predicts each byte from the same column of the previous record — 57% below
xz on `kennedy.xls`. It still loses on a SPARC executable (`sum`) and on
`xargs.1`, where brotli's built-in English dictionary pays off.

### enwik8 (first 100 MB of English Wikipedia, the Hutter Prize data)

| Compressor | Size (bytes) | Ratio | Bits per byte |
|---|---:|---:|---:|
| gzip -9 | 36,475,792 | 36.48% | 2.918 |
| bzip2 -9 | 29,008,758 | 29.01% | 2.321 |
| zstd -19 | 26,936,936 | 26.94% | 2.155 |
| brotli -11 | 25,742,001 | 25.74% | 2.059 |
| xz -9e | 24,831,648 | 24.83% | 1.987 |
| **sedge** `-b 0` (one block) | **21,793,239** | **21.79%** | **1.743** |
| **sedge** (default: 8 MiB blocks, parallel) | 22,691,880 | 22.69% | 1.815 |

In single-block mode, 12% smaller than xz -9e and 15% smaller than brotli -11. For perspective, the
best research compressors (cmix, nncp) reach ~15 MB on enwik8 at hundreds of times less
speed: there is still a lot of edge left to take.

### Speed — the honest part

A context-mixing model is expensive: one core runs at **~0.5 MiB/s**. So
`sedge` splits large inputs into independent 8 MiB blocks and compresses and
decompresses them on all cores. The output depends only on the block size,
never on the number of cores, so the same file gives the same bytes on any
machine. enwik8 on 4 cores of a 2.1 GHz Xeon:

| Mode | Size (bytes) | Compress | Decompress | vs. single block |
|---|---:|---:|---:|---:|
| `-b 0` (one block, max ratio) | 21,793,239 | 0.48 MiB/s | 0.48 MiB/s | — |
| `-b 32` | 22,097,516 | 1.39 MiB/s | 1.47 MiB/s | +1.4% |
| `-b 16` | 22,354,674 | 1.53 MiB/s | 1.50 MiB/s | +2.6% |
| **`-b 8` (default)** | **22,691,880** | **2.01 MiB/s** | **2.02 MiB/s** | +4.1% |

With the default, `sedge` is faster than single-threaded `xz -9e` (~1.9 MiB/s on the same
machine) and still 8.6% smaller. zstd remains in another league for speed
(hundreds of MiB/s). Each worker holds its own model (~140 MiB), so memory
grows with the thread count; `-t` limits threads. Closing the rest of the gap
is [Phase 1](ROADMAP.md#phase-1--speed-the-main-frontier).

### Shared knowledge: dictionaries (`-D`)

If sender and receiver already share some data `K`, the true cost of a new
file `X` is the conditional information `H(X | K)`, which can be far below
`H(X)`. With `-D K`, the model reads `K` before coding (`K` is never stored;
the stream records only its CRC and length, and decoding requires the same
file).

**Small messages.** Dictionary = two English books from the Canterbury corpus
(908,615 bytes). Real `.sedge` sizes, all verified:

| File | Original | brotli -11 | sedge | **sedge -D** |
|---|---:|---:|---:|---:|
| xargs.1 | 4,227 | 1,464 | 1,483 | **1,322** |
| grammar.lsp | 3,721 | 1,124 | 1,019 | **965** |
| cp.html | 24,603 | 6,894 | 6,485 | **6,152** |
| fields.c | 11,150 | 2,717 | 2,461 | **2,442** |
| 3 KB of *Alice in Wonderland* (bytes 1,000–4,000 of `alice29.txt`) | 3,000 | 1,217 | 1,278 | **962** |

**Block mode.** Every block is primed with the same dictionary, so blocks stay
independent (parallel) yet none starts from zero. enwik8 minus its first
4 MiB (95.8 MB), with dictionaries cut from that first 4 MiB (no overlap with
the data), 4 cores:

| Mode | Size (bytes) | Speed | Block-mode loss recovered |
|---|---:|---:|---:|
| one block (`-b 0`) | 20,896,796 | 0.53 MiB/s | — |
| 8 MiB blocks | 21,758,838 | 2.06 MiB/s | 0% |
| 8 MiB blocks + 1 MiB dictionary | 21,502,540 | 1.87 MiB/s | 30% |
| 8 MiB blocks + 4 MiB dictionary | 21,261,762 | 1.28 MiB/s | 58% |

**Primed models: pay for the dictionary once.** Reading a dictionary runs at
model speed, so `sedge prime` does it once and saves the primed model;
`-M` then loads it instead of re-reading. It is only a cache: streams made
with `-M` decode with `-D` and vice versa, byte-identical when the memory
level matches. Total command time for one 3 KB message, all verified:

| Message | Dictionary | `-D` (re-read) | `-M` (load) | Size with knowledge | Size without |
|---|---|---:|---:|---:|---:|
| *Alice* excerpt | 2 books, 908 KB | 1,664 ms | **427 ms** | 962 | 1,278 |
| last 3 KB of enwik8 | 4 MiB of enwik8 | 7,623 ms | **446 ms** | 764 | 1,211 |

The bigger the knowledge, the bigger the win: loading costs roughly the
same, re-reading grows with the dictionary. Model files are large (≈ the
model's memory, ~144 MB at the default level; `-m 20` gives ~43 MB and
986 bytes instead of 962 for the *Alice* excerpt). In a
long-running process, keep a `PrimedModel` in memory and skip the load too.

```sh
sedge prime samples.json                       # -> samples.json.sedgem
sedge compress msg.json -M samples.json.sedgem
sedge decompress msg.json.sedge -D samples.json   # either works
```

Reproduce the first table with `bench/shared_knowledge.py`.

### Small messages vs. the industry standard (zstd + trained dictionary)

For small records (API payloads, events, logs) the standard answer is zstd
with a dictionary trained on samples. Test: 1,000 real GitHub events from
GH Archive (2024-01-15, 16:00 UTC), each compressed **separately**. All
knowledge comes from 5,000 events of the previous hour (15:00 UTC); no test
record was ever seen. All sedge results verified bit-for-bit.

| Compressor (1,000 records, one by one) | Knowledge the receiver holds | Total bytes | vs zstd + dict |
|---|---|---:|---:|
| zstd -19 | none | 833,210 | +106.1% |
| brotli -11 | built-in | 727,176 | +79.9% |
| sedge | none | 726,386 | +79.7% |
| zstd -19 + its trained dictionary | 110 KiB | 404,285 | — |
| sedge -M, zstd's trained dictionary | 110 KiB | 334,447 | −17.3% |
| **sedge -M, sedge's own trained dictionary** | **110 KiB** | **327,667** | **−19.0%** |
| zstd -19, all 5,000 samples as raw dictionary | 18 MB | 376,960 | −6.8% |
| **sedge -M, primed on all 5,000 samples** | **18 MB** | **290,450** | **−28.2%** |

At **equal knowledge**, sedge wins at both budgets: −19% with 110 KiB
(and `sedge train` builds its dictionary in 2 s where zstd's trainer takes
113 s), −23% against zstd with the same 18 MB. The difference grows with
knowledge because a predictive model turns every sample into statistics,
while a copy-based dictionary can only reuse literal strings.

The price is speed. `PrimedModel::compress_message` (used by `sedge -M`)
works on the primed model in place and undoes its changes from a journal,
so a record costs time proportional to the record, not to the model, and
each slot is journaled at most once per record: ~8 ms per record per
direction. 1,000 records compress + decompress + verify in 16 s, whether
the model was primed on 110 KiB or on 18 MB — barely more than the 13.8 s
without any knowledge (before the journal: 63 s and 130 s). zstd takes microseconds. `.sedgem` model
files are large (here 162 MB). Reproduce with
`bench/small_messages.py`.

### Streams: sessions that keep learning

A device talking to a server, a webhook feed, telemetry: records arrive one
after another over one connection. A `Session` codes record *n* with
everything learned from records *0..n-1*; sender and receiver make the same
updates, so the model is never sent. Each record is a compact frame
(≈8 bytes: kind, length, 16-bit sequence number, CRC-32), lost or reordered
records are detected, and a corrupt record leaves the receiver unchanged.
`Session::lean()` drops the sequence number and CRC (2–3 bytes per frame)
for links that already guarantee integrity and order.

1,000 consecutive GitHub events (GH Archive, 2024-01-15 16:00 UTC), every
record verified for every method:

| Method (records sent one by one, in order) | Total bytes | % of original | vs best zstd |
|---|---:|---:|---:|
| zstd -19, each record alone | 827,032 | 24.26% | +152.0% |
| zstd -19, each record alone + trained dictionary (110 KiB) | 398,229 | 11.68% | +21.4% |
| zstd -19, streaming with context kept across records | 328,162 | 9.63% | — |
| zstd -19, streaming with context + trained dictionary | 329,931 | 9.68% | +0.5% |
| **sedge `Session`** | **240,606** | **7.06%** | **−26.7%** |
| **sedge `Session` from a sedge-trained dictionary (110 KiB)** | **232,946** | **6.83%** | **−29.0%** |

zstd's streaming mode with context takeover (as in WebSocket compression) is
the standard answer for streams; a learning session beats it by 27%, even
though every sedge frame carries a CRC-32 and the zstd frames carry none.
Cost: ~15 ms per record for both directions together (zstd: microseconds).

Sessions can run forever: the history the model copies from is a sliding
window (default 32 MiB, `Session::with_history_limit`; both sides must use
the same). Forgetting old text costs little, because the model keeps what
it learned as statistics. Same 1,000 events:

| History window | 32 MiB (default) | 1 MiB | 256 KiB | 64 KiB | zstd streaming (8 MiB window) |
|---|---:|---:|---:|---:|---:|
| Total bytes | 240,606 | 243,394 | 254,691 | 263,686 | 328,162 |

Reproduce with `bench/streams.py` and
`examples/session_bench.rs RECORDS N - HISTORY_KIB`.

```rust
let mut tx = shannon_edge::Session::new(&opts);   // or Session::from_model(primed)
let mut rx = shannon_edge::Session::new(&opts);
for record in records {
    let frame = tx.compress(record);
    assert_eq!(rx.decompress(&frame)?, record);
}
```

### Spacecraft telemetry vs. CCSDS 121, the space standard

Real telemetry from an ESA mission ([ESA Anomaly Dataset](https://doi.org/10.5281/zenodo.12528696),
Mission 1, CC BY 3.0 IGO; Kotowski et al., arXiv:2406.17826): six channels,
the first 1,000,000 samples of each, sent as packets of 256 consecutive
samples. CCSDS 121.0-B (libaec, unit-delay preprocessor, each packet
independent, as flown) against zstd and a sedge session per channel. Lean
session frames carry no CRC/sequence number, like CCSDS 121 packets, whose
integrity comes from the link layer. Each method's best representation
(published float32 values, or 16-bit codes + codebook) per channel; every
packet verified:

| Channel | CCSDS 121 | zstd -19 streaming | **sedge session (lean)** | vs CCSDS 121 |
|---|---:|---:|---:|---:|
| channel_1 | 30,036 | 48,828 | **23,264** | −23% |
| channel_4 | **17,037** | 40,076 | 16,737 | −2% |
| channel_10 | **16,338** | 39,392 | 16,230 | −1% |
| channel_12 | 277,906 | 285,261 | **157,384** | −43% |
| channel_14 | 298,025 | 281,299 | **149,156** | −50% |
| channel_25 | 306,424 | 328,917 | **179,964** | −41% |
| **Total** | **945,766** | 1,023,773 | **542,735** | **−43%** |

On smooth channels CCSDS 121 is already near-optimal and sedge only ties;
on noisy channels, where the downlink budget actually goes, a learning
model cuts the data almost in half. The catch is computation: CCSDS 121
coded each million samples in ~0.1 s, sedge took ~5–10 s (both directions)
— fine on the ground, but onboard use needs a much cheaper model.
Reproduce with `bench/telemetry.py` (full per-representation table there).

**Flight profile: the same idea, sized for a spacecraft.** Where does the
gain come from? Not from the text-oriented parts of the model: a tiny
numeric model keeps almost all of it. `shannon_edge::flight::FlightSession`
(also in C as `sedge_flight_*` and Python as `FlightSession`) combines

* a residual model (difference from the previous sample, coded with
  adaptive contexts where CCSDS 121 uses fixed Rice codes), and
* a transition model (orders 0–2 over sample values, i.e. "which value
  tends to follow which"), mixed by a small integer mixer,

and codes each sample with whichever was cheaper on the recent samples —
both ends know those, so the choice costs nothing to transmit. Integer
arithmetic only (a fixed-point log2 table for costs), bounded memory, a
golden test pinning the format. Same ESA channels and packets, every packet
verified:

| Codec | Model memory | Total, 6 channels | vs CCSDS 121 | Speed (encode + decode) |
|---|---:|---:|---:|---:|
| CCSDS 121 (libaec) | — | 945,766 | — | far faster (optimised C) |
| **flight profile, tables 2^18** | ~3 MiB | **566,196** | **−40.1%** | 2–4 M samples/s |
| **flight profile, tables 2^14** | **~0.2 MiB** | **577,403** | **−38.9%** | 2–4 M samples/s |
| full sedge session | ~70 MiB | 542,735 | −43% | 0.1–0.2 M samples/s |

Housekeeping telemetry runs at thousands of samples per second, so a model
doing millions per second on a desktop core, in 0.2 MiB, plausibly fits a
flight CPU with room to spare — still an estimate until it is timed on
flight-class hardware. `examples/telemetry_lite.rs` keeps the floating-point
research prototype and `examples/flight_bench.rs` reproduces the table.

### vs CCSDS 124 (POCKET+), the housekeeping-telemetry standard

CCSDS 124.0-B-1, based on ESA's POCKET+, is the CCSDS standard for
fixed-length housekeeping packets (adopted 2023; flown on OPS-SAT). Its
public test vectors include **real Venus Express housekeeping telemetry**
(151,200 packets of 90 bytes). For CCSDS 124 we use the open, MIT-licensed
implementation [tanagraspace/ccsds124](https://github.com/tanagraspace/ccsds124),
whose output we checked to be byte-identical (size and MD5) to the ESA
reference output, and we **swept its parameters** (robustness R=0..2,
mask/full/reset periods) to give it its best configuration. Every method
codes the packets **one by one, as they arrive**; every packet verified:

| Venus Express, packet by packet | Model memory | Bytes | Ratio | vs best CCSDS 124 |
|---|---:|---:|---:|---:|
| CCSDS 124, test-vector settings (R=2, pt=20, ft=50, rt=100) | tiny | 5,891,500 | 2.31× | +11.4% |
| **CCSDS 124, best of the sweep** (R=0, pt=14, ft=10⁵, rt=10⁶) | tiny | **5,289,939** | 2.57× | — |
| zstd -19, streaming, flushed per packet | ~8 MiB | 8,236,002 | 1.65× | +55.7% |
| sedge packet profile v1, tables 2^14 | 321 KiB | 3,650,124 | 3.73× | −31.0% |
| sedge packet profile v1, tables 2^18 | 5.0 MiB | 3,238,198 | 4.20× | −38.8% |
| sedge lean session + record model (full model) | ~70 MiB | 3,202,177 | 4.25× | −39.5% |
| **sedge packet profile v2, tables 2^12** | **372 KiB** | **3,350,925** | 4.06× | **−36.7%** |
| sedge packet profile v2, tables 2^14 | 648 KiB | 3,251,718 | 4.18× | −38.5% |
| **sedge packet profile v2, tables 2^18** | 6.0 MiB | **2,999,548** | **4.54×** | **−43.3%** |
| **sedge fast packet profile** (~50 MB/s, ~1.9x CCSDS 124's speed) | 193 KiB | **3,846,435** | 3.54× | **−27.3%** |

**The packet profile** (`shannon_edge::packet::PacketSession`) is the
flight-class answer: integer-only, golden-pinned, one coder per packet, no
framing (fixed packet length, like CCSDS 124 output). Each byte position is
a column predicted from the byte above (previous packet), two packets back
and its left neighbour, by a transition model and a residual model chosen
per column by recent cost.

**Version 2** (`PacketSession::v2`, a separate, golden-pinned stream) adds
a byte-level decision before the bit models — "is this byte the same as
in the previous packet?" — in contexts the bit models do not see (did the
left neighbour just change, how long the column has been constant, how many
bytes of this packet changed). 64% of Venus Express bytes repeat, so only a
third of the bytes reach the bit models. It also compares the two bit
models on one packet in 16 instead of running both on every byte (which,
it turned out, also stopped the inactive model from being trained on bytes
it does not code, and *improved* compression), and adds SSE stages. At
equal memory it is smaller and about twice as fast as v1; it is slightly
worse during the first ~100 packets and on streams where many columns
change at random in every packet. Details and the variants that failed:
[`packet_v2.md`](bench/results/packet_v2.md).

**The fast profile** (`packet_fast::FastPacketSession`) trades some
compression for speed: one cheap "same?" decision per byte and a single
adaptive symbol (the delta) per changed byte. Measured in-process on the
same core, it compresses at ~50 MB/s against ~26 MB/s for the open
CCSDS 124 implementation, while being 27% smaller — the first sedge codec
that beats CCSDS 124 on both size and speed (with 193 KiB of memory
instead of a few hundred bytes; [`packet_fast.md`](bench/results/packet_fast.md)).
*The ground thinks, the spacecraft executes:* the ground can choose a
context recipe per column from the history (`learn_recipes`, one byte per
column to uplink), which cut another 6.5% on the 90% of Venus Express not
used to learn them (−32.2% vs CCSDS 124 there) at the same speed. Ground-chosen
*coding classes* (static columns share one decision per packet; columns
that always change skip theirs) cut the work per byte by 11–17%. Counted in
instructions, the fast profile executes **3.0x fewer instructions per byte
than the open CCSDS 124 implementation on RISC-V** (191 vs 590, both
cross-compiled and counted exactly under QEMU; RISC-V is the ISA of ESA's
next flight processors) and 7–8x fewer on x86; ~2x in wall-clock time on a
desktop core. Not yet timed on real flight hardware.

The idea came from a clue in the data: on the whole file, xz (4.0 MB) beat
sedge (4.3 MB), so sedge was ignoring structure — the column, which POCKET+
also exploits with bit masks. Column contexts brought the whole file to
2.87 MB and the packet-by-packet results above.

Costs, stated plainly: CCSDS 124 compresses this file at ~15 MB/s with a
few hundred bytes of state, built for very weak flight CPUs; on one desktop
core the packet profile compresses at 2.9–3.6 MB/s (v1) and 5.2–7.0 MB/s
(v2), and needs 0.3–6 MiB. Its best CCSDS 124 configuration has no robustness (R=0), like
lean sedge: a lost packet desynchronises both. Reproduce with
`bench/ccsds124.py ccsds124/test-vectors --cli <ccsds124 CLI>`.

**Under packet loss: separate compression from protection.** Building loss
tolerance into the compressor (epochs, key packets) cost most of the
advantage ([`venus_robustness.md`](bench/results/venus_robustness.md)).
Following Shannon's separation principle instead — full-strength packet
profile, plus a packet-level Reed–Solomon erasure code over the compressed
payloads (`shannon_edge::fec`) — keeps it
([`venus_fec.md`](bench/results/venus_fec.md)). Against CCSDS 124 measured
under the same simulated i.i.d. loss (its decoder told about every gap,
`bench/c/ccsds124_loss.c`):

| Loss | Best CCSDS 124 | sedge + erasure code | Difference |
|---:|---|---|---:|
| 0.1% | R=1: 4,976,442 bytes, 99.89% of packets correct | v2, G=250, m=2: 2,886,474 bytes, **100%** | **−42.0%** |
| 1% | R=2: 5,123,900 bytes, 99.02% | v2, G=240, m=8: 3,022,098 bytes, **100%** | **−41.0%** |
| 5% | R=3: 5,241,460 bytes, 95.04% | v2, G=226, m=30: 3,547,406 bytes, **100%** | **−32.3%** |

(Packet profile v2, tables 2^16. The protection overhead — 1.5%, 6.3% and
24.8% — was decomposed into the finite-block margin and the padding of
Reed–Solomon parity to the longest payload; larger groups cut it, at the
price of waiting up to G + m packets after a loss:
[`robustness_cost.md`](bench/results/robustness_cost.md). With groups of
64 the differences were −37.5%, −36.2% and −29.5%; with v1, −31.7%,
−30.5% and −23.7%.)

The receiver also gets back the lost packets themselves. The price: after
a loss it waits up to G + m packets for the parity (CCSDS 124 does not
wait), and bursts longer than m need interleaving (not evaluated).

**Losing frames, as real links do.** Space links lose whole fixed-length
transfer frames, each carrying several packets. With payloads packed into
223-byte frames and Reed–Solomon parity over frames (no padding, since
frames all have the same length), sedge v2 recovers 100% of the packets at
0.1%, 1% and 5% frame loss with 3,037,086 / 3,109,086 / 3,343,086 bytes.
CCSDS 124 under the same frame loss only works at its maximum robustness
R=7 (5,673,343 bytes, 98.75% correct at 1%) and recovers 51.9% at 5%:
**−45.2% and −42.4%, with every packet recovered**. Given the same
frame-level protection, CCSDS 124 is 39.3% larger at every loss rate
([`frame_loss.md`](bench/results/frame_loss.md)).

**Optional: error-bounded mode.** Lossless coding must reproduce sensor
noise bit for bit. Bounding the error of each numeric field by a fraction
of its own noise (header and time exact; closed-loop quantiser as in
JPEG-LS / CCSDS 123 near-lossless; bound verified for every value) gives,
on Venus Express with v2: −53.3% vs CCSDS 124 at ≤ ¼ σ, −57.0% at ≤ ½ σ,
−61.0% at ≤ 1 σ, keeping three doubtful fields exact. Acceptable error is
the mission's call; see [`near_lossless.md`](bench/results/near_lossless.md).

**The compressor is also an anomaly detector.** The flight profile's
per-sample surprise, computed identically on both ends, scored on ESA's
anomaly-detection benchmark (ESA-ADB, Mission 1, its protocol and main
metric, test sets matching the paper's event counts): on the full channel
sets it beats every published algorithm — **0.279 vs 0.061 (Mission 1)
and 0.798 vs 0.079 (Mission 2)** — with no neural network; on the small
lightweight subsets it ranks 2nd (0.690 vs 0.786) and 3rd (0.725 vs 0.949).
With ESA-ADB's exact 30-s preprocessing the full-set results hold (0.292
and 0.815), while the Mission 1 lightweight subset collapses (0.103) because
the grid drops samples irregularly there
([`esa_adb.md`](bench/results/esa_adb.md)).

### A whole mission: 14 years of a satellite's life

`bench/mission.py` runs **every channel** of ESA-AD Mission 1 — 75 channels
(one skipped: more than 65,536 distinct values), 734 million samples from
2000 to 2013 — through CCSDS 121 and the flight profile (tables 2^14,
~0.2 MiB), every packet verified. Full per-channel table:
[`bench/results/esa_mission1.md`](bench/results/esa_mission1.md).

| | Bytes | % of float32 values |
|---|---:|---:|
| Telemetry values as published (float32) | 2,937,374,236 | 100% |
| CCSDS 121 | 275,956,412 | 9.4% |
| **flight profile** | **171,123,388** | **5.8%** |

* The flight profile beats CCSDS 121 on **75 of 75 channels** (from −0.6%
  to −52%), −38% in total.
* **16 channels end below 1%** of their float32 size (CCSDS 121: 13), the
  lowest at 0.43%; median 3.9%.
* As a lossless code, 171 MB is a verifiable upper bound on the new
  information in 14 years of these telemetry values.

The float32 baseline is the dataset's published representation; the raw
onboard samples were likely narrower, so the comparison that matters is
against CCSDS 121, not the percentages.

### The compressor is also an anomaly detector — for free

To compress, the flight profile already computes how surprising every
sample is (its cost in bits, given everything learned so far). The receiver
gets the very same number while decompressing, with nothing extra sent
(`compress_scored` / `decompress_scored`). The ESA dataset is an anomaly
benchmark, so we measured how well that surprise finds the anomalies ESA
engineers labelled, against two classical detectors on the same samples.
Mission 1, **all 58 target channels**, full history, 3,520 labelled
(anomaly, channel) events; thresholds set so each detector fires on the
same small fraction of nominal samples (full table:
[`bench/results/esa_mission1_anomaly.md`](bench/results/esa_mission1_anomaly.md)):

| Detector | Events found at 0.1% false alarms | at 0.01% false alarms | Best on channels |
|---|---:|---:|---:|
| **compressor surprise** | **2,173/3,520 (62%)** | **1,527/3,520 (43%)** | **54/58** |
| z-score (rolling mean/std, 256 samples) | 1,696/3,520 (48%) | 903/3,520 (26%) | 8/58 |
| jump \|x(t) − x(t−1)\| | 1,322/3,520 (38%) | 785/3,520 (22%) | 5/58 |

Caveats: thresholds
are calibrated with the labels (to compare detectors at equal false-alarm
rates; a deployed threshold must be set without them); the controls are
simple, and ESA's benchmark (ESA-ADB) has much stronger learned detectors — e.g.
Telemanom-ESA-Pruned reaches a corrected event-wise F0.5 of 0.968 on a
Mission 1 subset — and its own metrics, which we have not run; the model adapts within a few samples, so
it flags the onset and end of an anomaly rather than its whole duration.
The idea of detecting anomalies through compression is not new (Keogh et
al., 2004); what is shown here is that it comes free from a flight
compressor already running onboard. Reproduce with `bench/anomaly.py`.

### What it cannot do (and nothing can)

Random, encrypted or already-compressed data (JPEG, H.265 video, ZIP) does
not compress — by `sedge` or by anything else. Compressing *every* file to 1%
is not hard; it is **mathematically excluded** by a one-line counting
argument. [`docs/THEORY.md`](docs/THEORY.md) has the proof, plus the one lever
that genuinely moves the limit (shared knowledge). What `sedge` guarantees
instead: incompressible input grows by at most 20 bytes.

## Quick start

```sh
cargo build --release

./target/release/sedge compress   big.log            # -> big.log.sedge
./target/release/sedge decompress big.log.sedge      # -> big.log
./target/release/sedge bench      file1 file2 ...    # ratio + speed, verified
./target/release/sedge compress   big.log -b 0 -m 24 # max ratio: one block, more memory
./target/release/sedge compress   big.log -t 2       # limit to 2 threads
./target/release/sedge compress   packets.bin -r 90  # force 90-byte records (auto by default)
./target/release/sedge train samples/*.json -o samples.dict    # distil samples into a dictionary
./target/release/sedge compress   msg.json -D samples.dict   # shared-knowledge dictionary
./target/release/sedge decompress msg.json.sedge -D samples.dict
```

As a library:

```rust
let opts = shannon_edge::Options::default();
let packed = shannon_edge::compress(&data, &opts);
let back = shannon_edge::decompress(&packed)?; // CRC-32 verified
assert_eq!(back, data);

// With shared knowledge both sides hold:
let packed = shannon_edge::compress_with_dictionary(&data, &dict, &opts);
let back = shannon_edge::decompress_with_dictionary(&packed, &dict, 0)?;

// Prime once, then compress many messages from the primed state
// (in place, journaled: cost proportional to the message):
let mut model = shannon_edge::PrimedModel::new(&dict, &opts);
let packed = model.compress_message(&msg, &opts);
let back = model.decompress_message(&packed)?;
std::fs::write("dict.sedgem", model.to_bytes())?; // PrimedModel::from_bytes to load
```

Reproduce the benchmark tables:

```sh
pip install zstandard brotli   # optional competitors
python3 bench/compare.py path/to/canterbury/*
```

## Use it from Python, C or any language

The library exports a C ABI (`include/shannon_edge.h`), so anything with a C
FFI can use it. A dependency-free Python binding ships in `python/`:

```python
import shannon_edge as se          # after `cargo build --release`

packed = se.compress(data)
assert se.decompress(packed) == data

model = se.PrimedModel(samples)    # shared knowledge, read once
frame = model.compress(msg)
assert model.decompress(frame) == msg

tx, rx = se.Session(), se.Session()  # a learning stream, one per side
for record in records:
    assert rx.decompress(tx.compress(record)) == record
```

C: see `examples/c/demo.c`
(`cc examples/c/demo.c -Iinclude -Ltarget/release -lshannon_edge`). Errors
are negative codes (`sedge_error_message` describes them); invalid input is
reported, never aborts the host process. CI runs the Python tests on Linux,
macOS and Windows.

**On board, without Rust:** `c/` is the fast packet profile in portable
C99. It is two files and needs only `<stdint.h>`, `<stddef.h>` and
`<string.h>`. It uses no malloc, recursion, floating point or globals; the
caller provides a single memory block. It is bit-exact with the Rust crate:
the golden stream matches, and 151,200 of 151,200 Venus Express payloads
are byte-identical. Measured on this repository's test machines:

* Code size at -Os: about 5.9 KB on Cortex-M4 and rv32imc.
* Speed: 85–100% of Rust's.
* Tested on riscv32, Cortex-M4, i386, MIPS and PowerPC (big-endian) under
  qemu.
* Clean under ASan, UBSan and Valgrind, with no warnings from gcc or clang.

See `c/README.md`.

## How it works

```
             ┌──────────── models (each predicts P(next bit = 1)) ────────────┐
 history ──▶ │ order 0 · order 1 · order 2 · order 3 · order 4 · order 6      │
             │ word · previous word + word · sparse · match (long repeats)    │
             └───────────────────────────────┬────────────────────────────────┘
                                             ▼
                3 online neural mixers (weights picked by context)
                                             ▼
                          final mixer ─▶ 3 SSE / APM stages
                                             ▼
                      p ─▶ arithmetic coder ─▶ -log2(p) bits
```

* **Context models** keep adaptive bit probabilities in hash tables laid out
  so that each context touches one 64-byte cache line per nibble.
* **The match model** finds the longest earlier occurrence of the recent
  bytes and predicts that history repeats.
* **Mixers** are online logistic regressions that learn, while compressing,
  which models to trust in which situation.
* **SSE stages** correct the remaining bias of the mixed probability.
* The decoder runs the exact same model on the same history, so nothing but
  the coded surprise is stored. All arithmetic is integer, so output is
  bit-identical on every platform — enforced by a golden-stream test on
  Linux, macOS and Windows.

The file format is specified in [`docs/FORMAT.md`](docs/FORMAT.md).

## Project layout

| Path | Contents |
|---|---|
| `src/model.rs` | The predictor: context models, match model, mixers, SSE |
| `src/coder.rs` | Binary arithmetic coder |
| `src/math.rs` | Integer logistic functions and hashing |
| `src/lib.rs` | Public API and `.sedge` container |
| `src/train.rs` | Dictionary trainer (`sedge train`) |
| `src/main.rs` | `sedge` command-line tool |
| `src/ffi.rs`, `include/shannon_edge.h` | C ABI |
| `c/` | Fast packet profile in portable C99, bit-exact with Rust |
| `fuzz/` | Coverage-guided fuzzing of every decoder |
| `python/` | Python binding (ctypes) and its tests |
| `tests/` | Round-trip, adversarial, corruption and golden-format tests |
| `bench/compare.py` | Benchmark against gzip, bzip2, xz, zstd and brotli |
| `bench/shared_knowledge.py` | Compression with vs. without a shared dictionary |
| `bench/small_messages.py` | Many small records: sedge vs zstd with a trained dictionary |
| `bench/streams.py`, `examples/session_bench.rs` | Record streams: sedge sessions vs zstd streaming |
| `bench/telemetry.py` | ESA spacecraft telemetry: sedge vs CCSDS 121 and zstd |
| `src/packet.rs`, `examples/packet_bench.rs` | Packet profile for fixed-length housekeeping packets |
| `src/packet_fast.rs`, `examples/packet_fast_bench.rs` | Fast packet profile: one decision per byte, one symbol per changed byte |
| `examples/packet_robust.rs` | Packet profile under simulated packet loss (key packets, epochs, priming) |
| `src/fec.rs`, `examples/packet_fec.rs` | Packet-level Reed–Solomon erasure code; packet profile + erasure code under loss |
| `examples/frame_fec.rs` | Packets packed into transfer frames, Reed–Solomon over frames, frame loss |
| `bench/c/ccsds124_loss.c` | CCSDS 124 under the same simulated loss (open C implementation) |
| `examples/slepian_wolf.rs` | Slepian–Wolf prototype: XOR-only encoder, ground-side decoder ([results](bench/results/slepian_wolf.md)) |
| `bench/ccsds124.py` | Venus Express packets vs CCSDS 124 / POCKET+ (reference output and parameter sweep) |
| `bench/mission.py`, `bench/results/` | Every channel of an ESA mission through CCSDS 121 and the flight profile |
| `bench/anomaly.py`, `examples/flight_surprise.rs` | Anomaly detection from the compressor's surprise (ESA labels) |
| `docs/THEORY.md` | The limits, with proofs, and how to move them honestly |
| `docs/FORMAT.md` | `.sedge` format specification |
| `ROADMAP.md` | Where this goes next |

## License

MIT — see [LICENSE](LICENSE).
