/* Golden values of the record transforms: the C port must transform
 * exactly as the Rust crate (src/fields.rs) does. The constants were
 * dumped by a Rust program built against the crate.
 *
 * 1. Three uplinks: the planted ECG-like records of tests/fields.rs learned
 *    with deltas; a hand-made one with every integer width, signedness and
 *    byte order, an opaque field (with a delta bit Rust drops), a = -128,
 *    b = 127 on 64-bit fields; INCART ECG (i16le*12) learned with deltas.
 *    1000 random records each, reset every 300: FNV-1a of the forward
 *    outputs. Every record is also inverted and compared.
 * 2. 20,000 corrupted uplinks (bit flips, bytes, truncation, appended
 *    bytes, small indices and counts, flag bytes): FNV-1a of each verdict,
 *    the re-serialised uplink and three forward outputs when accepted.
 *    This checks that C accepts exactly the uplinks Rust accepts.
 *
 * Builds hosted (stdio) or, with -DSEDGE_FREESTANDING, with no C library
 * (cross/start.c) for the qemu runs of make cross.
 */
#include "sedge_fields.h"

#ifdef SEDGE_FREESTANDING
void test_write(const char *s);
#else
#include <stdio.h>
static void test_write(const char *s) { fputs(s, stdout); }
#endif

static const uint8_t BASE1[40] = {
    0x53, 0x45, 0x44, 0x47, 0x52, 0x45, 0x4c, 0x31, 0x06, 0x00, 0x02, 0x0b,
    0x02, 0x0b, 0x02, 0x03, 0x02, 0x03, 0x02, 0x03, 0x04, 0x05, 0x02, 0x00,
    0x02, 0x00, 0x00, 0x00, 0x01, 0x00, 0xfe, 0x02, 0x03, 0x00, 0x00, 0x00,
    0x01, 0x00, 0xff, 0xff,
};
static const uint8_t BASE2[66] = {
    0x53, 0x45, 0x44, 0x47, 0x52, 0x45, 0x4c, 0x31, 0x0b, 0x00, 0x01, 0x09,
    0x01, 0x03, 0x02, 0x0d, 0x02, 0x0b, 0x04, 0x07, 0x04, 0x09, 0x03, 0x08,
    0x08, 0x0b, 0x08, 0x05, 0x08, 0x0f, 0x02, 0x0f, 0x04, 0x00, 0x09, 0x00,
    0x07, 0x00, 0x08, 0x00, 0x80, 0x7f, 0x02, 0x00, 0x00, 0x00, 0x01, 0x00,
    0x03, 0xfc, 0x04, 0x00, 0x05, 0x00, 0x07, 0x00, 0xff, 0xff, 0x03, 0x00,
    0x0a, 0x00, 0x00, 0x00, 0x02, 0x00,
};
static const uint8_t BASE3[60] = {
    0x53, 0x45, 0x44, 0x47, 0x52, 0x45, 0x4c, 0x31, 0x0c, 0x00, 0x02, 0x03,
    0x02, 0x0b, 0x02, 0x0b, 0x02, 0x03, 0x02, 0x03, 0x02, 0x0b, 0x02, 0x0b,
    0x02, 0x0b, 0x02, 0x0b, 0x02, 0x0b, 0x02, 0x0b, 0x02, 0x0b, 0x03, 0x00,
    0x00, 0x00, 0x01, 0x00, 0x02, 0x00, 0x02, 0xfe, 0x04, 0x00, 0x01, 0x00,
    0x02, 0x00, 0x01, 0xfe, 0x03, 0x00, 0x01, 0x00, 0x05, 0x00, 0xfd, 0x02,
};
#define GOLDEN_FWD_BYTES 81000u
#define GOLDEN_FWD_HASH UINT64_C(0xbbea1a422146836f)
#define GOLDEN_GARBAGE_OK 1149u
#define GOLDEN_GARBAGE_FWD 3447u
#define GOLDEN_GARBAGE_HASH UINT64_C(0x178ddd804ca480ff)

#define FNV_INIT UINT64_C(0xcbf29ce484222325)
#define MAX_BLOB 128u
#define MAX_REC 512u
/* A corrupted uplink of at most MAX_BLOB bytes has fewer than 64 fields and
 * 16 relations. */
#define MEM_MAX SEDGE_FIELDS_MEMORY_BYTES(64u, 16u, 64u * 255u)

static uint64_t mem_tx[MEM_MAX / 8u + 1u];
static uint64_t mem_rx[MEM_MAX / 8u + 1u];
static uint8_t rec[MAX_REC], fwd[MAX_REC], inv[MAX_REC];
static uint8_t blob[MAX_BLOB], ser[MAX_BLOB];
static int failures;

/* xorshift64* of tests/fields.rs. */
static uint64_t rng_next(uint64_t *s)
{
    *s ^= *s >> 12;
    *s ^= *s << 25;
    *s ^= *s >> 27;
    return *s * UINT64_C(0x2545f4914f6cdd1d);
}

/* rng % n without a 64-bit division helper on 32-bit targets: the values
 * here are small, so reduce by shift-subtract. */
static uint64_t umod(uint64_t a, uint64_t n)
{
    uint64_t d = n;
    int sh = 0;
    while (d <= (a >> 1) && sh < 63) {
        d <<= 1;
        sh++;
    }
    while (sh >= 0) {
        if (a >= d) {
            a -= d;
        }
        d >>= 1;
        sh--;
    }
    return a;
}

static uint64_t below(uint64_t *s, uint64_t n)
{
    return umod(rng_next(s), n);
}

static uint64_t fnv(uint64_t h, const uint8_t *b, size_t n)
{
    size_t i;
    for (i = 0; i < n; i++) {
        h = (h ^ b[i]) * UINT64_C(0x100000001b3);
    }
    return h;
}

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
        s[--i] = (char)('0' + (int)(v % 10u));
        v /= 10u;
    } while (v != 0u);
    test_write(s + i);
}

static void check(int ok, const char *what)
{
    if (!ok) {
        failures++;
        test_write("FAIL: ");
        test_write(what);
        test_write("\n");
    }
}

/* The corruption scheme of the Rust dumper (fieldsref mutate). */
static size_t mutate(uint64_t *s, uint8_t *b, size_t n)
{
    uint64_t k, m;
    size_t i;
    switch ((int)below(s, 7u)) {
    case 0:
        i = (size_t)below(s, n);
        b[i] = (uint8_t)(b[i] ^ (1u << below(s, 8u)));
        break;
    case 1:
        i = (size_t)below(s, n);
        b[i] = (uint8_t)(rng_next(s) & 0xffu);
        break;
    case 2:
        n = (size_t)below(s, n);
        break;
    case 3:
        m = 1u + below(s, 8u);
        for (k = 0; k < m; k++) {
            b[n++] = (uint8_t)(rng_next(s) & 0xffu);
        }
        break;
    case 4:
        if (n >= 10u) {
            uint32_t v;
            i = 8u + 2u * (size_t)below(s, (n - 8u) / 2u);
            v = (uint32_t)below(s, 24u);
            b[i] = (uint8_t)v;
            if (i + 1u < n) {
                b[i + 1u] = (uint8_t)(v >> 8);
            }
        }
        break;
    case 5:
        if (n >= 12u) {
            i = 11u + 2u * (size_t)below(s, (n - 10u) / 2u);
            if (i < n) {
                b[i] = (uint8_t)below(s, 32u);
            }
        }
        break;
    default:
        for (k = 0; k < 2u; k++) {
            i = (size_t)below(s, n);
            b[i] = (uint8_t)(b[i] ^ (1u << below(s, 8u)));
        }
        break;
    }
    return n;
}

static const uint8_t *const BASES[3] = {BASE1, BASE2, BASE3};
static const size_t BASE_LEN[3] = {sizeof BASE1, sizeof BASE2, sizeof BASE3};

static void golden_forward(void)
{
    uint64_t s = 2026u, h = FNV_INIT;
    uint32_t total = 0;
    int b, n;
    size_t i, len, sl;
    sedge_fields *tx, *rx;
    for (b = 0; b < 3; b++) {
        check(sedge_fields_init(&tx, mem_tx, sizeof mem_tx, BASES[b], BASE_LEN[b]) == 0, "init tx");
        check(sedge_fields_init(&rx, mem_rx, sizeof mem_rx, BASES[b], BASE_LEN[b]) == 0, "init rx");
        if (tx == NULL || rx == NULL) {
            return;
        }
        len = sedge_fields_record_len(tx);
        /* BASE2 has a delta bit on an opaque field, which Rust drops. */
        check(sedge_fields_to_bytes(tx, ser, sizeof ser, &sl) == 0 && sl == BASE_LEN[b], "to_bytes");
        for (i = 0; i < sl; i++) {
            check(ser[i] == BASES[b][i] || (b == 1 && i == 23u && ser[i] == 0u), "to_bytes bytes");
        }
        for (n = 0; n < 1000; n++) {
            if (n > 0 && n % 300 == 0) {
                sedge_fields_reset(tx);
                sedge_fields_reset(rx);
            }
            for (i = 0; i < len; i++) {
                rec[i] = (uint8_t)(rng_next(&s) & 0xffu);
            }
            check(sedge_fields_forward(tx, rec, len, fwd) == 0, "forward");
            check(sedge_fields_inverse(rx, fwd, len, inv) == 0, "inverse");
            for (i = 0; i < len; i++) {
                if (inv[i] != rec[i]) {
                    check(0, "inverse restores the record");
                    break;
                }
            }
            h = fnv(h, fwd, len);
            total += (uint32_t)len;
        }
    }
    test_write("forward: ");
    write_dec(total);
    test_write(" bytes, FNV-1a ");
    write_hex(h);
    check(total == GOLDEN_FWD_BYTES && h == GOLDEN_FWD_HASH, "forward golden hash");
    test_write(h == GOLDEN_FWD_HASH ? " (match)\n" : " (MISMATCH)\n");
}

static void golden_garbage(void)
{
    uint64_t s = 77u, h = FNV_INIT, nm, m;
    uint32_t ok = 0, nfwd = 0, it;
    size_t n, i, len, sl;
    sedge_fields *tx;
    uint8_t v;
    for (it = 0; it < 20000u; it++) {
        n = BASE_LEN[it % 3u];
        for (i = 0; i < n; i++) {
            blob[i] = BASES[it % 3u][i];
        }
        nm = 1u + below(&s, 3u);
        for (m = 0; m < nm && n > 0u; m++) {
            n = mutate(&s, blob, n);
        }
        if (sedge_fields_init(&tx, mem_tx, sizeof mem_tx, blob, n) != 0) {
            check(tx == NULL, "rejected leaves no handle");
            v = 0;
            h = fnv(h, &v, 1u);
            continue;
        }
        ok++;
        v = 1;
        h = fnv(h, &v, 1u);
        check(sedge_fields_to_bytes(tx, ser, sizeof ser, &sl) == 0, "garbage to_bytes");
        h = fnv(h, ser, sl);
        len = sedge_fields_record_len(tx);
        if (len <= MAX_REC) {
            for (m = 0; m < 3u; m++) {
                for (i = 0; i < len; i++) {
                    rec[i] = (uint8_t)(rng_next(&s) & 0xffu);
                }
                check(sedge_fields_forward(tx, rec, len, fwd) == 0, "garbage forward");
                h = fnv(h, fwd, len);
                nfwd++;
            }
        }
    }
    test_write("corrupted uplinks: 20000, accepted ");
    write_dec(ok);
    test_write(", forwards ");
    write_dec(nfwd);
    test_write(", FNV-1a ");
    write_hex(h);
    check(ok == GOLDEN_GARBAGE_OK && nfwd == GOLDEN_GARBAGE_FWD && h == GOLDEN_GARBAGE_HASH,
          "garbage golden hash");
    test_write(h == GOLDEN_GARBAGE_HASH ? " (match)\n" : " (MISMATCH)\n");
}

#ifdef SEDGE_FREESTANDING
int test_golden_main(void)
#else
int main(void)
#endif
{
    golden_forward();
    golden_garbage();
    if (failures != 0) {
        test_write("test_fields_golden: FAILED\n");
        return 1;
    }
    test_write("test_fields_golden: all passed\n");
    return 0;
}
