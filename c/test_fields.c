/* Unit and fuzz tests of the record transforms (sedge_fields).
 *
 * - hand-computed values: floor of negative relations, zigzag deltas,
 *   wraps at every width, big-endian fields, reset;
 * - every rejection rule of Rust from_bytes, one uplink each;
 * - argument, memory and buffer errors; alignment; in-place calls; a
 *   failed load invalidates the old handle in the same block;
 * - fuzz: random and corrupted SEDGREL1 uplinks. Each must be rejected, or
 *   load into a transform that re-serialises canonically and whose inverse
 *   restores random records (with deltas and resets). The verdict is also
 *   compared with an independent, straightforward reading of the Rust
 *   rules (ref_valid below).
 */
#include "sedge_fields.h"

#include <stdio.h>
#include <string.h>

static int failures, checks;

#define CHECK(c)                                                           \
    do {                                                                   \
        checks++;                                                          \
        if (!(c)) {                                                        \
            failures++;                                                    \
            if (failures < 20) {                                           \
                printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c);        \
            }                                                              \
        }                                                                  \
    } while (0)

#define MEM_MAX SEDGE_FIELDS_MEMORY_BYTES(128u, 128u, 128u * 255u)
static uint64_t mem1[MEM_MAX / 8u + 2u], mem2[MEM_MAX / 8u + 2u];

static uint64_t rng_state = 12345u;
static uint64_t rnd(void)
{
    rng_state ^= rng_state >> 12;
    rng_state ^= rng_state << 25;
    rng_state ^= rng_state >> 27;
    return rng_state * UINT64_C(0x2545f4914f6cdd1d);
}
static uint32_t rnd_below(uint32_t n)
{
    return (uint32_t)((rnd() >> 32) % n);
}

/* ------------------------------------------------------- uplink builder */

typedef struct {
    uint8_t b[1024];
    size_t n;
} blob;

static void begin(blob *u, uint32_t nf)
{
    memcpy(u->b, "SEDGREL1", 8);
    u->b[8] = (uint8_t)(nf & 0xffu);
    u->b[9] = (uint8_t)(nf >> 8);
    u->n = 10;
}
static void field(blob *u, uint32_t w, uint32_t fl)
{
    u->b[u->n++] = (uint8_t)w;
    u->b[u->n++] = (uint8_t)fl;
}
static void put16(blob *u, uint32_t v)
{
    u->b[u->n++] = (uint8_t)(v & 0xffu);
    u->b[u->n++] = (uint8_t)(v >> 8);
}
static void rel(blob *u, uint32_t t, uint32_t i, uint32_t j, int a, int b)
{
    put16(u, t);
    put16(u, i);
    put16(u, j);
    u->b[u->n++] = (uint8_t)(a & 0xff);
    u->b[u->n++] = (uint8_t)(b & 0xff);
}

#define I 1u  /* integer */
#define S 2u  /* signed */
#define BE 4u /* big-endian */
#define D 8u  /* delta */

static int load(sedge_fields **t, void *mem, const blob *u)
{
    return sedge_fields_init(t, mem, sizeof mem1, u->b, u->n);
}

/* ------------------------------------------------------------- reference */

/* The Rust from_bytes rules, written as plainly as possible (quadratic). */
static int ref_valid(const uint8_t *b, size_t n)
{
    size_t at = 10, nf, nr, k, q;
    uint8_t integer[70000 / 8 + 1];
    if (n < 10u || memcmp(b, "SEDGREL1", 8) != 0) {
        return 0;
    }
    nf = (size_t)b[8] | ((size_t)b[9] << 8);
    memset(integer, 0, sizeof integer);
    for (k = 0; k < nf; k++) {
        unsigned w, fl;
        if (at + 2u > n) {
            return 0;
        }
        w = b[at];
        fl = b[at + 1u];
        at += 2;
        if (w == 0u || ((fl & 1u) && w != 1u && w != 2u && w != 4u && w != 8u) || fl >> 4) {
            return 0;
        }
        if (fl & 1u) {
            integer[k / 8u] = (uint8_t)(integer[k / 8u] | (1u << (k % 8u)));
        }
    }
    if (nf == 0u || at + 2u > n) {
        return 0;
    }
    nr = (size_t)b[at] | ((size_t)b[at + 1u] << 8);
    at += 2;
    if (n != at + 8u * nr) {
        return 0;
    }
#define U16(p) ((size_t)b[p] | ((size_t)b[(p) + 1u] << 8))
#define INT(x) ((x) < nf && (((unsigned)integer[(x) / 8u] >> ((x) % 8u)) & 1u))
    for (k = 0; k < nr; k++) {
        size_t t = U16(at + 8u * k), i = U16(at + 8u * k + 2u), j = U16(at + 8u * k + 4u);
        if (!INT(t) || !INT(i) || !INT(j) || t == i || t == j) {
            return 0;
        }
        for (q = 0; q < nr; q++) {
            size_t t2 = U16(at + 8u * q);
            if (q < k && t2 == t) {
                return 0; /* target used twice */
            }
            if (t2 == i || t2 == j) {
                return 0; /* a predictor is a target */
            }
        }
    }
#undef U16
#undef INT
    return 1;
}

/* ---------------------------------------------------------- unit tests */

static uint64_t get_le(const uint8_t *p, int w)
{
    uint64_t v = 0;
    while (w-- > 0) {
        v = (v << 8) | p[w];
    }
    return v;
}

static void test_values(void)
{
    blob u;
    sedge_fields *t, *r;
    uint8_t rec[16], out[16], back[16];
    sedge_fields_field f;
    sedge_fields_relation rl;

    /* i16le x0, x1, x2 with x2 = floor((x0 + x1) / 2) + r */
    begin(&u, 3);
    field(&u, 2, I | S);
    field(&u, 2, I | S);
    field(&u, 2, I | S);
    put16(&u, 1);
    rel(&u, 2, 0, 1, 1, 1);
    CHECK(load(&t, mem1, &u) == 0);
    CHECK(load(&r, mem2, &u) == 0);
    /* x0 = -3, x1 = 0, x2 = 5: pred = floor(-3 / 2) = -2, r = 7 */
    rec[0] = 0xfd; rec[1] = 0xff; rec[2] = 0; rec[3] = 0; rec[4] = 5; rec[5] = 0;
    CHECK(sedge_fields_forward(t, rec, 6, out) == 0);
    CHECK(out[4] == 7 && out[5] == 0 && memcmp(out, rec, 4) == 0);
    CHECK(sedge_fields_inverse(r, out, 6, back) == 0 && memcmp(back, rec, 6) == 0);
    /* x0 = x1 = -32768, x2 = 32767: pred = -32768, r = 65535 mod 2^16 */
    rec[0] = 0; rec[1] = 0x80; rec[2] = 0; rec[3] = 0x80; rec[4] = 0xff; rec[5] = 0x7f;
    CHECK(sedge_fields_forward(t, rec, 6, out) == 0 && out[4] == 0xff && out[5] == 0xff);
    CHECK(sedge_fields_inverse(r, out, 6, back) == 0 && memcmp(back, rec, 6) == 0);
    CHECK(sedge_fields_get_relation(t, 0, &rl) == 0 && rl.target == 2 && rl.i == 0 && rl.j == 1 &&
          rl.a == 1 && rl.b == 1);
    CHECK(sedge_fields_get_field(t, 2, &f) == 0 && f.offset == 4 && f.width == 2 && f.integer &&
          f.is_signed && !f.big_endian && !f.delta);
    CHECK(sedge_fields_get_relation(t, 1, &rl) == SEDGE_FIELDS_E_ARGUMENT);
    CHECK(sedge_fields_get_field(t, 3, &f) == SEDGE_FIELDS_E_ARGUMENT);

    /* Unsigned: a = -128, b = 127 on u8 fields, u32be target. */
    begin(&u, 3);
    field(&u, 1, I);
    field(&u, 1, I);
    field(&u, 4, I | BE);
    put16(&u, 1);
    rel(&u, 2, 0, 1, -128, 127);
    CHECK(load(&t, mem1, &u) == 0);
    rec[0] = 255; rec[1] = 3; rec[2] = 0; rec[3] = 0; rec[4] = 0; rec[5] = 0;
    /* pred = floor((-128 * 255 + 127 * 3) / 2) = floor(-32259 / 2) = -16130;
     * r = 0 + 16130 = 0x00003f02, big-endian */
    CHECK(sedge_fields_forward(t, rec, 6, out) == 0);
    CHECK(out[2] == 0 && out[3] == 0 && out[4] == 0x3f && out[5] == 0x02);
    CHECK(sedge_fields_get_relation(t, 0, &rl) == 0 && rl.a == -128 && rl.b == 127);

    /* Deltas: u8 and i64be fields, zigzag of the difference. */
    begin(&u, 2);
    field(&u, 1, I | D);
    field(&u, 8, I | S | BE | D);
    put16(&u, 0);
    CHECK(load(&t, mem1, &u) == 0);
    CHECK(load(&r, mem2, &u) == 0);
    {
        static const uint8_t v8[5] = {250, 3, 3, 0, 255};
        static const uint64_t v64[5] = {5u, 10u, 4u, UINT64_C(0x8000000000000000), 0u};
        /* expected forward: first unchanged; u8: 3-250 = 9 -> 18, 0 -> 0,
         * -3 -> 5, -1 -> 1; i64: 5 -> 10, -6 -> 11, 2^63 - 4 -> 2^64 - 8,
         * 2^63 -> 2^64 - 1 (zigzag of -2^63) */
        static const uint8_t e8[5] = {250, 18, 0, 5, 1};
        static const uint64_t e64[5] = {5u, 10u, 11u, UINT64_C(0xfffffffffffffff8),
                                        UINT64_C(0xffffffffffffffff)};
        int k, q;
        for (k = 0; k < 5; k++) {
            uint64_t got = 0;
            rec[0] = v8[k];
            for (q = 0; q < 8; q++) {
                rec[1 + q] = (uint8_t)(v64[k] >> (56 - 8 * q));
            }
            CHECK(sedge_fields_forward(t, rec, 9, out) == 0);
            for (q = 0; q < 8; q++) {
                got = (got << 8) | out[1 + q];
            }
            CHECK(out[0] == e8[k] && got == e64[k]);
            CHECK(sedge_fields_inverse(r, out, 9, back) == 0 && memcmp(back, rec, 9) == 0);
        }
        /* reset: the next record is sent unchanged */
        sedge_fields_reset(t);
        sedge_fields_reset(r);
        rec[0] = 77;
        CHECK(sedge_fields_forward(t, rec, 9, out) == 0 && memcmp(out, rec, 9) == 0);
        CHECK(sedge_fields_inverse(r, out, 9, back) == 0 && memcmp(back, rec, 9) == 0);
        /* only one side reset: the other still deltas */
        sedge_fields_reset(t);
        CHECK(sedge_fields_forward(t, rec, 9, out) == 0 && memcmp(out, rec, 9) == 0);
        CHECK(sedge_fields_inverse(r, out, 9, back) == 0 && memcmp(back, rec, 9) != 0);
    }

    /* Signed 32-bit relation wraps like Rust i64 then masks. */
    begin(&u, 3);
    field(&u, 4, I | S);
    field(&u, 4, I);
    field(&u, 4, I | S | D);
    put16(&u, 1);
    rel(&u, 2, 0, 1, 4, -4);
    CHECK(load(&t, mem1, &u) == 0);
    memset(rec, 0, sizeof rec);
    rec[3] = 0x80;                                   /* x0 = -2^31 */
    rec[4] = rec[5] = rec[6] = rec[7] = 0xff;        /* x1 = 2^32 - 1 (unsigned) */
    rec[8] = 1;                                      /* x2 = 1 */
    /* pred = floor((4 * -2^31 - 4 * (2^32 - 1)) / 2) = -3 * 2^32 + 2;
     * r = 1 - pred mod 2^32 = 0xffffffff */
    CHECK(sedge_fields_forward(t, rec, 12, out) == 0 && get_le(out + 8, 4) == 0xffffffffu);
}

static void test_rejects(void)
{
    blob u, v;
    sedge_fields *t;
    size_t k;
    /* a valid base: i16le, u8, b3, i32be(delta) */
    begin(&v, 4);
    field(&v, 2, I | S);
    field(&v, 1, I);
    field(&v, 3, 0);
    field(&v, 4, I | S | BE | D);
    put16(&v, 1);
    rel(&v, 3, 0, 1, 2, -1);
    CHECK(load(&t, mem1, &v) == 0 && ref_valid(v.b, v.n));

    CHECK(sedge_fields_init(&t, mem1, sizeof mem1, NULL, 0) == SEDGE_FIELDS_E_BAD_MODEL && !t);
    CHECK(sedge_fields_init(&t, mem1, sizeof mem1, (const uint8_t *)"SEDGREL1", 8) ==
          SEDGE_FIELDS_E_BAD_MODEL);
    u = v; u.b[7] = '2';                       /* magic */
    CHECK(load(&t, mem1, &u) == SEDGE_FIELDS_E_BAD_MODEL);
    begin(&u, 0); put16(&u, 0);                /* no fields */
    CHECK(load(&t, mem1, &u) == SEDGE_FIELDS_E_BAD_MODEL && !ref_valid(u.b, u.n));
    u = v; u.b[14] = 0;                        /* width 0 (opaque) */
    CHECK(load(&t, mem1, &u) == SEDGE_FIELDS_E_BAD_MODEL);
    u = v; u.b[16] = 3; u.b[17] = I;           /* integer width 3 */
    CHECK(load(&t, mem1, &u) == SEDGE_FIELDS_E_BAD_MODEL);
    u = v; u.b[16] = 16;                       /* integer width 16 */
    u.b[17] = I;
    CHECK(load(&t, mem1, &u) == SEDGE_FIELDS_E_BAD_MODEL);
    u = v; u.b[17] = 0x10;                     /* flag bit 4 */
    CHECK(load(&t, mem1, &u) == SEDGE_FIELDS_E_BAD_MODEL);
    u = v; u.b[11] = 0x80 | I;                 /* flag bit 7 */
    CHECK(load(&t, mem1, &u) == SEDGE_FIELDS_E_BAD_MODEL);
    for (k = 0; k < v.n; k++) {                /* every truncation */
        CHECK(sedge_fields_init(&t, mem1, sizeof mem1, v.b, k) == SEDGE_FIELDS_E_BAD_MODEL);
    }
    u = v; u.b[u.n++] = 0;                     /* trailing byte */
    CHECK(load(&t, mem1, &u) == SEDGE_FIELDS_E_BAD_MODEL);
    u = v; u.b[18] = 2;                        /* relation count too high */
    CHECK(load(&t, mem1, &u) == SEDGE_FIELDS_E_BAD_MODEL);
    u = v; u.b[8] = 5;                         /* field count too high */
    CHECK(load(&t, mem1, &u) == SEDGE_FIELDS_E_BAD_MODEL);

    /* relations: indices out of range, opaque fields, t == i or j */
    {
        static const int bad[][3] = {{4, 0, 1}, {3, 4, 1}, {3, 0, 4}, {3, 0x100, 1}, {2, 0, 1},
                                     {3, 2, 1}, {3, 0, 2}, {3, 3, 1}, {3, 0, 3}, {0xffff, 0, 1}};
        for (k = 0; k < sizeof bad / sizeof bad[0]; k++) {
            u = v;
            u.n -= 8;
            rel(&u, (uint32_t)bad[k][0], (uint32_t)bad[k][1], (uint32_t)bad[k][2], 1, 1);
            CHECK(load(&t, mem1, &u) == SEDGE_FIELDS_E_BAD_MODEL && !ref_valid(u.b, u.n));
        }
    }
    /* target used twice */
    u = v; u.b[18] = 2; rel(&u, 3, 1, 0, 1, 1);
    CHECK(load(&t, mem1, &u) == SEDGE_FIELDS_E_BAD_MODEL && !ref_valid(u.b, u.n));
    /* a target as predictor, before and after its own relation */
    u = v; u.b[18] = 2; rel(&u, 0, 3, 1, 1, 1);
    CHECK(load(&t, mem1, &u) == SEDGE_FIELDS_E_BAD_MODEL && !ref_valid(u.b, u.n));
    u = v; u.n -= 8; u.b[18] = 2; rel(&u, 0, 1, 1, 1, 1); rel(&u, 3, 0, 1, 1, 1);
    CHECK(load(&t, mem1, &u) == SEDGE_FIELDS_E_BAD_MODEL && !ref_valid(u.b, u.n));

    /* accepted: i == j, a == b == 0, opaque with signed/BE/delta bits */
    u = v; u.n -= 8; rel(&u, 3, 1, 1, 0, 0);
    CHECK(load(&t, mem1, &u) == 0 && ref_valid(u.b, u.n));
    u = v; u.b[15] = BE | S | D;
    CHECK(load(&t, mem1, &u) == 0 && ref_valid(u.b, u.n));
    {
        uint8_t ser[64];
        size_t n;
        sedge_fields_field f;
        CHECK(sedge_fields_to_bytes(t, ser, sizeof ser, &n) == 0 && n == u.n);
        CHECK(ser[15] == (BE | S) && memcmp(ser, u.b, 15) == 0 &&
              memcmp(ser + 16, u.b + 16, n - 16) == 0);
        CHECK(sedge_fields_get_field(t, 2, &f) == 0 && !f.integer && f.is_signed && f.big_endian &&
              !f.delta && f.width == 3 && f.offset == 3);
    }
    /* the widest opaque fields: 255 bytes */
    begin(&u, 4);
    field(&u, 255, 0);
    field(&u, 255, S | BE);
    field(&u, 8, I | D);
    field(&u, 255, 0);
    put16(&u, 0);
    CHECK(load(&t, mem1, &u) == 0 && sedge_fields_record_len(t) == 773u);
}

static void test_api(void)
{
    blob v;
    sedge_fields *t, *t2;
    uint8_t rec[16], out[16], buf[64];
    size_t n, need, a;
    begin(&v, 2);
    field(&v, 2, I | D);
    field(&v, 2, I | S | BE);
    put16(&v, 1);
    rel(&v, 0, 1, 1, 3, -1);
    need = sedge_fields_memory_bytes(v.b, v.n);
    CHECK(need == SEDGE_FIELDS_MEMORY_BYTES(2, 1, 4));
    CHECK(sedge_fields_memory_bytes(v.b, v.n - 1) == 0 && sedge_fields_memory_bytes(NULL, 0) == 0);
    CHECK(sedge_fields_init(NULL, mem1, sizeof mem1, v.b, v.n) == SEDGE_FIELDS_E_ARGUMENT);
    CHECK(sedge_fields_init(&t, NULL, sizeof mem1, v.b, v.n) == SEDGE_FIELDS_E_ARGUMENT && !t);
    CHECK(sedge_fields_init(&t, mem1, sizeof mem1, NULL, 5) == SEDGE_FIELDS_E_ARGUMENT);
    for (a = 0; a < 8; a++) {
        CHECK(sedge_fields_init(&t, (uint8_t *)mem1 + a, need - 1, v.b, v.n) == SEDGE_FIELDS_E_MEMORY);
        CHECK(sedge_fields_init(&t, (uint8_t *)mem1 + a, need, v.b, v.n) == 0 && t != NULL);
        CHECK(((uintptr_t)t & 7u) == 0);
    }
    CHECK(sedge_fields_record_len(t) == 4 && sedge_fields_field_count(t) == 2 &&
          sedge_fields_relation_count(t) == 1);
    CHECK(sedge_fields_forward(t, rec, 3, out) == SEDGE_FIELDS_E_ARGUMENT);
    CHECK(sedge_fields_forward(t, rec, 5, out) == SEDGE_FIELDS_E_ARGUMENT);
    CHECK(sedge_fields_forward(t, NULL, 4, out) == SEDGE_FIELDS_E_ARGUMENT);
    CHECK(sedge_fields_inverse(t, rec, 4, NULL) == SEDGE_FIELDS_E_ARGUMENT);
    CHECK(sedge_fields_forward(NULL, rec, 4, out) == SEDGE_FIELDS_E_ARGUMENT);
    CHECK(sedge_fields_to_bytes(t, buf, v.n - 1, &n) == SEDGE_FIELDS_E_BUFFER && n == v.n);
    CHECK(sedge_fields_to_bytes(t, NULL, 0, &n) == SEDGE_FIELDS_E_BUFFER && n == v.n);
    CHECK(sedge_fields_to_bytes(t, NULL, 5, &n) == SEDGE_FIELDS_E_ARGUMENT);
    CHECK(sedge_fields_to_bytes(t, buf, sizeof buf, NULL) == SEDGE_FIELDS_E_ARGUMENT);
    CHECK(sedge_fields_to_bytes(t, buf, sizeof buf, &n) == 0 && n == v.n && memcmp(buf, v.b, n) == 0);
    CHECK(sedge_fields_record_len(NULL) == 0 && sedge_fields_field_count(NULL) == 0);
    sedge_fields_reset(NULL);
    /* A failed load in the same block invalidates the old handle. */
    v.b[v.n - 4] = 9;
    CHECK(sedge_fields_init(&t2, (uint8_t *)mem1 + 7, need, v.b, v.n) == SEDGE_FIELDS_E_BAD_MODEL);
    CHECK(sedge_fields_forward(t, rec, 4, out) == SEDGE_FIELDS_E_ARGUMENT);
    CHECK(sedge_fields_record_len(t) == 0);
    /* Never-initialised block. */
    memset(mem2, 0xa5, 64);
    CHECK(sedge_fields_record_len((const sedge_fields *)(const void *)mem2) == 0);
    CHECK(sedge_fields_error_message(SEDGE_FIELDS_E_BAD_MODEL)[0] != 'u' &&
          sedge_fields_error_message(12345)[0] == 'u');
}

/* ---------------------------------------------------------------- fuzz */

static uint8_t recs[8][2048], fwd[2048], tmp[2048];
static unsigned long fz_total, fz_accepted, fz_records, fz_relations, fz_deltas;

/* An accepted transform must re-serialise canonically and invert itself. */
static void exercise(const uint8_t *b, size_t n, size_t skew)
{
    sedge_fields *tx, *rx, *t3;
    uint8_t ser[1024], ser2[1024];
    size_t sl, sl2, len, k, q, off = 0;
    int ok = sedge_fields_init(&tx, (uint8_t *)mem1 + skew, sizeof mem1 - 8, b, n);
    int want = ref_valid(b, n);
    fz_total++;
    CHECK((ok == 0) == (want != 0));
    if (ok != 0) {
        CHECK(ok == SEDGE_FIELDS_E_BAD_MODEL && tx == NULL);
        return;
    }
    fz_accepted++;
    CHECK(sedge_fields_memory_bytes(b, n) ==
          SEDGE_FIELDS_MEMORY_BYTES(sedge_fields_field_count(tx), sedge_fields_relation_count(tx),
                                    sedge_fields_record_len(tx)));
    /* to_bytes: the uplink itself, except delta bits of opaque fields */
    CHECK(sedge_fields_to_bytes(tx, ser, sizeof ser, &sl) == 0 && sl == n);
    for (k = 0; k < sl; k++) {
        int is_flag = k >= 11u && k < 10u + 2u * sedge_fields_field_count(tx) && (k & 1u);
        CHECK(ser[k] == b[k] || (is_flag && !(b[k] & 1u) && ser[k] == (b[k] & 7u)));
    }
    /* reload: identical, and a fixed point */
    CHECK(sedge_fields_init(&t3, mem2, sizeof mem2, ser, sl) == 0);
    CHECK(sedge_fields_to_bytes(t3, ser2, sizeof ser2, &sl2) == 0 && sl2 == sl &&
          memcmp(ser, ser2, sl) == 0);
    CHECK(sedge_fields_init(&rx, (uint8_t *)mem2 + (7 - skew), sizeof mem2 - 8, b, n) == 0);
    /* fields tile the record; relations obey the rules */
    for (k = 0; k < sedge_fields_field_count(tx); k++) {
        sedge_fields_field f;
        CHECK(sedge_fields_get_field(tx, k, &f) == 0 && f.offset == off);
        off += f.width;
        fz_deltas += (unsigned long)f.delta;
    }
    len = sedge_fields_record_len(tx);
    CHECK(off == len);
    fz_relations += sedge_fields_relation_count(tx);
    if (len > sizeof fwd) {
        return;
    }
    /* records: random, slowly varying and all-ones, with resets */
    for (q = 0; q < 24u; q++) {
        uint8_t *r = recs[q % 8u];
        int mode = (int)(q / 8u);
        for (k = 0; k < len; k++) {
            r[k] = mode == 0 ? (uint8_t)rnd() : mode == 1 ? (uint8_t)(r[k] + (rnd() & 3u)) : 0xff;
        }
        if (q == 13u) {
            sedge_fields_reset(tx);
            sedge_fields_reset(rx);
        }
        CHECK(sedge_fields_forward(tx, r, len, fwd) == 0);
        memcpy(tmp, fwd, len);
        CHECK(sedge_fields_inverse(rx, tmp, len, tmp) == 0); /* in place */
        CHECK(memcmp(tmp, r, len) == 0);
        fz_records++;
    }
}

static void corrupt(uint8_t *b, size_t *n)
{
    size_t i;
    switch (rnd_below(8)) {
    case 0:
        i = rnd_below((uint32_t)*n);
        b[i] ^= (uint8_t)(1u << rnd_below(8));
        break;
    case 1:
        i = rnd_below((uint32_t)*n);
        b[i] = (uint8_t)rnd();
        break;
    case 2:
        *n = rnd_below((uint32_t)*n);
        break;
    case 3:
        if (*n < 900) {
            b[(*n)++] = (uint8_t)rnd();
        }
        break;
    case 4: /* a small value into a 16-bit slot */
        if (*n >= 12) {
            i = 8 + 2 * rnd_below((uint32_t)(*n - 8) / 2);
            b[i] = (uint8_t)rnd_below(12);
            b[i + 1] = 0;
        }
        break;
    case 5: /* swap two 16-bit slots */
        if (*n >= 14) {
            size_t j = 8 + 2 * rnd_below((uint32_t)(*n - 8) / 2);
            uint8_t x0, x1;
            i = 8 + 2 * rnd_below((uint32_t)(*n - 8) / 2);
            x0 = b[i];
            x1 = b[i + 1];
            b[i] = b[j];
            b[i + 1] = b[j + 1];
            b[j] = x0;
            b[j + 1] = x1;
        }
        break;
    case 6: /* drop or repeat a relation-sized tail */
        if (*n >= 20 && rnd_below(2)) {
            *n -= 8;
        } else if (*n >= 8 && *n < 900) {
            memcpy(b + *n, b + *n - 8, 8);
            *n += 8;
        }
        break;
    default: /* a flags byte */
        if (*n >= 12) {
            i = 11 + 2 * rnd_below((uint32_t)(*n - 10) / 2);
            if (i < *n) {
                b[i] = (uint8_t)rnd_below(32);
            }
        }
        break;
    }
}

/* A random uplink of consistent length: few fields, random widths and
 * flags, random relations among small indices. Often valid. */
static void random_uplink(blob *u)
{
    static const uint32_t widths[] = {1, 2, 4, 8, 1, 2, 4, 8, 3, 0, 5, 16, 255};
    uint32_t nf = 1 + rnd_below(8), nr = rnd_below(5), k;
    if (rnd_below(50) == 0) {
        nf = rnd_below(64);
    }
    begin(u, nf);
    for (k = 0; k < nf; k++) {
        uint32_t fl = rnd_below(4) ? (I | (rnd_below(16) & ~I)) : rnd_below(16);
        if (rnd_below(40) == 0) {
            fl |= 16u << rnd_below(4);
        }
        field(u, widths[rnd_below(rnd_below(10) ? 8 : 13)], fl);
    }
    put16(u, nr);
    for (k = 0; k < nr; k++) {
        uint32_t m = nf + (rnd_below(10) == 0);
        /* one call per statement: argument order is unspecified */
        uint32_t t = rnd_below(m ? m : 1), i = rnd_below(m ? m : 1), j = rnd_below(m ? m : 1);
        int a = (int)rnd_below(256), b = (int)rnd_below(256);
        rel(u, t, i, j, a, b);
    }
}

static void test_fuzz(void)
{
    blob u, base[3];
    uint32_t it, k;
    size_t n;
    /* three valid bases to corrupt */
    begin(&base[0], 6);
    field(&base[0], 2, I | S | D);
    field(&base[0], 2, I | S | D);
    field(&base[0], 2, I | S);
    field(&base[0], 2, I | S);
    field(&base[0], 2, I | S);
    field(&base[0], 4, I | BE);
    put16(&base[0], 2);
    rel(&base[0], 2, 0, 1, -2, 2);
    rel(&base[0], 3, 0, 1, -1, -1);
    begin(&base[1], 9);
    field(&base[1], 1, I);
    field(&base[1], 1, I | S | D);
    field(&base[1], 2, I | BE | D);
    field(&base[1], 4, I | S);
    field(&base[1], 8, I | S | BE | D);
    field(&base[1], 8, I);
    field(&base[1], 7, 0);
    field(&base[1], 4, I | S | BE | D);
    field(&base[1], 2, I | S);
    put16(&base[1], 4);
    rel(&base[1], 4, 5, 1, -128, 127);
    rel(&base[1], 0, 1, 1, 3, 0);
    rel(&base[1], 7, 8, 2, 1, -3);
    rel(&base[1], 3, 2, 8, 4, 4);
    begin(&base[2], 1);
    field(&base[2], 8, I | S | D);
    put16(&base[2], 0);
    for (k = 0; k < 3; k++) {
        CHECK(ref_valid(base[k].b, base[k].n));
        exercise(base[k].b, base[k].n, k);
    }
    for (it = 0; it < 300000u; it++) {
        switch (it % 3u) {
        case 0: /* corrupted valid uplink */
            u = base[rnd_below(3)];
            for (k = 1 + rnd_below(4); k > 0 && u.n > 0; k--) {
                corrupt(u.b, &u.n);
            }
            break;
        case 1: /* random structured uplink, maybe corrupted */
            random_uplink(&u);
            if (rnd_below(3) == 0 && u.n > 0) {
                corrupt(u.b, &u.n);
            }
            break;
        default: /* random bytes behind the magic */
            n = 8 + rnd_below(rnd_below(4) ? 40 : 200);
            memcpy(u.b, "SEDGREL1", 8);
            for (k = 8; k < n; k++) {
                u.b[k] = (uint8_t)rnd();
            }
            if (rnd_below(2)) {
                u.b[8] = (uint8_t)rnd_below(4);
                u.b[9] = 0;
            }
            if (rnd_below(16) == 0) {
                u.b[rnd_below(8)] ^= 0x20;
            }
            u.n = n;
            break;
        }
        exercise(u.b, u.n, it % 8u);
    }
    printf("fuzz: %lu uplinks, %lu accepted (%lu relations, %lu delta fields), %lu records inverted\n",
           fz_total, fz_accepted, fz_relations, fz_deltas, fz_records);
}

int main(void)
{
    test_values();
    test_rejects();
    test_api();
    test_fuzz();
    printf("test_fields: %d checks, %d failures\n", checks, failures);
    return failures != 0;
}
