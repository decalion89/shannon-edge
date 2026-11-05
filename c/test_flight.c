/* Unit tests of the flight profile (hosted; build with
 * -DSEDGE_FLIGHT_TEST_HOOKS and link with -lm): internal tables, round
 * trips, garbage and truncated frames, argument and buffer errors, the frame
 * bound, alignment, and the Kraft helpers (the e-value precision is checked
 * against long double, the only floating point anywhere, here in the test).
 */
#include "sedge_flight.h"
#include "test_flight_data.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

const int16_t *sedge_flight_test_stretch(void);
const uint16_t *sedge_flight_test_neg_log2(void);
const uint32_t *sedge_flight_test_recip(void);

static int failures;

#define CHECK(cond)                                                      \
    do {                                                                 \
        if (!(cond)) {                                                   \
            printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);       \
            failures++;                                                  \
        }                                                                \
    } while (0)

static void *xmalloc(size_t n)
{
    void *p = malloc(n);
    if (p == NULL) {
        printf("out of memory\n");
        exit(2);
    }
    return p;
}

static sedge_flight *new_session(uint32_t bits, uint32_t tb, void **mem)
{
    size_t need = sedge_flight_memory_bytes(bits, tb);
    sedge_flight *s = NULL;
    *mem = xmalloc(need);
    CHECK(sedge_flight_init(&s, *mem, need, bits, tb) == 0);
    return s;
}

/* ------------------------------------------------------------- tables */

static const int SQ[33] = {1, 2, 4, 6, 10, 17, 27, 45, 74, 120, 194, 311, 488, 747, 1102, 1546,
                           2048, 2550, 2994, 3349, 3608, 3785, 3902, 3976, 4022, 4051, 4069,
                           4079, 4086, 4090, 4092, 4094, 4095};

static int squash_ref(int x)
{
    int w, i;
    if (x >= 2047) {
        return 4095;
    }
    if (x <= -2047) {
        return 1;
    }
    w = x & 127;
    i = (x >> 7) + 16;
    return (SQ[i] * (128 - w) + SQ[i + 1] * w + 64) >> 7;
}

static void test_tables(void)
{
    static int t[4096];
    const int16_t *st = sedge_flight_test_stretch();
    const uint16_t *nl = sedge_flight_test_neg_log2();
    const uint32_t *rc = sedge_flight_test_recip();
    int pi = 0, x, j, bad = 0;
    uint32_t p, d, v;
    /* src/math.rs build_stretch */
    for (x = -2047; x <= 2047; x++) {
        int sv = squash_ref(x);
        for (j = pi; j <= sv; j++) {
            t[j] = x;
        }
        pi = sv + 1;
    }
    for (j = pi; j < 4096; j++) {
        t[j] = 2047;
    }
    for (j = 0; j < 4096; j++) {
        bad += st[j] != t[j];
    }
    CHECK(bad == 0);
    /* src/flight.rs NEG_LOG2 */
    bad = nl[0] != 0u;
    for (p = 1; p <= 4096u; p++) {
        uint32_t n = 0, frac = 0, bit = 128;
        uint64_t y;
        while ((p >> (n + 1u)) != 0u) {
            n++;
        }
        y = ((uint64_t)p << 16) >> n;
        while (bit != 0u) {
            y = (y * y) >> 16;
            if (y >= (UINT64_C(2) << 16)) {
                y >>= 1;
                frac |= bit;
            }
            bit >>= 1;
        }
        bad += nl[p] != (12u << 8) - ((n << 8) | frac);
        /* and within 1.5/256 bit of -log2(p / 4096), as the Rust test */
        bad += fabs((double)nl[p] + log2((double)p / 4096.0) * 256.0) > 1.5;
    }
    CHECK(bad == 0);
    /* Division by multiplication: exact for every counter update. */
    for (d = 2; d <= 62u; d++) {
        for (v = 0; v < 65536u; v++) {
            bad += (uint32_t)(((uint64_t)v * rc[d - 2u]) >> 32) != v / d;
        }
    }
    CHECK(bad == 0);
}

/* --------------------------------------------------------- round trips */

/* Compress `n` samples in packets of `packet`, decode, compare; returns
 * the total frame size and the largest frame / bound ratio seen (x1000). */
static size_t roundtrip(const uint16_t *s, size_t n, uint32_t bits, uint32_t tb, size_t packet,
                        uint32_t *worst_permille)
{
    void *ma, *mb;
    sedge_flight *tx = new_session(bits, tb, &ma), *rx = new_session(bits, tb, &mb);
    size_t cap = sedge_flight_max_frame(packet, bits), at = 0, total = 0;
    uint8_t *f = xmalloc(cap);
    uint16_t *d = xmalloc(packet * sizeof *d + 1u);
    uint32_t *sa = xmalloc(packet * sizeof *sa + 1u), *sb = xmalloc(packet * sizeof *sb + 1u);
    while (at < n || (n == 0u && at == 0u)) {
        size_t k = n - at < packet ? n - at : packet, len = 0, m = 0, bound;
        CHECK(sedge_flight_compress_scored(tx, s + at, k, f, cap, &len, sa) == 0);
        bound = sedge_flight_max_frame(k, bits);
        CHECK(len <= bound);
        if (worst_permille != NULL && len * 1000u / bound > *worst_permille) {
            *worst_permille = (uint32_t)(len * 1000u / bound);
        }
        CHECK(sedge_flight_decompress_scored(rx, f, len, d, packet, &m, sb) == 0);
        CHECK(m == k && memcmp(d, s + at, k * sizeof *d) == 0 &&
              memcmp(sa, sb, k * sizeof *sa) == 0);
        CHECK(sedge_flight_last_overrun(rx) <= SEDGE_FLIGHT_MAX_OVERRUN);
        total += len;
        at += k;
        if (n == 0u) {
            break;
        }
    }
    free(f);
    free(d);
    free(sa);
    free(sb);
    free(ma);
    free(mb);
    return total;
}

static void test_roundtrips(void)
{
    static uint16_t s[20000];
    static size_t sizes[20001];
    static const uint32_t bitsv[] = {1, 2, 7, 8, 12, 15, 16};
    uint64_t rng = 5;
    uint32_t worst = 0, i, j;
    for (i = 0; i < sizeof bitsv / sizeof bitsv[0]; i++) {
        uint32_t b = bitsv[i];
        size_t size, raw;
        (void)gen2(b, b, s, 20000u, sizes, 20001u);
        size = roundtrip(s, 20000u, b, 14u, 256u, &worst);
        raw = 20000u * b / 8u;
        CHECK(size < raw / 2u || b < 7u); /* below 7 bits the walk is noise */
        for (j = 0; j < 5000u; j++) {
            s[j] = (uint16_t)(rng_next(&rng) & ((UINT32_C(1) << b) - 1u));
        }
        (void)roundtrip(s, 5000u, b, 12u, 256u, &worst);
        (void)roundtrip(s, 600u, b, 13u, 1u, &worst);
    }
    {
        static const uint16_t edge[6] = {0, 65535, 0, 65535, 1, 65534};
        (void)roundtrip(edge, 6u, 16u, 12u, 1u, &worst);
        (void)roundtrip(edge, 6u, 16u, 16u, 6u, &worst);
        (void)roundtrip(edge, 0u, 8u, 12u, 1u, &worst);
    }
    /* Alternating extremes: the most expensive input we know. */
    for (j = 0; j < 4000u; j++) {
        s[j] = (uint16_t)((j & 1u) ? 65535u : 0u);
    }
    (void)roundtrip(s, 4000u, 16u, 12u, 64u, &worst);
    for (j = 0; j < 4000u; j++) {
        s[j] = (uint16_t)rng_next(&rng);
    }
    (void)roundtrip(s, 4000u, 16u, 12u, 64u, &worst);
    printf("largest frame: %u.%u%% of SEDGE_FLIGHT_MAX_FRAME\n", worst / 10u, worst % 10u);
    /* Empty packets in the middle of a stream (as tests/flight.rs). */
    {
        static const uint16_t p0[3] = {1, 2, 3}, p2[2] = {4, 5};
        const uint16_t *ps[4] = {p0, NULL, p2, NULL};
        static const size_t ns[4] = {3, 0, 2, 0};
        void *ma, *mb;
        sedge_flight *tx = new_session(8, 12, &ma), *rx = new_session(8, 12, &mb);
        uint8_t f[64];
        uint16_t d[4];
        size_t len, m;
        for (j = 0; j < 4u; j++) {
            CHECK(sedge_flight_compress_scored(tx, ps[j], ns[j], f, sizeof f, &len, NULL) == 0);
            CHECK(ns[j] != 0u || (len == 1u && f[0] == 0u));
            CHECK(sedge_flight_decompress_scored(rx, f, len, d, 4u, &m, NULL) == 0 && m == ns[j]);
            CHECK(ns[j] == 0u || memcmp(d, ps[j], ns[j] * sizeof d[0]) == 0);
        }
        free(ma);
        free(mb);
    }
}

/* A glitch the model has never seen stands out in the surprise (the
 * tests/flight.rs check, on the integer GEN2 stream). */
static void test_surprise_glitch(void)
{
    static uint16_t s[10000];
    static uint32_t a[10000];
    static size_t sizes[10001];
    void *m;
    sedge_flight *tx = new_session(12, 14, &m);
    uint8_t f[SEDGE_FLIGHT_MAX_FRAME(256u, 12u)];
    size_t i, len;
    uint64_t sum = 0;
    (void)gen2(12u, 9u, s, 10000u, sizes, 10001u);
    for (i = 7000; i < 7010u; i++) {
        s[i] = (uint16_t)((s[i] + 1500u) % 4096u);
    }
    for (i = 0; i < 10000u; i += 256u) {
        size_t k = 10000u - i < 256u ? 10000u - i : 256u;
        CHECK(sedge_flight_compress_scored(tx, s + i, k, f, sizeof f, &len, a + i) == 0);
    }
    for (i = 6000; i < 7000u; i++) {
        sum += a[i];
    }
    CHECK(a[7000] > 5u * (sum / 1000u));
    free(m);
}

/* ----------------------------------------------------- hostile input */

static void test_garbage(void)
{
    static uint16_t d[1u << 16];
    static uint32_t su[1u << 16];
    uint8_t f[600];
    uint64_t rng = 77;
    void *m;
    sedge_flight *s;
    size_t len, n, i, k;
    int r;
    uint32_t ok = 0, err = 0;
    /* tests/flight.rs garbage_frames_never_panic_or_hang */
    for (len = 0; len < 64u; len++) {
        s = new_session(12, 12, &m);
        for (i = 0; i < len; i++) {
            f[i] = (uint8_t)rng_next(&rng);
        }
        r = sedge_flight_decompress_scored(s, f, len, d, sizeof d / sizeof d[0], &n, su);
        CHECK(r == 0 || r == SEDGE_FLIGHT_E_TRUNCATED || r == SEDGE_FLIGHT_E_TOO_LARGE ||
              r == SEDGE_FLIGHT_E_BUFFER);
        free(m);
    }
    s = new_session(12, 12, &m);
    {
        static const uint8_t big[5] = {0xff, 0xff, 0xff, 0xff, 0x7f};
        static const uint8_t six[6] = {0xff, 0xff, 0xff, 0xff, 0xff, 0x01};
        CHECK(sedge_flight_decompress_scored(s, big, 5, d, 1u << 16, &n, NULL) ==
              SEDGE_FLIGHT_E_TOO_LARGE);
        CHECK(sedge_flight_decompress_scored(s, six, 6, d, 1u << 16, &n, NULL) ==
              SEDGE_FLIGHT_E_TOO_LARGE);
        CHECK(sedge_flight_decompress_scored(s, big, 0, d, 1u << 16, &n, NULL) ==
              SEDGE_FLIGHT_E_TRUNCATED);
        CHECK(sedge_flight_decompress_scored(s, NULL, 0, d, 1u << 16, &n, NULL) ==
              SEDGE_FLIGHT_E_TRUNCATED);
        CHECK(sedge_flight_decompress_scored(s, big, 3, d, 1u << 16, &n, NULL) ==
              SEDGE_FLIGHT_E_TRUNCATED);
    }
    free(m);
    /* Random frames on every width; decoding up to 65536 samples. */
    for (k = 0; k < 3000u; k++) {
        uint32_t bits = 1u + (uint32_t)(k % 16u);
        s = new_session(bits, 12u + (uint32_t)(k % 3u), &m);
        for (i = 0; i < 4u; i++) {
            size_t fl = (size_t)(rng_next(&rng) % sizeof f), j;
            for (j = 0; j < fl; j++) {
                f[j] = (uint8_t)rng_next(&rng);
            }
            if (fl > 0u && (k & 1u)) {
                f[0] = (uint8_t)(f[0] & 0x7fu); /* a plausible count */
            }
            r = sedge_flight_decompress_scored(s, f, fl, d, sizeof d / sizeof d[0], &n, su);
            if (r == 0) {
                ok++;
                for (j = 0; j < n; j++) {
                    CHECK((d[j] >> bits) == 0u);
                }
            } else {
                err++;
                CHECK(r == SEDGE_FLIGHT_E_TRUNCATED || r == SEDGE_FLIGHT_E_TOO_LARGE ||
                      r == SEDGE_FLIGHT_E_BUFFER);
            }
        }
        free(m);
    }
    printf("random frames: %u decoded, %u rejected\n", ok, err);
    /* Truncated and bit-flipped valid frames. */
    {
        static uint16_t smp[256];
        static size_t sz[257];
        uint8_t full[SEDGE_FLIGHT_MAX_FRAME(256u, 12u)];
        size_t flen, cut, over = 0;
        void *mt;
        sedge_flight *tx = new_session(12, 14, &mt);
        (void)gen2(12u, 3u, smp, 256u, sz, 257u);
        CHECK(sedge_flight_compress_scored(tx, smp, 256u, full, sizeof full, &flen, NULL) == 0);
        for (cut = 0; cut <= flen; cut++) {
            s = new_session(12, 14, &m);
            r = sedge_flight_decompress_scored(s, full, cut, d, 256u, &n, NULL);
            if (r == 0 && sedge_flight_last_overrun(s) > SEDGE_FLIGHT_MAX_OVERRUN) {
                over++;
            }
            free(m);
        }
        printf("truncated frames: %u of %u flagged by last_overrun > %u\n", (unsigned)over,
               (unsigned)flen, SEDGE_FLIGHT_MAX_OVERRUN);
        for (i = 0; i < flen * 8u; i++) {
            full[i / 8u] = (uint8_t)(full[i / 8u] ^ (1u << (i % 8u)));
            s = new_session(12, 14, &m);
            (void)sedge_flight_decompress_scored(s, full, flen, d, 1u << 16, &n, su);
            free(m);
            full[i / 8u] = (uint8_t)(full[i / 8u] ^ (1u << (i % 8u)));
        }
        free(mt);
    }
}

/* ------------------------------------------- arguments, buffers, memory */

static void test_errors(void)
{
    static uint64_t mem[SEDGE_FLIGHT_MEMORY_BYTES(8u, 12u) / 8u + 2u];
    sedge_flight *s = NULL, *t = NULL;
    uint8_t f[SEDGE_FLIGHT_MAX_FRAME(64u, 8u)], g[SEDGE_FLIGHT_MAX_FRAME(64u, 8u)];
    uint16_t smp[64], d[64];
    size_t n, m, len, glen, off;
    uint32_t b, tb;
    void *ma, *mb;
    for (b = 0; b <= 17u; b++) {
        for (tb = 10; tb <= 25u; tb++) {
            int ok = b >= 1u && b <= 16u && tb >= 12u && tb <= 24u;
            size_t need = sedge_flight_memory_bytes(b, tb);
            CHECK((need != 0u) == ok);
            if (ok) {
                CHECK(need == SEDGE_FLIGHT_MEMORY_BYTES(b, tb));
            }
        }
    }
    CHECK(sedge_flight_init(&s, mem, sizeof mem, 0u, 12u) == SEDGE_FLIGHT_E_ARGUMENT && s == NULL);
    CHECK(sedge_flight_init(&s, mem, sizeof mem, 8u, 11u) == SEDGE_FLIGHT_E_ARGUMENT);
    CHECK(sedge_flight_init(&s, NULL, sizeof mem, 8u, 12u) == SEDGE_FLIGHT_E_ARGUMENT);
    CHECK(sedge_flight_init(NULL, mem, sizeof mem, 8u, 12u) == SEDGE_FLIGHT_E_ARGUMENT);
    CHECK(sedge_flight_init(&s, mem, SEDGE_FLIGHT_MEMORY_BYTES(8u, 12u) - 1u, 8u, 12u) ==
          SEDGE_FLIGHT_E_MEMORY);
    CHECK(sedge_flight_compress_scored(NULL, smp, 1, f, sizeof f, &n, NULL) ==
          SEDGE_FLIGHT_E_ARGUMENT);
    CHECK(sedge_flight_bits_per_sample(NULL) == 0u && sedge_flight_last_overrun(NULL) == 0u);
    CHECK(sedge_flight_max_frame(10u, 0u) == 0u && sedge_flight_max_frame((size_t)-1, 16u) == 0u);
    CHECK(sedge_flight_max_frame(10u, 16u) == SEDGE_FLIGHT_MAX_FRAME(10u, 16u));
    for (n = 0; n < 64u; n++) {
        smp[n] = (uint16_t)(n * 3u);
    }
    /* Any alignment of the block: the same frames. */
    for (off = 0; off < 8u; off++) {
        CHECK(sedge_flight_init(&s, (unsigned char *)mem + off, sizeof mem - 8u, 8u, 12u) == 0);
        CHECK(sedge_flight_bits_per_sample(s) == 8u);
        CHECK(sedge_flight_compress_scored(s, smp, 64u, off ? g : f, sizeof f, off ? &glen : &len,
                                           NULL) == 0);
        CHECK(off == 0u || (glen == len && memcmp(f, g, len) == 0));
    }
    /* A sample out of range: rejected, nothing learned. */
    s = new_session(8, 12, &ma);
    t = new_session(8, 12, &mb);
    smp[10] = 256u;
    CHECK(sedge_flight_compress_scored(s, smp, 64u, f, sizeof f, &len, NULL) ==
          SEDGE_FLIGHT_E_ARGUMENT);
    smp[10] = 30u;
    CHECK(sedge_flight_compress_scored(s, smp, 64u, f, sizeof f, &len, NULL) == 0);
    CHECK(sedge_flight_compress_scored(t, smp, 64u, g, sizeof g, &glen, NULL) == 0);
    CHECK(len == glen && memcmp(f, g, len) == 0);
    /* Output too small: E_BUFFER with the exact size needed; the prefix is
     * right; the packet was learned (both sessions stay in step). */
    for (m = 0; m < len; m += 3u) {
        size_t need;
        uint8_t small[SEDGE_FLIGHT_MAX_FRAME(64u, 8u)];
        CHECK(sedge_flight_compress_scored(s, smp, 64u, small, m, &need, NULL) ==
              SEDGE_FLIGHT_E_BUFFER);
        CHECK(sedge_flight_compress_scored(t, smp, 64u, g, sizeof g, &glen, NULL) == 0);
        CHECK(need == glen && memcmp(small, g, m) == 0);
    }
    free(ma);
    free(mb);
    /* Decoder: too many samples for the buffer leaves the state unchanged. */
    s = new_session(8, 12, &ma);
    t = new_session(8, 12, &mb);
    CHECK(sedge_flight_compress_scored(s, smp, 64u, f, sizeof f, &len, NULL) == 0);
    CHECK(sedge_flight_decompress_scored(t, f, len, d, 63u, &n, NULL) == SEDGE_FLIGHT_E_BUFFER &&
          n == 64u);
    CHECK(sedge_flight_decompress_scored(t, f, len, d, 64u, &n, NULL) == 0 && n == 64u &&
          memcmp(d, smp, sizeof d) == 0);
    CHECK(sedge_flight_decompress_scored(t, f, len, NULL, 0u, &n, NULL) == SEDGE_FLIGHT_E_BUFFER);
    CHECK(sedge_flight_decompress_scored(t, f, len, d, 64u, NULL, NULL) == SEDGE_FLIGHT_E_ARGUMENT);
    free(ma);
    free(mb);
    CHECK(strcmp(sedge_flight_error_message(SEDGE_FLIGHT_E_BUFFER), "output buffer too small") == 0);
    CHECK(strcmp(sedge_flight_error_message(12345), "unknown error") == 0);
}

/* ---------------------------------------------------------------- Kraft */

static long double exact_evalue(uint32_t c, uint32_t b, uint32_t k)
{
    long double e = ldexpl(1.0L, -(int)k);
    long double d = (long double)c / 256.0L - (long double)b;
    if (d - (long double)k > 60.0L) {
        return d - (long double)k + log2l(1.0L + (1.0L - e) * exp2l((long double)k - d));
    }
    return log2l((1.0L - e) + e * exp2l(d));
}

static void test_kraft(void)
{
    static const uint32_t ks[4] = {1, 4, 8, 12};
    uint64_t n;
    uint32_t t, b, ki, i;
    long double lo = 1e9L, hi = -1e9L;
    sedge_flight_cusum c;
    for (t = 1; t < 64u; t++) {
        n = UINT64_C(1) << t;
        CHECK(sedge_flight_kraft_t(n) == t && sedge_flight_kraft_t(n + 1u) == t + 1u &&
              sedge_flight_kraft_t(n - 1u) == (t == 1u ? 0u : t));
    }
    /* Log e-values: every surprise up to 512 bits, and large ones. */
    for (b = 1; b <= 16u; b++) {
        for (ki = 0; ki < 4u; ki++) {
            for (i = 0; i < 140000u; i++) {
                uint32_t cc = i < 131072u ? i : UINT32_C(0xffffffff) - (i - 131072u) * 491527u;
                long double diff = exact_evalue(cc, b, ks[ki]) -
                                   (long double)sedge_flight_log_evalue(cc, b, ks[ki]) /
                                       4294967296.0L;
                lo = diff < lo ? diff : lo;
                hi = diff > hi ? diff : hi;
            }
        }
    }
    printf("log e-value: exact - fixed point in [%.2Lf, %.2Lf] x 2^-32 bits\n",
           lo * 4294967296.0L, hi * 4294967296.0L);
    CHECK(lo > 0.0L && hi < ldexpl(1.0L, -28));
    CHECK(sedge_flight_log_evalue(1000u, 0u, 1u) == 0 && sedge_flight_log_evalue(1000u, 8u, 33u) == 0);
    /* Cumulative rule: nominal costs never alarm and keep the score at 0... */
    sedge_flight_cusum_init(&c);
    for (i = 0; i < 1000000u; i++) {
        CHECK(sedge_flight_cusum_update(&c, (i * 7u) % 1024u, 12u, 20u) == 0);
    }
    CHECK(sedge_flight_cusum_score(&c) == 0);
    /* ...one sample of b + t + 3 bits alarms at once (via e = 1/2)... */
    CHECK(sedge_flight_cusum_update(&c, (12u + 20u + 3u) * 256u, 12u, 20u) == 1);
    /* ...and decays back: S_(1/2) by 1 bit per nominal sample, S_(2^-12)
     * by only 0.00035 bit (11 bits take about 31,000 samples). */
    for (i = 0; i < 100u; i++) {
        (void)sedge_flight_cusum_update(&c, 0u, 12u, 20u);
    }
    CHECK(c.s[0] == 0 && c.s[3] > 0);
    for (i = 0; i < 40000u; i++) {
        (void)sedge_flight_cusum_update(&c, 0u, 12u, 20u);
    }
    CHECK(sedge_flight_cusum_score(&c) == 0);
    /* Moderate surprises (b + 8 bits, below the per-sample threshold of
     * b + 20) add up: alarm after a few. */
    for (i = 0; i < 10u && !sedge_flight_cusum_update(&c, (12u + 8u) * 256u, 12u, 20u); i++) {
    }
    printf("cumulative rule: %u samples of b + 8 bits to alarm at t = 20\n", i + 1u);
    CHECK(i < 10u && i >= 2u);
    for (i = 0; i < 3u; i++) {
        (void)sedge_flight_cusum_update(&c, UINT32_C(0xffffffff), 16u, 20u);
    }
    CHECK(sedge_flight_cusum_score(&c) > (INT64_C(1) << 56));
}

int main(void)
{
    test_tables();
    test_roundtrips();
    test_surprise_glitch();
    test_garbage();
    test_errors();
    test_kraft();
    printf(failures ? "test_flight: %d FAILED\n" : "test_flight: OK\n", failures);
    return failures ? 1 : 0;
}
