/* Golden streams of the flight profile: the C codec must produce exactly
 * the frames and per-sample surprise the Rust crate produces.
 *
 * 1. GOLDEN (tests/flight.rs, golden_flight_stream_is_stable): 2140 bytes,
 *    FNV-1a-64 0xe373eda58555da7a, plus the surprise hash.
 * 2. GEN2: six (bits, table_bits) configurations, uneven and empty packets.
 * 3. Kraft helpers, and a hash of the cumulative detector's log e-values
 *    (a C-only value: it checks every CPU computes the same fixed point).
 * Every frame is also decoded and checked (samples and surprise).
 *
 * Builds hosted (stdio) or, with -DSEDGE_FREESTANDING, with no C library at
 * all (cross/start.c supplies _start, write and exit) for qemu runs.
 */
#include "sedge_flight.h"
#include "test_flight_data.h"

#ifdef SEDGE_FREESTANDING
void test_write(const char *s);
#else
#include <stdio.h>
static void test_write(const char *s) { fputs(s, stdout); }
#endif

/* Hash of sedge_flight_log_evalue over the grid in golden_cusum. */
#define EVALUE_HASH UINT64_C(0x163c6c7138abb377)

#define FNV_INIT UINT64_C(0xcbf29ce484222325)

static uint64_t fnv(uint64_t h, const uint8_t *b, size_t n)
{
    size_t i;
    for (i = 0; i < n; i++) {
        h = (h ^ b[i]) * UINT64_C(0x100000001b3);
    }
    return h;
}

/* FNV-1a of u32 values as little-endian bytes (Rust to_le_bytes). */
static uint64_t fnv_u32(uint64_t h, const uint32_t *v, size_t n)
{
    size_t i;
    uint32_t k;
    for (i = 0; i < n; i++) {
        for (k = 0; k < 32u; k += 8u) {
            h = (h ^ ((v[i] >> k) & 0xffu)) * UINT64_C(0x100000001b3);
        }
    }
    return h;
}

#define MEM_MAX SEDGE_FLIGHT_MEMORY_BYTES(16u, 16u)

static uint64_t mem_tx[MEM_MAX / 8u + 1u];
static uint64_t mem_rx[MEM_MAX / 8u + 1u];
static uint16_t samples[GEN2_SAMPLES > 4096u ? GEN2_SAMPLES : 4096u];
static uint16_t decoded[512];
static uint32_t sur_tx[512], sur_rx[512];
static uint8_t frame[SEDGE_FLIGHT_MAX_FRAME(512u, 16u)];
static size_t sizes[GEN2_SAMPLES + 1u];
static int failures;

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

static void check(int ok, const char *what)
{
    if (!ok) {
        test_write("FAIL: ");
        test_write(what);
        test_write("\n");
        failures++;
    }
}

static void report(const char *name, uint32_t len, uint64_t h, uint64_t hs,
                   uint32_t want_len, uint64_t want_h, uint64_t want_hs)
{
    int ok = len == want_len && h == want_h && hs == want_hs;
    test_write(ok ? "match    " : "MISMATCH ");
    test_write(name);
    test_write(": ");
    write_dec(len);
    test_write(" bytes, frames ");
    write_hex(h);
    test_write(", surprise ");
    write_hex(hs);
    test_write("\n");
    if (!ok) {
        test_write("  expected ");
        write_dec(want_len);
        test_write(" bytes, ");
        write_hex(want_h);
        test_write(", ");
        write_hex(want_hs);
        test_write("\n");
        failures++;
    }
}

/* Compress `n` samples in packets of sizes[] with (bits, tb), decode each
 * frame with a second session; accumulate frame and surprise hashes. */
static void run_stream(uint32_t bits, uint32_t tb, const uint16_t *s,
                       const size_t *sz, size_t np, uint32_t *total,
                       uint64_t *h, uint64_t *hs, uint32_t *sum)
{
    sedge_flight *tx, *rx;
    size_t i, k, at = 0, n, m;
    check(sedge_flight_init(&tx, mem_tx, sizeof mem_tx, bits, tb) == 0, "init tx");
    check(sedge_flight_init(&rx, mem_rx, sizeof mem_rx, bits, tb) == 0, "init rx");
    if (failures) {
        return;
    }
    for (i = 0; i < np; i++) {
        int same = 1;
        check(sedge_flight_compress_scored(tx, s + at, sz[i], frame, sizeof frame, &n, sur_tx) == 0,
              "compress");
        *h = fnv(*h, frame, n);
        *hs = fnv_u32(*hs, sur_tx, sz[i]);
        *total += (uint32_t)n;
        check(sedge_flight_decompress_scored(rx, frame, n, decoded, 512u, &m, sur_rx) == 0 &&
                  m == sz[i],
              "decompress");
        for (k = 0; k < sz[i] && k < m; k++) {
            same &= decoded[k] == s[at + k] && sur_rx[k] == sur_tx[k];
            *sum += sur_tx[k];
        }
        check(same, "decoded samples and surprise equal the sender's");
        check(sedge_flight_last_overrun(rx) <= SEDGE_FLIGHT_MAX_OVERRUN, "overrun bound");
        at += sz[i];
    }
}

static void golden(void)
{
    size_t i;
    uint32_t total = 0, sum = 0;
    uint64_t h = FNV_INIT, hs = FNV_INIT;
    for (i = 0; i < 4096u; i++) {
        samples[i] = golden_samples[i];
    }
    for (i = 0; i < 16u; i++) {
        sizes[i] = 256u;
    }
    run_stream(12u, 14u, samples, sizes, 16u, &total, &h, &hs, &sum);
    report("GOLDEN flight (tests/flight.rs)", total, h, hs, GOLDEN_LEN, GOLDEN_HASH,
           GOLDEN_SURPRISE_HASH);
    check(sum == GOLDEN_SURPRISE_SUM, "golden surprise sum");
}

static void golden_gen2(void)
{
    uint32_t c, total = 0, sum = 0;
    uint64_t h = FNV_INIT, hs = FNV_INIT;
    for (c = 0; c < GEN2_CONFIGS; c++) {
        size_t np = gen2(gen2_config[c][0], 100u + c, samples, GEN2_SAMPLES, sizes,
                         GEN2_SAMPLES + 1u);
        run_stream(gen2_config[c][0], gen2_config[c][1], samples, sizes, np, &total, &h, &hs,
                   &sum);
    }
    report("GEN2 (bits 1..16, tables 12..16)", total, h, hs, GEN2_LEN, GEN2_HASH,
           GEN2_SURPRISE_HASH);
}

static void golden_kraft(void)
{
    uint64_t h = FNV_INIT;
    uint32_t c, b, k, i;
    check(sedge_flight_kraft_t(0u) == 0u && sedge_flight_kraft_t(1u) == 0u &&
              sedge_flight_kraft_t(2u) == 1u && sedge_flight_kraft_t(3u) == 2u &&
              sedge_flight_kraft_t(4u) == 2u && sedge_flight_kraft_t(5u) == 3u &&
              sedge_flight_kraft_t(UINT64_C(1) << 40) == 40u &&
              sedge_flight_kraft_t((UINT64_C(1) << 40) + 1u) == 41u &&
              sedge_flight_kraft_t(UINT64_C(0xffffffffffffffff)) == 64u,
          "kraft_t");
    check(sedge_flight_kraft_threshold(12u, 23u) == 35u * 256u &&
              sedge_flight_kraft_alarm(35u * 256u, 12u, 23u) == 1 &&
              sedge_flight_kraft_alarm(35u * 256u - 1u, 12u, 23u) == 0 &&
              sedge_flight_kraft_threshold(16u, UINT32_C(0xffffffff)) == UINT32_C(0xffffffff),
          "kraft threshold");
#ifndef SEDGE_FLIGHT_NO_CUSUM
    for (b = 1; b <= 16u; b += 5u) {
        for (k = 1; k <= 32u; k++) {
            for (i = 0; i < 700u; i++) {
                int64_t x;
                uint32_t lo, hi;
                c = i < 600u ? i * 37u : UINT32_C(0xffffffff) - (i - 600u) * 1234567u;
                x = sedge_flight_log_evalue(c, b, k);
                lo = (uint32_t)((uint64_t)x & 0xffffffffu);
                hi = (uint32_t)((uint64_t)x >> 32);
                h = fnv_u32(h, &lo, 1u);
                h = fnv_u32(h, &hi, 1u);
            }
        }
    }
    test_write(h == EVALUE_HASH ? "match    " : "MISMATCH ");
    test_write("cumulative Kraft log e-values (C fixed point): ");
    write_hex(h);
    test_write("\n");
    if (h != EVALUE_HASH) {
        failures++;
    }
#else
    (void)c;
    (void)b;
    (void)k;
    (void)i;
    (void)h;
#endif
}

int test_golden_main(void);

int test_golden_main(void)
{
    golden();
    golden_gen2();
    golden_kraft();
    test_write(failures ? "test_flight_golden: FAILED\n" : "test_flight_golden: OK\n");
    return failures ? 1 : 0;
}

#ifndef SEDGE_FREESTANDING
int main(void) { return test_golden_main(); }
#endif
