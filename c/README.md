# sedge_fast: the fast packet profile in portable C99

A dependency-free C99 implementation of the shannon-edge **fast packet
profile** (`src/packet_fast.rs`, `FastPacketSession`). It is **bit-exact**
with the Rust crate: the same packets, layout, priming and epochs give the
same payload bytes, so a C encoder on board can talk to a Rust decoder on
the ground, or the other way round.

The **flight profile** (`sedge_flight.h`, `sedge_flight.c`: integer
samples, per-sample surprise and the Kraft anomaly detector) is described
in [its own part](#sedge_flight-the-flight-profile-in-portable-c99) below,
and the **record transforms** (`sedge_fields.h`, `sedge_fields.c`: field
relations and deltas loaded from the `SEDGREL1` uplink) in
[theirs](#sedge_fields-record-transforms-in-portable-c99). All three follow
the same rules and share the Makefile.

- `sedge_fast.h`, `sedge_fast.c`: the codec (one file to add to a build)
- `test_golden.c`: the Rust golden stream, and a second golden stream that
  covers every recipe and class with priming and epochs. Runs hosted or with
  no C library at all.
- `test_fast.c`: round trips, garbage input, lost packets and epochs,
  learned layouts, argument errors, alignment, copies and the payload bound
- `crosscheck.c`: compares C and Rust payloads packet by packet on a data
  set
- `bench.c`: speed, like `examples/packet_fast_bench.rs`
- `test_gen.h`: the Rust test packet generator and FNV-1a
- `cross/`: a stand-in `string.h` and a no-libc start file, used by
  `make cross` to run the golden test under qemu
- `Makefile`: `make test`, `make warnings`, `make cross`, `make size`,
  `make bench DATA=... LEN=...`, `make crosscheck`

## API

```c
#include "sedge_fast.h"

/* Static allocation: 90-byte packets, default recipes (2 tables per
 * column), no epochs. */
static uint64_t mem[SEDGE_FAST_MEMORY_BYTES(90, 2 * 90, 0) / 8 + 1];
static uint8_t payload[SEDGE_FAST_MAX_PAYLOAD(90)];

sedge_fast *tx;
size_t n;
sedge_fast_init(&tx, mem, sizeof mem, 90, NULL, NULL, 0);
sedge_fast_compress(tx, packet, payload, sizeof payload, &n);   /* send n bytes */

/* Ground side, same layout:  */
sedge_fast_decompress(rx, payload, n, packet_out);
```

| Rust (`FastPacketSession`) | C |
|---|---|
| `new(len)`, `with_recipes(r)`, `with_layout(r, c)` | `sedge_fast_init(&s, mem, bytes, len, recipes or NULL, classes or NULL, flags)` |
| `prime(packets)` | `sedge_fast_prime(s, packets, n)` (`n * len` contiguous bytes) |
| `with_epochs(every)` | `sedge_fast_set_epochs(s, every)` (needs `SEDGE_FAST_EPOCHS` at init) |
| `compress(p)` | `sedge_fast_compress(s, p, out, cap, &n)` |
| `decompress(payload)` | `sedge_fast_decompress(s, payload, n, packet)` |
| `decompress_indexed(i, payload)` | `sedge_fast_decompress_indexed(s, i, payload, n, packet)` |
| `clone()` | `sedge_fast_copy(&dst, mem, bytes, src)` |
| `packet_len()`, `memory_bytes()` | `sedge_fast_packet_len(s)`, `sedge_fast_model_bytes(s)` |
| `learn_classes(len, h, 0.01, 0.9)` | `sedge_fast_learn_classes(len, h, n, 10000, 900000, out)` (thresholds in ppm) |
| `learn_recipes(len, h)` | `sedge_fast_learn_recipes(len, h, n, scratch, SEDGE_FAST_LEARN_SCRATCH_BYTES, out)` |
| `Error::SessionOutOfSync` | `SEDGE_FAST_E_OUT_OF_SYNC`; the expected index is `sedge_fast_count(s)` |
| panics on bad arguments | `SEDGE_FAST_E_ARGUMENT`, `_E_MEMORY`, `_E_STATE` (see the header) |

Recipes (`SEDGE_FAST_RECIPE_*`) and classes (`SEDGE_FAST_CLASS_*`) have the
same numbers as `packet_fast::recipe` and `packet_fast::class`. Nothing in
the Rust API is left out.

C additions:

- `sedge_fast_last_overrun(s)`: bytes the last decompress read past its
  payload. More than `SEDGE_FAST_MAX_OVERRUN` (7) proves the payload was
  truncated or corrupt. This is an optional check; decoding itself behaves
  as in Rust.
- `-DSEDGE_FAST_NO_LEARN` leaves out the two ground-side learning
  functions.

## Memory

All state lives in one caller-provided block. The codec does no
allocation, has no globals and keeps only small fixed-size locals on the
stack.

```
SEDGE_FAST_MEMORY_BYTES(len, tables, epochs)
  = 8 + 128 + (1 + epochs) * round_up_8(8 + 1032 * tables + 137 * len)
```

- `tables` is the total number of delta tables: 2 per column for the
  default recipe, otherwise 2/10/10/16/20 per column for recipes 0-4 (at
  most `20 * len`). `sedge_fast_memory_bytes(len, recipes, flags)` returns
  the same value at run time.
- Per column: one 1032-byte table per context (256 frequencies, a 257-node
  Fenwick tree and the total), 128 bytes of "same?" probabilities, an
  8-byte column record and 1 byte of the previous packet.
- With epochs, the block holds a second copy of the model: the snapshot
  every epoch restarts from.
- The 8 + 128 bytes are alignment slack and the session header. The block
  may have any alignment.
- Default recipes come to about `2201 * len` bytes. Venus Express (90-byte
  packets): 198,240 bytes (193.6 KiB), or 396,344 bytes with epochs. Rust
  `memory_bytes()` reports 198,450 bytes for the same model.
- `sedge_fast_learn_recipes` needs `SEDGE_FAST_LEARN_SCRATCH_BYTES`
  (20,648 bytes) of scratch memory.

The state is position-independent (offsets, not pointers), so
`sedge_fast_copy` clones a session into another block of any alignment,
for example to prime once and then make the encoder and decoder copies.

Strict aliasing: the codec stores its structures into the block. Give it
memory nothing else accesses: `malloc`, a linker-section region, or a
static array that is used only through this API, as in the example above.

### Payload bound

A payload is never larger than `SEDGE_FAST_MAX_PAYLOAD(len) = 14 * len + 8`
bytes. Any buffer at least that big makes `sedge_fast_compress` infallible.
Why the bound holds:

- every binary decision narrows the coder interval by at most a factor of
  4097 (12.0004 bits);
- a symbol costs at most 16 bits, or 8 decisions (96 bits) on the
  bit-by-bit fallback;
- so a column costs at most 108.004 bits, the static-group decision 12, and
  the flush 4 bytes.

The largest payload seen in the tests (random data, every class) was
1.36 × len. With a smaller buffer, `SEDGE_FAST_E_BUFFER` means the payload
did not fit. The packet was still learned, so the receiver should treat it
as lost; with epochs, it resumes at the next epoch.

## Guarantees

- **C99**: only `<stdint.h>`, `<stddef.h>` and `<string.h>` (`memcpy`,
  `memmove`, `memset`). No malloc, no recursion, no floating point, no
  globals. Reentrant across sessions; a session is not thread-safe.
- **No undefined behaviour**:
  - all coder and model arithmetic is on `uint32_t`, with explicit casts for
    every narrowing;
  - Rust's arithmetic right shift of a negative probability step is
    rewritten in unsigned form (`p - ((p + 15) >> 4)`);
  - 64-bit packet counts are never divided: the epoch phase is kept
    incrementally, and a shift-subtract modulo handles index jumps.
- **Checked by**: gcc ASan+UBSan (`make test`); clang
  `-fsanitize=undefined,implicit-conversion,bounds` in trap mode; Valgrind
  memcheck on the `-O2` binaries.
- **Same bytes on every CPU**: no dependence on endianness, `int` width or
  `size_t` width. The golden tests pass on x86-64, and under qemu on
  riscv32, Cortex-M4 (Thumb-2), i386, MIPS32 big- and little-endian and
  PowerPC32 big-endian (`make cross`). The codec also compiles cleanly for
  16-bit-`int` targets (MSP430, AVR).
- **Garbage never crashes**: a payload of any length or content (including
  empty or NULL with length 0) decodes to some packet with no out-of-bounds
  access. Every array index is bounded by construction: Fenwick walks stay
  within 0..256 and decoded symbols are clamped as in Rust.
- **Runtime helpers**: on CPUs without a hardware divider (Cortex-M0, rv32i)
  the compiler calls its standard runtime helpers (`__aeabi_uidiv`, and
  `__aeabi_llsr` on Thumb-1), as for any C code that divides.
- **Trusted state**: the session state is not self-checking. Protect it
  like any other RAM state (EDAC, scrubbing).

## Bit-exactness: how it was checked

| Check | Result |
|---|---|
| `GOLDEN_FAST` (tests/packet_fast.rs: 1000 × 48-byte packets, seed 2026) | 2093 bytes, FNV-1a 0x44699763fe3fe9c3: **match** |
| Layout stream: recipes `(k/3)%5`, classes `k%3`, primed with 200 packets, epochs of 64, 1000 packets, decoded with lost packets 70 and 500-502 | 1990 bytes, 0x03b6874b397e6285 (value from the Rust crate): **match** |
| Venus Express, 151,200 × 90 bytes, default layout | 151,200 / 151,200 payloads identical to Rust (3,846,435 bytes) |
| Venus Express, learned recipes + classes, primed with the first 10%, epochs of 256 | 136,080 / 136,080 identical (3,444,281 bytes) |
| Random 64-byte packets (20,000), default / all ALWAYS / all STATIC | 20,000 / 20,000 identical in each case |

The cross-checks run the bit-by-bit fallback path (interval narrower than
the frequency total) 368 to 1,920 times each, counted with
`-DSEDGE_FAST_TEST_HOOKS`. Every C payload is also decoded and verified.

Learning:

- `learn_classes` matches Rust on 90/90 Venus columns.
- `learn_recipes` matches on 89/90. The remaining column (8) is an exact
  tie: recipes 1 and 2 both cost 71.491943 bits. Rust's f64 sums differ in
  the last ulp; C's fixed-point sums are equal, so it takes the first.
  Either choice compresses the same.

To repeat the cross-check, dump Rust payloads (4-byte little-endian length,
then the bytes, per packet) with a small program built against the crate,
then run `crosscheck`:

```rust
// cargo project with: shannon-edge = { path = "..." }
use shannon_edge::packet_fast::FastPacketSession;
use std::io::Write;
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let (data, len) = (std::fs::read(&a[0]).unwrap(), a[1].parse::<usize>().unwrap());
    let ps: Vec<&[u8]> = data.chunks_exact(len).collect();
    let (hist, test) = ps.split_at(ps.len() / 10);
    let recipes = FastPacketSession::learn_recipes(len, hist);
    let classes = FastPacketSession::learn_classes(len, hist, 0.01, 0.9);
    std::fs::write("recipes.bin", &recipes).unwrap();
    std::fs::write("classes.bin", &classes).unwrap();
    let mut s = FastPacketSession::with_layout(&recipes, &classes);
    s.prime(hist.iter().copied());
    let mut s = s.with_epochs(256);
    let mut f = std::io::BufWriter::new(std::fs::File::create("learned.pay").unwrap());
    for p in test {
        let c = s.compress(p);
        f.write_all(&(c.len() as u32).to_le_bytes()).unwrap();
        f.write_all(&c).unwrap();
    }
}
```

```
make crosscheck
build/crosscheck venus-express.ccsds 90 learned.pay --recipes recipes.bin \
    --classes classes.bin --prime 15120 --epochs 256 --learn
```

## Speed

Venus Express, 151,200 × 90-byte packets, default layout. Each run
compresses every packet, then decompresses and verifies every one. One core
(`taskset`), `nice -n 10`, on a 4-core machine shared with long jobs (load
about 3.5), so the numbers are noisy. Values are the best and the median of
8 interleaved runs of each program. The Rust figure is
`examples/packet_fast_bench` (release profile: opt-level 3, fat LTO), and
its compress time includes allocating the payload `Vec`s.

| Build | Compress MB/s (best / median) | Decompress MB/s (best / median) |
|---|---:|---:|
| Rust `packet_fast_bench` | 53.6 / 42.1 | 33.7 / 29.4 |
| C, gcc 13 `-O2` | 45.5 / 35.9 | 31.2 / 26.4 |
| C, clang 18 `-O2` | 47.5 / 40.3 | 39.7 / 32.1 |
| C, gcc 13 `-O3` | 49.1 / 46.5 | 34.6 / 30.4 |
| C, clang 18 `-O3` | 44.8 / 40.5 | 39.1 / 33.5 |

C at `-O2` compresses at roughly 85-90% of the Rust speed and decompresses
at the same speed or faster. On this load, the differences are about as
large as the run-to-run noise.

Callgrind on the first 20,000 packets: Rust executes 655M instructions,
C (gcc `-O2`) 686M with 4.6M branch mispredictions against Rust's 4.8M.
Two changes narrowed the gap:

- inline hints on the coder helpers;
- mask-based (branch-free) Fenwick walks, which gcc otherwise compiles to
  branches that mispredict at every level.

Both change only speed, not the bytes produced. Not timed on flight
hardware.

## Code size

`make size`: text + data + bss of `sedge_fast.o` at `-Os` (no unwind
tables, no stack protector).

| Target | Full | `-DSEDGE_FAST_NO_LEARN` |
|---|---:|---:|
| x86-64, gcc 13 | 5,883 | 5,106 |
| RISC-V rv32imc, clang 18 | 6,052 | 5,192 |
| Cortex-M4 (Thumb-2), clang 18 | 5,848 | 4,972 |
| Cortex-M0 (Thumb-1), clang 18 | 5,818 | 4,950 |
| MSP430 (16-bit), clang 18 | 12,720 | 10,512 |

A flight encoder needs about 5 KB of code plus the memory block above.

## Building and testing

```
make test        # golden + unit tests of all three, then again under
                 # ASan + UBSan (make test-fast / test-flight / test-fields: one)
make warnings    # -Werror, gcc and clang:
                 #   -std=c99 -Wall -Wextra -Wpedantic -Wconversion -Wshadow
make cross       # golden tests (all three) on riscv32, Cortex-M4, i386, MIPS BE/LE,
                 # PPC32 BE (clang + ld.lld + qemu-user)
make size
make bench DATA=venus-express.ccsds LEN=90
make bench-flight DATA=samples.u16 TB=14
```

`SAN_CC` selects the sanitizer compiler (default `$(CC)`; clang needs its
compiler-rt sanitizer runtimes installed).

# sedge_flight: the flight profile in portable C99

A dependency-free C99 implementation of the shannon-edge **flight profile**
(`src/flight.rs`, `FlightSession`), with the parts of `src/coder.rs` it uses
(`finish_short` drops at most `MAX_IMPLIED_ZEROS` = 4 trailing zeros). It is
**bit-exact** with the Rust crate: the same samples give the same frames
and the same per-sample **surprise** (the cost of each sample in 1/256
bits, a `u32`), so either end of a link can be C or Rust. On top of it, a
training-free anomaly detector from `docs/KRAFT_DETECTION.md`.

- `sedge_flight.h`, `sedge_flight.c`: the codec and the detector (one file
  to add to a build)
- `test_flight_golden.c`: the Rust golden stream of `tests/flight.rs`, a
  second Rust stream over six (bits, table_bits) settings with uneven and
  empty packets, and a hash of the detector's fixed-point values. Runs
  hosted or with no C library at all (`make cross`).
- `test_flight.c`: internal tables rebuilt and compared, round trips,
  garbage / truncated / bit-flipped frames, argument and buffer errors,
  alignment, the frame bound, the detector's precision against
  `long double`
- `test_flight_data.h`: the golden samples (dumped by the Rust crate: the
  Rust generator uses `f64::sin`) and the integer-only second stream
- `crosscheck_flight.c`: compares C and Rust frames and surprise on a
  sample file
- `bench_flight.c`: speed

## API

```c
#include "sedge_flight.h"

/* 12-bit samples, 2^14-entry tables, static allocation. */
static uint64_t mem[SEDGE_FLIGHT_MEMORY_BYTES(12, 14) / 8 + 1];
static uint8_t frame[SEDGE_FLIGHT_MAX_FRAME(256, 12)];
static uint32_t surprise[256];

sedge_flight *tx;
size_t n;
sedge_flight_init(&tx, mem, sizeof mem, 12, 14);
sedge_flight_compress_scored(tx, samples, 256, frame, sizeof frame, &n, surprise);
/* send frame[0..n); surprise[] is the anomaly score, free of charge */

/* Ground side, same parameters: */
sedge_flight_decompress_scored(rx, frame, n, samples_out, 256, &count, surprise);
```

| Rust (`FlightSession`) | C |
|---|---|
| `new(bits, table_bits)` | `sedge_flight_init(&s, mem, bytes, bits, table_bits)` |
| `compress_scored(p, &mut v)` | `sedge_flight_compress_scored(s, p, n, out, cap, &len, v)` |
| `compress(p)` | the same with `surprise = NULL` |
| `decompress_scored(f, &mut v)` | `sedge_flight_decompress_scored(s, f, len, out, cap, &count, v)` |
| `decompress(f)` | the same with `surprise = NULL` |
| `bits_per_sample()` | `sedge_flight_bits_per_sample(s)` |
| `Error::Truncated`, `Error::TooLarge` | `SEDGE_FLIGHT_E_TRUNCATED` (-2), `SEDGE_FLIGHT_E_TOO_LARGE` (-7) |
| panics (bad parameters, a sample too wide) | `SEDGE_FLIGHT_E_ARGUMENT` (-1) |

There is no `sedge_flight_compress` or `sedge_flight_decompress`: the Rust
C ABI (`include/shannon_edge.h`) already exports `sedge_flight_new`,
`_compress`, `_decompress` and `_free`, and this port keeps clear of those
names so one ground tool can link both.

C additions:

- `SEDGE_FLIGHT_E_MEMORY` (block too small) and `SEDGE_FLIGHT_E_BUFFER`
  (output too small). On decompress, `E_BUFFER` means the frame holds more
  samples than `cap`; `count` is set to the number needed and the session is
  unchanged. On compress, the packet was already learned, so the two ends
  are out of step and must restart; `cap >= SEDGE_FLIGHT_MAX_FRAME(n, bits)`
  rules it out.
- A sample wider than `bits_per_sample` is rejected before anything is
  learned (Rust panics).
- `sedge_flight_last_overrun(s)`: bytes the last decompress read past its
  frame. More than `SEDGE_FLIGHT_MAX_OVERRUN` (7) proves the frame was
  truncated or corrupt. It is a weak check: it flags only the cuts close to
  the end of a frame (10 of the 115 possible cuts of a test frame).
- `-DSEDGE_FLIGHT_NO_CUSUM` leaves out the experimental cumulative detector.

## Memory

All state lives in one caller-provided block of any alignment; no
allocation, no globals, small fixed-size locals only.

```
SEDGE_FLIGHT_MEMORY_BYTES(bits, tb)
  = 72 + 16 * bits + 4 * (2^min(tb, bits + 1) + 2 * 2^tb + 2^min(tb, 16))
```

- 4-byte adaptive counters: the order-0, order-1 and order-2 tables of the
  transition model and the residual model's table, as in Rust;
- 16 bytes of mixer weights per bit of sample;
- 64 bytes of session header and 8 of alignment slack.

Bytes per channel (`sedge_flight_memory_bytes`):

| table_bits | 8-bit samples | 10-bit | 12-bit | 16-bit |
|---:|---:|---:|---:|---:|
| 12 | 51,400 | 57,576 | 65,800 | 65,864 |
| 13 | 100,552 | 106,728 | 131,336 | 131,400 |
| 14 | 198,856 | 205,032 | 229,640 | 262,472 |
| 15 | 395,464 | 401,640 | 426,248 | 524,616 |
| 16 | 788,680 | 794,856 | 819,464 | 1,048,904 |

The Rust session holds the same tables (same counters and weights); 12 to
24 table bits are accepted, as in Rust. The detector adds 32 bytes per
channel for the cumulative variant, nothing for the per-sample rule.

### Frame bound

A frame of n samples is never larger than
`SEDGE_FLIGHT_MAX_FRAME(n, bits) = 14 + n * (3 * bits + 4)` bytes:

- every binary decision narrows the coder interval by at most a factor of
  4097 (12.0004 bits), and emitted bytes never exceed the bits of narrowing
  divided by 8;
- the chosen model codes a valid sample with at most 2 * bits + 2
  decisions (residual: unary length up to bits + 2, mantissa up to bits);
- the sample count takes at most 10 bytes and the flush 4.

The largest frame in the tests (alternating 0 / 65535) reached 9.5% of the
bound; random 16-bit data is about 2 bytes per sample.

## Kraft anomaly detector

For a lossless sequential code, Kraft's inequality makes the surprise a
calibrated test statistic (`docs/KRAFT_DETECTION.md`): with b =
bits_per_sample, P(surprise >= b + t bits) <= 2^-t for every sample,
whatever came before, if the model is calibrated.

**Per-sample rule (primary, validated on ESA-ADB):**

```c
uint32_t t = sedge_flight_kraft_t(n_samples);          /* ceil(log2 N), integer */
int alarm = sedge_flight_kraft_alarm(surprise[i], bits, t);
/* i.e. surprise[i] >= sedge_flight_kraft_threshold(bits, t) = (bits + t) * 256 */
```

t = ceil(log2 N) allows one expected false alarm in N samples. There is
nothing to train and nothing to store.

**Cumulative rule (EXPERIMENTAL).** `bench/results/esa_adb.md` shows it
gains on ESA-AD Mission 1 lightweight (0.766 against 0.705) but collapses
where the model is even mildly overconfident (Mission 1 full, Mission 2),
so it is not the default and not recommended for operations. Per channel,
four CUSUMs S_e = max(0, S_e + x_e) of the log e-values

    x_e = log2((1 - e) + e * 2^(cost - b)),   e = 2^-1, 2^-4, 2^-8, 2^-12

alarm while max_e S_e >= t + 2 bits:

```c
sedge_flight_cusum c;                 /* 32 bytes per channel */
sedge_flight_cusum_init(&c);
alarm = sedge_flight_cusum_update(&c, surprise[i], bits, t);
```

Fixed point, no floating point:

- x_e and S_e are `int64_t` in units of 2^-32 bits. With u = surprise -
  256 (b + k) and e = 2^-k: y = (1 - 2^-k) + 2^(u/256) is formed exactly
  in Q62 (a 256-entry table of 2^(f/256) for the fraction of u), normalised
  to m in [1, 2), and log2(m) is a 64-entry reciprocal table (exact
  -log2 of the rounded reciprocal) plus ln(1 + r) to the r^4 term (r <
  2^-6, error below 2^-32).
- **Precision:** every x_e is rounded *down* (never above the exact value,
  so the e-value bound still holds) and lies 2.0 to 11.5 units of 2^-32
  bits below it. This is checked by `test_flight.c` against `long double`
  for every surprise up to 512 bits and for large ones, all b and the four
  values of e; the documented bound is 2^-28 bits (16 units). The smallest
  increment that matters, log2(1 - 2^-12) = -0.00035 bits, is resolved to
  about 1 part in 10^5.
- S_e saturates at 2^30 bits; t is capped at 2^28.
- Because every increment is rounded down, S_e drifts low while it stays
  positive: by at most 12 units of 2^-32 bits per sample. On ESA-AD
  Mission 1 channel 41 (15.4 M samples, t = 24), S_(2^-12) stayed positive
  for up to 296,000 samples in a row and the C scores ended at most
  3.5e-4 bits below a sequential `long double` evaluation. Being low, the
  C rule can only alarm less: 529,148 samples in alarm against 529,150
  (2 flags differ, both within 3.5e-4 bits of the threshold). The float64
  `cumsum` of `bench/anomaly_esaadb.py` gives the same 529,150.
- The tables (1.5 KB) are generated from 60-digit decimal arithmetic.

Two details differ from `bench/anomaly_esaadb.py`. The script raises a
per-sample alarm when cost > b + t (strict); this API follows
`docs/KRAFT_DETECTION.md` and alarms at cost >= b + t. They differ only
when a surprise is exactly (b + t) * 256: none on channel 41 at
t = 24. The script also takes b from the number of distinct values. That
equals bits_per_sample for its code files (codes 0..distinct-1).

## Guarantees

- **C99**: only `<stdint.h>`, `<stddef.h>` and `<string.h>` (`memset`). No
  malloc, no recursion, no floating point, no globals (constant tables
  only). Reentrant across sessions; a session is not thread-safe.
- **No undefined behaviour**:
  - the coder, counters and hashes are `uint32_t` / `uint64_t` arithmetic;
  - Rust's arithmetic right shifts of negative values (`dot >> 16`,
    `(x * err) >> 10`) are rewritten with offsets that keep the operand
    positive;
  - the mixer weights wrap like Rust's release `i32` (kept as `uint32_t`,
    read through a well-defined two's-complement conversion);
  - no 64-bit division anywhere; in the codec, 64-bit shifts are by
    constants, so 32-bit targets need no runtime helper.
- **Checked by**: gcc ASan+UBSan (`make test-flight`); clang
  `-fsanitize=undefined,implicit-conversion,bounds` in trap mode; Valgrind
  memcheck on the golden test.
- **Same bytes on every CPU**: the golden tests (frames, surprise and the
  detector's fixed-point values) pass on x86-64, and under qemu on riscv32,
  Cortex-M4 (Thumb-2), i386, MIPS32 big- and little-endian and PowerPC32
  big-endian, linked with `-nostdlib` (`make cross`).
- **Garbage never crashes**: the Rust garbage test, 12,000 random frames on
  every sample width (up to 65,536 decoded samples each), every truncation
  and every single-bit flip of a valid frame, all under the sanitizers. A
  decoded sample always fits `bits_per_sample`; work is bounded by the
  sample count, which is capped by the frame length as in Rust.
- **Trusted state**: the session is not self-checking; protect it like any
  other RAM state (EDAC, scrubbing).

## Bit-exactness: how it was checked

| Check | Result |
|---|---|
| `GOLDEN` (tests/flight.rs: telemetry(4096, 12, 2026), `new(12, 14)`, 256-sample packets) | 2140 bytes, FNV-1a 0xe373eda58555da7a: **match**; surprise hash 0xf7c227d90b62b922: **match** |
| GEN2: bits/table_bits (1,12) (4,12) (8,13) (12,14) (16,12) (16,16), 3000 samples each, packets of 0..511 | 6331 bytes, 0x50343dce1ac45b81, surprise 0x226e1e82a3600898 (values from the Rust crate): **match** |
| ESA-AD Mission 1, channels 41-46 (10-bit, 15,381,169 samples each), table_bits 14 | 6 × 60,083 / 60,083 frames identical; 6 × 15,381,169 / 15,381,169 surprise values identical |
| Channel 1 (16-bit, 10,513,336 samples; 34,550 distinct values), table_bits 14 and 16 | 41,068 / 41,068 frames and 10,513,336 / 10,513,336 surprise values identical, in both cases |
| Channel 12 (8-bit, 14,258,506 samples), table_bits 14 and 16 | 55,698 / 55,698 frames and 14,258,506 / 14,258,506 surprise values identical, in both cases |
| Channel 41, table_bits 12 | 60,083 / 60,083 and 15,381,169 / 15,381,169 identical |

In all, 157,212,867 samples and 614,113 frames, with no difference. The
sample files are made as `bench/anomaly_esaadb.py` makes them (distinct
values to ordered codes); the Rust side is the session of
`examples/flight_surprise.rs`.

Every C frame is also decoded by C, and the samples and surprise are
compared.

To repeat it, dump the Rust frames (4-byte little-endian length, then the
bytes, per frame) and surprise the way `examples/flight_surprise.rs` runs
the session, then run `crosscheck_flight`:

```rust
// cargo project with: shannon-edge = { path = "..." }
use shannon_edge::flight::FlightSession;
use std::io::Write;
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let raw = std::fs::read(&a[0]).unwrap();
    let tb: u32 = a.get(3).map_or(14, |v| v.parse().unwrap());
    let s: Vec<u16> = raw.chunks_exact(2).map(|c| u16::from_le_bytes([c[0], c[1]])).collect();
    let bits = (16 - s.iter().max().unwrap_or(&0).leading_zeros()).max(1);
    let mut tx = FlightSession::new(bits, tb);
    let (mut f, mut sur) = (std::io::BufWriter::new(std::fs::File::create(&a[1]).unwrap()), vec![]);
    for p in s.chunks(256) {
        let c = tx.compress_scored(p, &mut sur);
        f.write_all(&(c.len() as u32).to_le_bytes()).unwrap();
        f.write_all(&c).unwrap();
    }
    std::fs::write(&a[2], sur.iter().flat_map(|c| c.to_le_bytes()).collect::<Vec<u8>>()).unwrap();
}
```

```
make crosscheck
build/crosscheck_flight samples.u16 rust.frames rust.u32 14
```

## Speed

ESA-AD Mission 1 channels 41 (10-bit, 15.4 M samples) and 1 (16-bit,
10.5 M samples), table_bits 14, 256-sample packets. Each run compresses
every packet with its surprise, then decompresses and verifies every one
(`bench_flight`; the Rust figure is the same loop over `FlightSession`,
release profile with fat LTO). One core (`taskset`), `nice -n 10`, on a
4-core machine shared with a long job (load about 4), so the numbers are
noisy. Best and median of 6 interleaved runs, in million samples per
second:

| Build | ch 41 compress | ch 41 decompress | ch 1 compress | ch 1 decompress |
|---|---:|---:|---:|---:|
| Rust | 4.22 / 4.17 | 3.78 / 3.72 | 4.40 / 4.00 | 4.38 / 4.17 |
| C, gcc 13 `-O2` | 4.12 / 3.97 | 3.71 / 3.66 | 4.12 / 3.81 | 4.49 / 4.25 |
| C, clang 18 `-O2` | 4.02 / 3.83 | 3.77 / 3.66 | 4.01 / 3.90 | 4.60 / 3.52 |
| C, gcc 13 `-O3` | 4.24 / 4.05 | 3.74 / 3.70 | 4.13 / 3.96 | 4.33 / 3.97 |
| C, clang 18 `-O3` | 4.05 / 3.76 | 3.97 / 3.80 | 4.54 / 4.30 | 4.31 / 3.77 |

C runs at the speed of Rust, within the run-to-run noise: compress medians
are 0.92 to 1.07 times Rust's, decompress medians 0.84 to 1.02. Both ends
run both models on every sample (the one not chosen is only measured):
about 0.25 µs per sample on this machine. The counters divide by
multiplying with a reciprocal table instead of Rust's division, which
mostly helps CPUs with a slow divider or none. Not timed on flight
hardware.

## Code size

`make size`: text + data + bss of `sedge_flight.o` at `-Os`, and in
brackets the code alone; the rest is read-only tables.

| Target | Full | `-DSEDGE_FLIGHT_NO_CUSUM` |
|---|---:|---:|
| x86-64, gcc 13 | 22,824 (4,318) | 20,704 (3,766) |
| RISC-V rv32imc, clang 18 | 22,660 (4,286) | 20,324 (3,490) |
| Cortex-M4 (Thumb-2), clang 18 | 22,314 (3,780) | 20,078 (3,116) |
| Cortex-M0 (Thumb-1), clang 18 | 22,262 (3,728) | 19,994 (3,032) |
| MSP430 (16-bit), clang 18 | 30,560 (12,170) | 25,666 (8,816) |

About 3 KB of code. The tables are 16.7 KB of flash: `STRETCH` (4096 ×
int16, the inverse logistic of `src/math.rs`) and `NEG_LOG2` (4097 ×
uint16, the cost table of `src/flight.rs`), both needed for exactness and
speed, plus 1.5 KB for the cumulative detector. Neither has a symmetry that
would halve it.

# sedge_fields: record transforms in portable C99

A dependency-free C99 implementation of the sender and receiver side of
`src/fields.rs` (`RecordTransform`): field **relations** (within a record)
and field **deltas** (across records), loaded from the `SEDGREL1` uplink of
`docs/FORMAT.md` ("Record transforms"). It is **bit-exact** with the Rust
crate: the same uplink and records give the same transformed records, and
C accepts exactly the uplinks Rust accepts. Learning a transform
(`RecordTransform::learn`, floating point) is ground-side only and stays in
Rust.

- `sedge_fields.h`, `sedge_fields.c`: the transform (one file to add to a
  build)
- `test_fields_golden.c`: Rust golden values: forward outputs of three
  uplinks, and the verdicts, re-serialised uplinks and forward outputs of
  20,000 corrupted uplinks. Runs hosted or with no C library (`make cross`).
- `test_fields.c`: hand-computed values, every rejection rule, argument
  and memory errors, alignment, in-place calls, and the garbage-uplink fuzz
- `crosscheck_fields.c`: compares C and Rust on a data set, or on a file
  of random cases

## API

```c
#include "sedge_fields.h"

/* Static allocation: up to 16 fields, 8 relations, 64-byte records. */
static uint64_t mem[SEDGE_FIELDS_MEMORY_BYTES(16, 8, 64) / 8 + 1];

sedge_fields *t;
sedge_fields_init(&t, mem, sizeof mem, uplink, uplink_len);  /* checks everything */

/* On board (sender), records in order: */
sedge_fields_forward(t, record, len, out);       /* out may equal record */
/* ... compress out with a packet codec ... */

/* On the ground (receiver), after decoding, same order: */
sedge_fields_inverse(t, decoded, len, record_out);
```

| Rust (`RecordTransform`) | C |
|---|---|
| `from_bytes(b)` | `sedge_fields_init(&t, mem, bytes, b, n)` |
| `forward(rec)` | `sedge_fields_forward(t, rec, len, out)` |
| `inverse(rec)` | `sedge_fields_inverse(t, rec, len, out)` |
| `reset()` | `sedge_fields_reset(t)` |
| `to_bytes()` | `sedge_fields_to_bytes(t, out, cap, &n)` |
| `layout().len()`, `layout().fields()`, `deltas()` | `sedge_fields_record_len(t)`, `sedge_fields_field_count(t)`, `sedge_fields_get_field(t, k, &f)` (`f.delta`) |
| `relations()` | `sedge_fields_relation_count(t)`, `sedge_fields_get_relation(t, k, &r)` |
| `Error::BadModel` | `SEDGE_FIELDS_E_BAD_MODEL` (-12, as in `include/shannon_edge.h`) |
| panics (record of the wrong length) | `SEDGE_FIELDS_E_ARGUMENT` (-1) |

Not ported: `learn` (ground only), `Layout::parse` and `identity` (an
uplink with no relations and no delta flags is the identity). Field and
relation types mirror `fields::Field` and `fields::Relation`.

C additions:

- `sedge_fields_memory_bytes(uplink, n)`: the block size this uplink
  needs (0 if it is malformed);
- `SEDGE_FIELDS_E_MEMORY` (block too small) and `SEDGE_FIELDS_E_BUFFER`
  (`to_bytes` output too small; `n` is the size needed);
- forward and inverse work in place, or on overlapping buffers;
- a failed `sedge_fields_init` leaves `*out` NULL; a transform
  previously loaded in the same block must not be used afterwards (it is
  invalidated when the failure is a bad index).

Loading checks what Rust `from_bytes` checks, in the same way: magic; at
least one field; widths 1..255, and 1, 2, 4 or 8 for integer fields; flag
bits 4-7 zero; every relation index in range and on an integer field;
target different from both predictors; no target used twice; no target
used as a predictor (in any relation, before or after); exact length, no
trailing bytes. As in Rust, a delta bit on an opaque field is accepted and
dropped (so `to_bytes` writes it as 0), and the signed and big-endian bits
of an opaque field are kept. A relation may use the same predictor twice
(`i == j`). The only difference in order: an uplink that is well formed
but has a bad index, given a block too small for it, gets
`SEDGE_FIELDS_E_MEMORY` before the indices are checked.

## Memory

All state lives in one caller-provided block of any alignment: no
allocation, no globals, a few scalar locals.

```
SEDGE_FIELDS_MEMORY_BYTES(fields, relations, record_len)
  = 40 + 8 * fields + 8 * relations + 2 * record_len
```

- 8 bytes per field (offset, width, flags), 8 per relation (as uplinked);
- the previous record of each side (`prev_fwd`, `prev_inv`), used by the
  deltas: `2 * record_len`;
- 32 bytes of header and 8 of alignment slack.

INCART ECG (`i16le*12`, 3 relations): 208 bytes. AIS (14 fields, 34-byte
records): 220 bytes. The uplink is copied into the block, so it can be
discarded after `sedge_fields_init`. The largest possible uplink (65,535
fields of 255 bytes and 65,535 relations) needs 34.5 MB; on a 16-bit
`size_t` target, uplinks that do not fit are rejected with
`SEDGE_FIELDS_E_MEMORY` (`memory_bytes` returns 0).

## Guarantees

- **C99**: only `<stdint.h>`, `<stddef.h>` and `<string.h>` (`memcpy`,
  `memmove`, `memset`). No malloc, no recursion, no floating point, no
  globals (constant tables only). Reentrant across transforms; a transform
  is not thread-safe.
- **No undefined behaviour**:
  - every value is a `uint64_t`; Rust's wrapping `i64` products and sums
    followed by a mask to the field width are the same bits in unsigned
    arithmetic;
  - sign extension ORs in the high bits (`v | ~mask` when `v > mask / 2`),
    and `a`, `b` are sign-extended the same way from their raw bytes;
  - the floor of a relation, Rust's arithmetic `>> 1`, is
    `(s >> 1) | (s & 2^63)`; zigzag and unzigzag are written on unsigned
    values (`(d << 1) ^ (negative ? ~0 : 0)`, `(z >> 1) ^ (0 - (z & 1))`);
  - every shift is by a constant, so 32-bit CPUs need no 64-bit shift
    helper (64-bit multiplies are inline on all the targets below).
- **Checked by**: gcc ASan+UBSan (`make test-fields`); clang
  `-fsanitize=undefined,implicit-conversion,bounds,integer` in trap mode
  (all but the intended unsigned wrap: `-fno-sanitize=unsigned-integer-overflow,unsigned-shift-base`);
  Valgrind memcheck on both tests. No warnings with gcc 13 and clang 18 at
  `-O0` to `-O3` and `-Os` (`make warnings`: `-O2`).
- **Same bytes on every CPU**: the golden test passes on x86-64 and, under
  qemu with no C library, on riscv32, Cortex-M4 (Thumb-2), i386, MIPS32
  big- and little-endian and PowerPC32 big-endian (`make cross`).
- **Untrusted uplinks**: any byte string is either rejected or loads into
  a transform whose inverse undoes its forward step. Work per record is
  O(fields + relations + record length); loading is O(uplink length +
  record length).
- **Trusted state**: the block is not self-checking; protect it like any
  other RAM state (EDAC, scrubbing).

## Bit-exactness: how it was checked

The Rust side is a small program built against the crate (not in the
repository) that learns transforms, dumps the uplink and the Rust
`forward` output of every record, and checks Rust's own inverse.
`crosscheck_fields` then runs C `forward` on every record and compares it
with Rust's, and runs C `inverse` and compares it with the original.

| Data | Transform (learned on the first 10%, `max_bits` 2) | Result |
|---|---|---|
| INCART ECG, `i16le*12`, 4,626,000 records | 3 relations, no deltas | 4,626,000 / 4,626,000 forward identical; 4,626,000 / 4,626,000 restored |
| same | 3 relations, deltas on 9 fields | 4,626,000 / 4,626,000 identical; all restored |
| AIS tracks, `u32le*2,i32le*2,i16le*2,u16le*2,u8,u16le*4,u8`, 4,076,512 records | no relation found, no deltas (identity) | 4,076,512 / 4,076,512 identical; all restored |
| same | deltas on all 14 fields | 4,076,512 / 4,076,512 identical; all restored |
| same | deltas, `reset()` every 256 records | 4,076,512 / 4,076,512 identical; all restored |
| Random cases (3 seeds × 4,000) | see below | 12,000 / 12,000 verdicts equal; 9,160 / 9,160 `to_bytes` equal; 7,293,050 / 7,293,050 records identical and restored |

The random cases have random layouts of 1 to 40 fields: every integer
width (8 to 64 bits), signed and unsigned, little- and big-endian, and
opaque fields of 1 to 9 bytes. Values are random walks, full-range noise,
extremes (minimum and maximum of the type) or near-constants. A quarter
are learned by Rust on data with a planted relation (with and without
deltas); half are random valid uplinks with arbitrary `a`, `b` in
-128..127 (including -128 and 127 on 64-bit fields), random targets,
predictors and delta flags, shuffled relation order and junk flag bits on
opaque fields; a quarter are corrupted uplinks. Resets every 1, 7 or 100
records or never. In all, 5,608 accepted uplinks had relations and 6,842
had deltas.

`test_fields_golden` freezes a part of this: 81,000 bytes of forward
output (FNV-1a 0xbbea1a422146836f) and 20,000 corrupted uplinks, of
which Rust accepts 1,149 (FNV-1a of verdicts, uplinks and 3,447 forward
outputs 0x178ddd804ca480ff); C matches on every target above.

`test_fields` adds 2.76 million checks, among them a fuzz of 300,003
random, structured and corrupted uplinks (19,848 accepted, 476,352
records with deltas and resets inverted in place). Each verdict is also
compared with an independent, plain reading of the Rust rules, and each
accepted uplink must re-serialise to itself (up to the dropped delta bits
of opaque fields) and be a fixed point of `to_bytes` and `init`.

No deviation from Rust was found.

To repeat the cross-check, dump the uplink and the forward output with a
small program built against the crate, then run `crosscheck_fields`:

```rust
// cargo project with: shannon-edge = { path = "..." }
use shannon_edge::fields::{Layout, RecordTransform};
use std::io::Write;
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let (raw, lay) = (std::fs::read(&a[0]).unwrap(), Layout::parse(&a[1]).unwrap());
    let recs: Vec<&[u8]> = raw.chunks_exact(lay.len()).collect();
    let tf = RecordTransform::learn(lay, recs[..recs.len() / 10].iter().copied(), a[2] == "1", 2.0);
    std::fs::write("t.up", tf.to_bytes()).unwrap();
    let mut tx = RecordTransform::from_bytes(&tf.to_bytes()).unwrap();
    let mut f = std::io::BufWriter::new(std::fs::File::create("t.fwd").unwrap());
    for r in &recs {
        f.write_all(&tx.forward(r)).unwrap();
    }
}
```

```
make crosscheck
build/crosscheck_fields ecg_incart.bin t.up t.fwd [RESET]
```

## Code size

`make size`: text + data + bss of `sedge_fields.o` at `-Os`, and in
brackets the code alone (the rest is the magic and the error strings).

| Target | Total | Code |
|---|---:|---:|
| x86-64, gcc 13 | 2,939 | 2,761 |
| RISC-V rv32imc, clang 18 | 3,098 | 2,984 |
| Cortex-M4 (Thumb-2), clang 18 | 3,014 | 2,772 |
| Cortex-M0 (Thumb-1), clang 18 | 2,886 | 2,644 |
| MSP430 (16-bit), clang 18 | 5,936 | 5,822 |

About 3 KB, of which the sender alone (`init`, `forward`, `reset`) is
about two thirds; the linker drops the unused functions with
`-ffunction-sections -Wl,--gc-sections`.
