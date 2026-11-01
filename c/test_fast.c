/* Unit tests of the C fast profile: the Rust tests/packet_fast.rs cases
 * (round trips, compression, garbage, lost packets and epochs, learned
 * recipes and classes) plus C-specific ones (argument errors, memory and
 * buffer sizes, alignment, copies, the payload bound). Run them under
 * -fsanitize=address,undefined too (make test does). */
#include "sedge_fast.h"
#include "test_gen.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

unsigned long sedge_fast_test_fallbacks;

static int failures;
#define CHECK(c)                                                         \
    do {                                                                 \
        if (!(c)) {                                                      \
            failures++;                                                  \
            fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #c); \
        }                                                                \
    } while (0)

/* A session in freshly allocated memory (released by the caller). */
static sedge_fast *new_session(void **mem, size_t len, const uint8_t *recipes,
                               const uint8_t *classes, unsigned flags)
{
    size_t bytes = sedge_fast_memory_bytes(len, recipes, flags);
    sedge_fast *s = NULL;
    *mem = malloc(bytes);
    if (*mem == NULL || sedge_fast_init(&s, *mem, bytes, len, recipes, classes, flags) != 0) {
        fprintf(stderr, "cannot create a session of length %zu\n", len);
        exit(2);
    }
    return s;
}

static uint8_t *make_packets(size_t n, size_t len, uint64_t seed)
{
    uint8_t *p = malloc(n * len);
    gen_t g;
    size_t i;
    gen_init(&g, seed);
    for (i = 0; i < n; i++) {
        gen_packet(&g, p + i * len, len);
    }
    return p;
}

static double worst_ratio; /* largest payload / len seen */

/* Compress and decompress n packets through tx/rx; total payload bytes. */
static size_t roundtrip_with(sedge_fast *tx, sedge_fast *rx, const uint8_t *ps, size_t n, size_t len)
{
    size_t cap = sedge_fast_max_payload(len), total = 0, i, plen;
    uint8_t *out = malloc(cap), *q = malloc(len);
    for (i = 0; i < n; i++) {
        const uint8_t *p = ps + i * len;
        CHECK(sedge_fast_compress(tx, p, out, cap, &plen) == 0);
        CHECK(plen <= cap);
        if ((double)plen / (double)len > worst_ratio) {
            worst_ratio = (double)plen / (double)len;
        }
        CHECK(sedge_fast_decompress(rx, out, plen, q) == 0);
        CHECK(memcmp(p, q, len) == 0);
        CHECK(sedge_fast_last_overrun(rx) <= SEDGE_FAST_MAX_OVERRUN);
        total += plen;
    }
    free(out);
    free(q);
    return total;
}

static size_t roundtrip(const uint8_t *ps, size_t n, size_t len, const uint8_t *recipes,
                        const uint8_t *classes, const uint8_t *prime, size_t nprime)
{
    void *mt, *mr;
    sedge_fast *tx = new_session(&mt, len, recipes, classes, 0u);
    sedge_fast *rx = new_session(&mr, len, recipes, classes, 0u);
    size_t total;
    CHECK(sedge_fast_prime(tx, prime, nprime) == 0);
    CHECK(sedge_fast_prime(rx, prime, nprime) == 0);
    total = roundtrip_with(tx, rx, ps, n, len);
    free(mt);
    free(mr);
    return total;
}

static void test_roundtrips_and_compresses(void)
{
    static const size_t lens[] = {1, 9, 32, 90, 1000};
    size_t i;
    for (i = 0; i < sizeof lens / sizeof lens[0]; i++) {
        size_t len = lens[i];
        uint8_t *ps = make_packets(2000, len, len);
        size_t size = roundtrip(ps, 2000, len, NULL, NULL, NULL, 0);
        if (len >= 32) {
            CHECK(size * 6 < 2000 * len);
        }
        free(ps);
    }
}

static void test_random_and_extreme(void)
{
    uint64_t rng = 9;
    size_t i, k, len = 64, n = 2000;
    uint8_t *ps = malloc(n * len), recipes[64], classes[64];
    for (i = 0; i < n * len; i++) {
        ps[i] = (uint8_t)rng_next(&rng);
    }
    roundtrip(ps, n, len, NULL, NULL, NULL, 0);
    /* Every recipe and every class on random data (worst case for the
     * payload bound: many symbols, many bit-by-bit fallbacks). */
    for (k = 0; k < len; k++) {
        recipes[k] = (uint8_t)(k % 5);
        classes[k] = (uint8_t)(k / 5 % 3);
    }
    roundtrip(ps, n, len, recipes, classes, NULL, 0);
    memset(classes, SEDGE_FAST_CLASS_ALWAYS, len);
    roundtrip(ps, n, len, recipes, classes, NULL, 0);
    memset(classes, SEDGE_FAST_CLASS_STATIC, len);
    roundtrip(ps, n, len, recipes, classes, NULL, 0);
    free(ps);
    /* Alternating extremes: every byte changes, by every delta. */
    n = 600;
    len = 16;
    ps = malloc(n * len);
    for (i = 0; i < n; i++) {
        for (k = 0; k < len; k++) {
            ps[i * len + k] = (uint8_t)((i * (k + 1)) % 256);
        }
    }
    roundtrip(ps, n, len, NULL, NULL, NULL, 0);
    free(ps);
}

/* Garbage payloads of every length decode to some packet, never crash,
 * under every class and recipe. */
static void test_garbage(void)
{
    uint64_t rng = 4;
    size_t len = 40, n, k, i, layout;
    uint8_t payload[400], q[40], recipes[40], classes[40];
    for (layout = 0; layout < 4; layout++) {
        void *m;
        sedge_fast *rx;
        for (k = 0; k < len; k++) {
            recipes[k] = (uint8_t)(layout == 0 ? 0 : k % 5);
            classes[k] = (uint8_t)(layout < 2 ? 0 : layout == 2 ? k % 3 : 2);
        }
        rx = new_session(&m, len, recipes, classes, SEDGE_FAST_EPOCHS);
        CHECK(sedge_fast_set_epochs(rx, 7) == 0);
        for (n = 0; n < 3000; n++) {
            size_t plen = n % 400;
            for (i = 0; i < plen; i++) {
                payload[i] = (uint8_t)rng_next(&rng);
            }
            if (n % 5 == 0 && plen > 0) {
                memset(payload, n % 10 == 0 ? 0xff : 0x00, plen); /* extremes */
            }
            if (n % 3 == 0) {
                int r = sedge_fast_decompress_indexed(rx, sedge_fast_count(rx) + n % 4, payload, plen, q);
                CHECK(r == 0 || r == SEDGE_FAST_E_OUT_OF_SYNC);
            } else {
                CHECK(sedge_fast_decompress(rx, plen ? payload : NULL, plen, q) == 0);
            }
        }
        free(m);
    }
}

/* tests/packet_fast.rs lost_packet_recovers_at_next_epoch. */
static void test_lost_packet_epochs(void)
{
    size_t len = 32, i, cap = SEDGE_FAST_MAX_PAYLOAD(32), plen;
    uint8_t *ps = make_packets(300, len, 5), *hist = make_packets(50, len, 6);
    uint8_t out[SEDGE_FAST_MAX_PAYLOAD(32)], q[32];
    void *mt, *mr;
    sedge_fast *tx = new_session(&mt, len, NULL, NULL, SEDGE_FAST_EPOCHS);
    sedge_fast *rx = new_session(&mr, len, NULL, NULL, SEDGE_FAST_EPOCHS);
    CHECK(sedge_fast_prime(tx, hist, 50) == 0 && sedge_fast_set_epochs(tx, 64) == 0);
    CHECK(sedge_fast_prime(rx, hist, 50) == 0 && sedge_fast_set_epochs(rx, 64) == 0);
    CHECK(sedge_fast_prime(rx, hist, 1) == SEDGE_FAST_E_STATE);
    for (i = 0; i < 300; i++) {
        int r;
        CHECK(sedge_fast_compress(tx, ps + i * len, out, cap, &plen) == 0);
        if (i == 70) {
            continue; /* lost */
        }
        r = sedge_fast_decompress_indexed(rx, i, out, plen, q);
        if (i >= 71 && i < 128) {
            CHECK(r == SEDGE_FAST_E_OUT_OF_SYNC);
        } else {
            CHECK(r == 0 && memcmp(q, ps + i * len, len) == 0);
        }
    }
    /* An old index is refused without changing anything. */
    CHECK(sedge_fast_decompress_indexed(rx, 5, out, plen, q) == SEDGE_FAST_E_OUT_OF_SYNC);
    CHECK(sedge_fast_count(rx) == 300);
    free(mt);
    free(mr);
    free(ps);
    free(hist);
}

static void test_learned_layouts(void)
{
    size_t len = 32, k, r;
    uint8_t *all = make_packets(3000, len, 11), *test = all + 300 * len;
    uint8_t recipes[32], again[32], fixed[32], classes[32];
    void *scratch = malloc(SEDGE_FAST_LEARN_SCRATCH_BYTES);
    size_t learned, base;
    CHECK(sedge_fast_learn_recipes(len, all, 300, scratch, SEDGE_FAST_LEARN_SCRATCH_BYTES, recipes) == 0);
    CHECK(sedge_fast_learn_recipes(len, all, 300, scratch, SEDGE_FAST_LEARN_SCRATCH_BYTES, again) == 0);
    CHECK(memcmp(recipes, again, len) == 0);
    for (k = 0; k < len; k++) {
        CHECK(recipes[k] < SEDGE_FAST_RECIPE_COUNT);
    }
    for (r = 0; r < SEDGE_FAST_RECIPE_COUNT; r++) {
        memset(fixed, (int)r, len);
        roundtrip(test, 2700, len, fixed, NULL, all, 300);
    }
    learned = roundtrip(test, 2700, len, recipes, NULL, all, 300);
    base = roundtrip(test, 2700, len, NULL, NULL, all, 300);
    CHECK(learned <= base + 32);
    printf("learned recipes: %zu bytes vs default %zu\n", learned, base);

    free(all);
    all = make_packets(2000, len, 21);
    test = all + 200 * len;
    CHECK(sedge_fast_learn_classes(len, all, 200, 10000, 900000, classes) == 0);
    CHECK(memchr(classes, SEDGE_FAST_CLASS_STATIC, len) != NULL);
    CHECK(memchr(classes, SEDGE_FAST_CLASS_ALWAYS, len) != NULL);
    CHECK(sedge_fast_learn_recipes(len, all, 200, scratch, SEDGE_FAST_LEARN_SCRATCH_BYTES, recipes) == 0);
    roundtrip(test, 1800, len, recipes, classes, all, 200);
    memset(classes, SEDGE_FAST_CLASS_STATIC, len);
    roundtrip(test, 1800, len, recipes, classes, all, 200);
    memset(classes, SEDGE_FAST_CLASS_ALWAYS, len);
    roundtrip(test, 1800, len, recipes, classes, all, 200);
    /* Edge cases of the history: empty and one packet. */
    CHECK(sedge_fast_learn_classes(len, NULL, 0, 10000, 900000, classes) == 0);
    CHECK(classes[0] == SEDGE_FAST_CLASS_STATIC);
    CHECK(sedge_fast_learn_recipes(len, all, 1, scratch, SEDGE_FAST_LEARN_SCRATCH_BYTES, recipes) == 0);
    CHECK(sedge_fast_learn_recipes(len, all, 1, scratch, 100, recipes) == SEDGE_FAST_E_MEMORY);
    free(scratch);
    free(all);
}

static void test_api_errors(void)
{
    uint8_t bad_recipe[2] = {0, 9}, bad_class[2] = {0, 7}, ok2[2] = {0, 0};
    uint8_t p[16] = {1, 2, 3}, out[300], q[16];
    unsigned char *mem;
    size_t bytes, plen, off;
    sedge_fast *s, *c;
    void *m;

    memset(out, 0x5a, sizeof out);
    CHECK(sedge_fast_memory_bytes(0, NULL, 0) == 0);
    CHECK(sedge_fast_memory_bytes(65537, NULL, 0) == 0);
    CHECK(sedge_fast_memory_bytes(2, bad_recipe, 0) == 0);
    CHECK(sedge_fast_memory_bytes(2, NULL, 2u) == 0);
    CHECK(sedge_fast_memory_bytes(65536, NULL, SEDGE_FAST_EPOCHS) ==
          SEDGE_FAST_MEMORY_BYTES(65536, 2 * 65536, 1));
    CHECK(sedge_fast_memory_bytes(90, NULL, 0) == SEDGE_FAST_MEMORY_BYTES(90, 180, 0));
    CHECK(sedge_fast_memory_bytes(48, NULL, 0) == SEDGE_FAST_MEMORY_BYTES(48, 96, 0));
    printf("memory: 90-byte packets %zu bytes (%zu with epochs)\n",
           sedge_fast_memory_bytes(90, NULL, 0), sedge_fast_memory_bytes(90, NULL, 1));

    bytes = sedge_fast_memory_bytes(16, NULL, 0);
    mem = malloc(bytes + 64);
    CHECK(sedge_fast_init(NULL, mem, bytes, 16, NULL, NULL, 0) == SEDGE_FAST_E_ARGUMENT);
    CHECK(sedge_fast_init(&s, NULL, bytes, 16, NULL, NULL, 0) == SEDGE_FAST_E_ARGUMENT);
    CHECK(sedge_fast_init(&s, mem, bytes, 0, NULL, NULL, 0) == SEDGE_FAST_E_ARGUMENT);
    CHECK(sedge_fast_init(&s, mem, bytes, 2, bad_recipe, NULL, 0) == SEDGE_FAST_E_ARGUMENT);
    CHECK(sedge_fast_init(&s, mem, bytes, 2, NULL, bad_class, 0) == SEDGE_FAST_E_ARGUMENT);
    CHECK(sedge_fast_init(&s, mem, bytes - 8 - 1, 16, NULL, NULL, 0) == SEDGE_FAST_E_MEMORY);
    CHECK(s == NULL);
    CHECK(sedge_fast_init(&s, mem, 3, 16, NULL, NULL, 0) == SEDGE_FAST_E_MEMORY);
    /* Any alignment works with the advertised size. */
    for (off = 0; off < 8; off++) {
        CHECK(sedge_fast_init(&s, mem + off, bytes, 16, NULL, NULL, 0) == 0);
        CHECK(sedge_fast_packet_len(s) == 16);
    }
    CHECK(sedge_fast_set_epochs(s, 4) == SEDGE_FAST_E_STATE); /* no room */
    CHECK(sedge_fast_compress(s, p, NULL, 0, &plen) == SEDGE_FAST_E_BUFFER);
    CHECK(sedge_fast_count(s) == 1); /* consumed: treat as lost */
    CHECK(sedge_fast_compress(s, NULL, out, sizeof out, &plen) == SEDGE_FAST_E_ARGUMENT);
    CHECK(sedge_fast_compress(s, p, out, sizeof out, NULL) == SEDGE_FAST_E_ARGUMENT);
    CHECK(sedge_fast_decompress(s, NULL, 3, q) == SEDGE_FAST_E_ARGUMENT);
    CHECK(sedge_fast_decompress(s, out, 3, NULL) == SEDGE_FAST_E_ARGUMENT);
    CHECK(sedge_fast_decompress(NULL, out, 3, q) == SEDGE_FAST_E_ARGUMENT);
    CHECK(sedge_fast_prime(s, NULL, 1) == SEDGE_FAST_E_ARGUMENT);
    CHECK(sedge_fast_count(NULL) == 0 && sedge_fast_packet_len(NULL) == 0);
    CHECK(sedge_fast_init(&s, mem, bytes, 2, ok2, ok2, 0) == 0);
    CHECK(sedge_fast_copy(&c, mem, 10, s) == SEDGE_FAST_E_MEMORY);
    free(mem);

    s = new_session(&m, 16, NULL, NULL, SEDGE_FAST_EPOCHS);
    CHECK(sedge_fast_set_epochs(s, 0) == SEDGE_FAST_E_ARGUMENT);
    CHECK(sedge_fast_set_epochs(s, UINT64_C(1) << 40) == 0);
    /* Huge indices: 64-bit epoch arithmetic without 64-bit division. */
    CHECK(sedge_fast_decompress_indexed(s, (UINT64_C(1) << 40) * 3 + 1, out, 5, q) ==
          SEDGE_FAST_E_OUT_OF_SYNC);
    CHECK(sedge_fast_decompress_indexed(s, (UINT64_C(1) << 40) * 5, out, 5, q) == 0);
    CHECK(sedge_fast_count(s) == (UINT64_C(1) << 40) * 5 + 1);
    CHECK(sedge_fast_decompress_indexed(s, UINT64_MAX - 3, out, 5, q) == SEDGE_FAST_E_OUT_OF_SYNC);
    CHECK(sedge_fast_error_message(SEDGE_FAST_E_BUFFER)[0] != 'u');
    free(m);
}

/* A copy at another alignment continues exactly like the original. */
static void test_copy(void)
{
    size_t len = 90, i, cap = SEDGE_FAST_MAX_PAYLOAD(90), na, nb;
    uint8_t *ps = make_packets(400, len, 3), oa[SEDGE_FAST_MAX_PAYLOAD(90)],
            ob[SEDGE_FAST_MAX_PAYLOAD(90)];
    void *m;
    sedge_fast *a = new_session(&m, len, NULL, NULL, SEDGE_FAST_EPOCHS), *b;
    size_t bytes = sedge_fast_memory_bytes(len, NULL, SEDGE_FAST_EPOCHS);
    unsigned char *mb = malloc(bytes + 3);
    CHECK(sedge_fast_set_epochs(a, 50) == 0);
    for (i = 0; i < 120; i++) {
        CHECK(sedge_fast_compress(a, ps + i * len, oa, cap, &na) == 0);
    }
    CHECK(sedge_fast_copy(&b, mb + 3, bytes, a) == 0);
    for (; i < 400; i++) {
        CHECK(sedge_fast_compress(a, ps + i * len, oa, cap, &na) == 0);
        CHECK(sedge_fast_compress(b, ps + i * len, ob, cap, &nb) == 0);
        CHECK(na == nb && fnv(FNV_INIT, oa, na) == fnv(FNV_INIT, ob, nb));
    }
    free(m);
    free(mb);
    free(ps);
}

int main(void)
{
    test_roundtrips_and_compresses();
    test_random_and_extreme();
    test_garbage();
    test_lost_packet_epochs();
    test_learned_layouts();
    test_api_errors();
    test_copy();
    printf("largest payload: %.3f x packet length (bound 14 x + 8); "
           "bit-by-bit symbols: %lu\n", worst_ratio, sedge_fast_test_fallbacks);
    printf(failures ? "test_fast: %d FAILED\n" : "test_fast: OK\n", failures);
    return failures != 0;
}
