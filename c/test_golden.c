/* Golden streams: the C codec must produce exactly the bytes the Rust crate
 * produces.
 *
 * Model version 2 (two-speed flags, per-column windows).
 * 1. GOLDEN_FAST (tests/packet_fast.rs, golden_fast_stream_is_stable):
 *    default session, 1000 packets of 48 bytes, generator seed 2026, all
 *    payloads concatenated: length 2064, FNV-1a-64 0x1b52626dbcc31761.
 * 2. LAYOUT: every recipe x class x window combination, priming and
 *    epochs: recipes[k] = (k / 3) % 5, classes[k] = k % 3,
 *    windows[k] = k % 7 (with_layout_windows), prime with
 *    packets(200, 48, 7), epochs of 64, compress packets(1000, 48, 2027).
 * 3. SLOPES: the same with with_slopes(k % 2 == 1).
 * 4. RAMP: the accelerating ramp of tests/packet_fast.rs (slopes test):
 *    packet i = [(i * i / 200) as u8, rng(42) % 4, 9], 6000 packets, slope
 *    on column 0 (NORMAL classes), then every column ALWAYS with slopes.
 *    Expected values 2-4 computed by the Rust crate (see README.md).
 * Every stream is also decoded (2 and 3 with lost packets).
 *
 * Builds hosted (stdio) or, with -DSEDGE_FREESTANDING, with no C library at
 * all (cross/start.c supplies _start, write and exit) for qemu runs.
 */
#include "sedge_fast.h"
#include "test_gen.h"

#ifdef SEDGE_FREESTANDING
void test_write(const char *s);
#else
#include <stdio.h>
static void test_write(const char *s) { fputs(s, stdout); }
#endif

#define GOLDEN_LEN 2064u
#define GOLDEN_HASH UINT64_C(0x1b52626dbcc31761)
#define LAYOUT_LEN 2138u
#define LAYOUT_HASH UINT64_C(0xae3dc66a4f3440aa)
#define SLOPES_LEN 2236u
#define SLOPES_HASH UINT64_C(0x9266c293803ea6d1)
#define RAMP_LEN 5270u
#define RAMP_HASH UINT64_C(0xa5905fbb4a1fcf6f)
#define RAMP_ALWAYS_LEN 5683u
#define RAMP_ALWAYS_HASH UINT64_C(0xcfff2fb139459917)

#define PLEN 48u
#define NPKT 1000u
#define MEM SEDGE_FAST_MEMORY_BYTES(PLEN, 20u * PLEN, 1u)

static uint64_t mem_tx[MEM / 8u + 1u];
static uint64_t mem_rx[MEM / 8u + 1u];
static uint8_t history[200u * PLEN];

static void write_hex(uint64_t v)
{
    char s[19];
    int i;
    s[0] = '0';
    s[1] = 'x';
    for (i = 0; i < 16; i++) {
        s[2 + i] = "0123456789abcdef"[(v >> (60 - 4 * i)) & 15u];
    }
    s[18] = 0;
    test_write(s);
}

static void write_dec(uint32_t v)
{
    char s[11];
    int i = 10;
    s[i] = 0;
    do {
        s[--i] = (char)('0' + v % 10u);
        v /= 10u;
    } while (v != 0u && i > 0);
    test_write(s + i);
}

static int failures;

static void check(int ok, const char *what)
{
    if (!ok) {
        failures++;
        test_write("FAIL: ");
        test_write(what);
        test_write("\n");
    }
}

static int same_bytes(const uint8_t *a, const uint8_t *b, uint32_t n)
{
    uint32_t i;
    for (i = 0; i < n; i++) {
        if (a[i] != b[i]) {
            return 0;
        }
    }
    return 1;
}

static void report(const char *name, uint32_t len, uint64_t h, uint32_t want_len, uint64_t want_h)
{
    test_write(name);
    test_write(": ");
    write_dec(len);
    test_write(" bytes, fnv ");
    write_hex(h);
    test_write(len == want_len && h == want_h ? " (match)\n" : " (MISMATCH)\n");
    check(len == want_len && h == want_h, name);
}

static void golden_fast(void)
{
    sedge_fast *tx, *rx;
    gen_t g;
    uint8_t p[PLEN], q[PLEN], out[SEDGE_FAST_MAX_PAYLOAD(PLEN)];
    uint64_t h = FNV_INIT;
    uint32_t i, total = 0;
    size_t n;
    check(sedge_fast_init(&tx, mem_tx, sizeof mem_tx, PLEN, NULL, NULL, NULL, 0u) == 0, "init tx");
    check(sedge_fast_init(&rx, mem_rx, sizeof mem_rx, PLEN, NULL, NULL, NULL, 0u) == 0, "init rx");
    if (failures) {
        return;
    }
    gen_init(&g, 2026u);
    for (i = 0; i < NPKT; i++) {
        gen_packet(&g, p, PLEN);
        check(sedge_fast_compress(tx, p, out, sizeof out, &n) == 0, "compress");
        h = fnv(h, out, n);
        total += (uint32_t)n;
        check(sedge_fast_decompress(rx, out, n, q) == 0 && same_bytes(p, q, PLEN), "decode");
        check(sedge_fast_last_overrun(rx) <= SEDGE_FAST_MAX_OVERRUN, "overrun");
    }
    report("golden fast stream (Rust GOLDEN_LEN/GOLDEN_HASH)", total, h, GOLDEN_LEN, GOLDEN_HASH);
}

static void golden_layout(int slopes_on)
{
    uint8_t recipes[PLEN], classes[PLEN], windows[PLEN], slopes[PLEN];
    uint8_t p[PLEN], q[PLEN], out[SEDGE_FAST_MAX_PAYLOAD(PLEN)];
    sedge_fast *tx, *rx;
    gen_t g;
    uint64_t h = FNV_INIT;
    uint32_t i, total = 0;
    size_t n;
    for (i = 0; i < PLEN; i++) {
        recipes[i] = (uint8_t)((i / 3u) % 5u);
        classes[i] = (uint8_t)(i % 3u);
        windows[i] = (uint8_t)(i % 7u);
        slopes[i] = (uint8_t)(i % 2u);
    }
    gen_init(&g, 7u);
    for (i = 0; i < 200u; i++) {
        gen_packet(&g, history + i * PLEN, PLEN);
    }
    check(sedge_fast_init(&tx, mem_tx, sizeof mem_tx, PLEN, recipes, classes, windows,
                          SEDGE_FAST_EPOCHS) == 0,
          "init layout");
    if (slopes_on) {
        check(sedge_fast_set_slopes(tx, slopes) == 0, "slopes");
    }
    check(sedge_fast_prime(tx, history, 200u) == 0, "prime");
    check(sedge_fast_set_epochs(tx, 64u) == 0, "epochs");
    check(sedge_fast_copy(&rx, mem_rx, sizeof mem_rx, tx) == 0, "copy");
    if (failures) {
        return;
    }
    gen_init(&g, 2027u);
    for (i = 0; i < NPKT; i++) {
        int r;
        gen_packet(&g, p, PLEN);
        check(sedge_fast_compress(tx, p, out, sizeof out, &n) == 0, "compress layout");
        h = fnv(h, out, n);
        total += (uint32_t)n;
        if (i == 70u || (i >= 500u && i <= 502u)) {
            continue; /* lost */
        }
        r = sedge_fast_decompress_indexed(rx, i, out, n, q);
        if ((i > 70u && i < 128u) || (i > 502u && i < 512u)) {
            check(r == SEDGE_FAST_E_OUT_OF_SYNC, "waits for the epoch");
        } else {
            check(r == 0 && same_bytes(p, q, PLEN), "decode layout");
        }
    }
    if (slopes_on) {
        report("slopes stream (the same, slopes on odd columns)", total, h, SLOPES_LEN, SLOPES_HASH);
    } else {
        report("layout stream (recipes x classes x windows, prime, epochs)", total, h, LAYOUT_LEN,
               LAYOUT_HASH);
    }
}

/* The slopes test's accelerating ramp: column 0 follows its slope. */
static void golden_ramp(int always)
{
    static const uint8_t slope0[3] = {1, 0, 0}, all[3] = {1, 1, 1}, cl_always[3] = {2, 2, 2};
    sedge_fast *tx, *rx;
    uint8_t p[3], q[3], out[SEDGE_FAST_MAX_PAYLOAD(3)];
    uint64_t h = FNV_INIT, rng = 42u;
    uint32_t i, total = 0;
    size_t n;
    check(sedge_fast_init(&tx, mem_tx, sizeof mem_tx, 3u, NULL, always ? cl_always : NULL, NULL,
                          0u) == 0 &&
              sedge_fast_set_slopes(tx, always ? all : slope0) == 0,
          "init ramp");
    check(sedge_fast_copy(&rx, mem_rx, sizeof mem_rx, tx) == 0, "copy ramp");
    if (failures) {
        return;
    }
    for (i = 0; i < 6000u; i++) {
        p[0] = (uint8_t)(i * i / 200u);
        p[1] = (uint8_t)mod_small(rng_next(&rng), 4u);
        p[2] = 9u;
        check(sedge_fast_compress(tx, p, out, sizeof out, &n) == 0, "compress ramp");
        h = fnv(h, out, n);
        total += (uint32_t)n;
        check(sedge_fast_decompress(rx, out, n, q) == 0 && same_bytes(p, q, 3u), "decode ramp");
    }
    if (always) {
        report("ramp, ALWAYS columns with slopes", total, h, RAMP_ALWAYS_LEN, RAMP_ALWAYS_HASH);
    } else {
        report("ramp, slope on column 0", total, h, RAMP_LEN, RAMP_HASH);
    }
}

int test_golden_main(void);

int test_golden_main(void)
{
    golden_fast();
    golden_layout(0);
    golden_layout(1);
    golden_ramp(0);
    golden_ramp(1);
    test_write(failures ? "test_golden: FAILED\n" : "test_golden: OK\n");
    return failures ? 1 : 0;
}

#ifndef SEDGE_FREESTANDING
int main(void) { return test_golden_main(); }
#endif
