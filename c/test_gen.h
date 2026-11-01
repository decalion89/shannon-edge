/* Test helpers shared by the C tests: the packet generator of
 * tests/packet_fast.rs (xorshift64*) and FNV-1a-64. No C library needed;
 * 64-bit values are only shifted, xored and multiplied (no 64-bit
 * division, so freestanding 32-bit builds need no libgcc helper). */
#ifndef SEDGE_TEST_GEN_H
#define SEDGE_TEST_GEN_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint64_t rng;
    uint8_t temp;
    uint32_t i;
} gen_t;

static uint64_t rng_next(uint64_t *s)
{
    *s ^= *s >> 12;
    *s ^= *s << 25;
    *s ^= *s >> 27;
    return *s * UINT64_C(0x2545f4914f6cdd1d);
}

/* a % m for m < 2^16, with 32-bit divisions only. */
static uint32_t mod_small(uint64_t a, uint32_t m)
{
    uint32_t r = (uint32_t)(a >> 32) % m;
    r = ((r << 16) | (uint32_t)((a >> 16) & 0xffffu)) % m;
    return ((r << 16) | (uint32_t)(a & 0xffffu)) % m;
}

static void gen_init(gen_t *g, uint64_t seed)
{
    g->rng = seed;
    g->temp = 120u;
    g->i = 0u;
}

/* The Rust test's next housekeeping-like packet: header, counter, slow
 * field, noisy fields, constants. Any len >= 1. */
static void gen_packet(gen_t *g, uint8_t *p, size_t len)
{
    uint8_t head[9];
    size_t k;
    if (mod_small(rng_next(&g->rng), 20u) == 0u) {
        g->temp = (uint8_t)(g->temp + (uint8_t)mod_small(rng_next(&g->rng), 3u) - 1u);
    }
    head[0] = 0x08u;
    head[1] = 0x1fu;
    head[2] = (uint8_t)(g->i >> 8);
    head[3] = (uint8_t)g->i;
    head[4] = g->temp;
    for (k = 5; k < 9u; k++) {
        head[k] = (uint8_t)mod_small(rng_next(&g->rng), 4u);
    }
    for (k = 0; k < len; k++) {
        p[k] = k < 9u ? head[k] : (uint8_t)(k * 7u);
    }
    g->i++;
}

static uint64_t fnv(uint64_t h, const uint8_t *b, size_t n)
{
    size_t i;
    for (i = 0; i < n; i++) {
        h = (h ^ b[i]) * UINT64_C(0x100000001b3);
    }
    return h;
}

#define FNV_INIT UINT64_C(0xcbf29ce484222325)

#endif
