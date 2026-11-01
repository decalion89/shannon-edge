# sedge_fast: the fast packet profile in portable C99

A dependency-free C99 implementation of the shannon-edge **fast packet
profile** (`src/packet_fast.rs`, `FastPacketSession`). It is **bit-exact**
with the Rust crate: the same packets, layout, priming and epochs give the
same payload bytes, so a C encoder on board can talk to a Rust decoder on
the ground, or the other way round.

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
make test        # golden + unit tests, then again under ASan + UBSan
make warnings    # -Werror, gcc and clang:
                 #   -std=c99 -Wall -Wextra -Wpedantic -Wconversion -Wshadow
make cross       # golden test on riscv32, Cortex-M4, i386, MIPS BE/LE,
                 # PPC32 BE (clang + ld.lld + qemu-user)
make size
make bench DATA=venus-express.ccsds LEN=90
```

`SAN_CC` selects the sanitizer compiler (default `$(CC)`; clang needs its
compiler-rt sanitizer runtimes installed).
