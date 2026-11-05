/* Compare the C record transforms with Rust dumps (see README.md).
 *
 *   crosscheck_fields DATA UPLINK RUST_FWD [RESET]
 *       DATA: records back to back; UPLINK: Rust to_bytes(); RUST_FWD: the
 *       Rust forward() of every record (reset() every RESET records).
 *   crosscheck_fields --cases FILE
 *       Case file, per case (u32 little-endian):
 *         u32 n, uplink[n], u8 rust_ok,
 *         if rust_ok: u32 m, rust to_bytes[m], u32 len, u32 count, u32 reset,
 *                     records[count * len], rust forward[count * len]
 *
 * Checks: C accepts exactly the uplinks Rust accepts; C to_bytes equals
 * Rust's; every C forward equals Rust's; C inverse restores every record.
 */
#include "sedge_fields.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void die(const char *m)
{
    fprintf(stderr, "crosscheck_fields: %s\n", m);
    exit(2);
}

static void *xmalloc(size_t n)
{
    void *p = malloc(n ? n : 1u);
    if (p == NULL) {
        die("out of memory");
    }
    return p;
}

static uint8_t *read_file(const char *path, size_t *n)
{
    FILE *f = fopen(path, "rb");
    uint8_t *b;
    long sz = 0;
    if (f == NULL || fseek(f, 0, SEEK_END) != 0 || (sz = ftell(f)) < 0 ||
        fseek(f, 0, SEEK_SET) != 0) {
        die("cannot read file");
    }
    b = xmalloc((size_t)sz);
    if (fread(b, 1, (size_t)sz, f) != (size_t)sz) {
        die("short read");
    }
    fclose(f);
    *n = (size_t)sz;
    return b;
}

/* Load the same uplink twice (sender, receiver) in blocks shifted by `skew`
 * bytes to exercise any alignment. */
static int load(const uint8_t *up, size_t n, size_t skew, uint8_t **m1, uint8_t **m2,
                sedge_fields **tx, sedge_fields **rx)
{
    size_t need = sedge_fields_memory_bytes(up, n);
    int r1, r2;
    *m1 = xmalloc(need + 8u);
    *m2 = xmalloc(need + 8u);
    r1 = sedge_fields_init(tx, *m1 + skew, need, up, n);
    r2 = sedge_fields_init(rx, *m2 + (7u - skew), need, up, n);
    if (r1 != r2) {
        die("sender and receiver disagree");
    }
    if (r1 == SEDGE_FIELDS_OK && need == 0u) {
        die("accepted with memory_bytes 0");
    }
    return r1;
}

static int real(int argc, char **argv)
{
    size_t dn, un, fn, len, n, k, sl, reset;
    uint8_t *data = read_file(argv[1], &dn), *up = read_file(argv[2], &un),
            *rf = read_file(argv[3], &fn), *m1, *m2, *fwd, *inv, *ser;
    unsigned long long fwd_bad = 0, inv_bad = 0;
    sedge_fields *tx, *rx;
    reset = argc > 4 ? (size_t)strtoul(argv[4], NULL, 10) : 0u;
    if (load(up, un, 3u, &m1, &m2, &tx, &rx) != SEDGE_FIELDS_OK) {
        die("C rejects the Rust uplink");
    }
    len = sedge_fields_record_len(tx);
    n = dn / len;
    if (fn != n * len) {
        die("forward file length does not match the data");
    }
    ser = xmalloc(un);
    if (sedge_fields_to_bytes(tx, ser, un, &sl) != 0 || sl != un || memcmp(ser, up, un) != 0) {
        die("to_bytes differs from the Rust uplink");
    }
    fwd = xmalloc(len);
    inv = xmalloc(len);
    for (k = 0; k < n; k++) {
        if (reset != 0u && k > 0u && k % reset == 0u) {
            sedge_fields_reset(tx);
            sedge_fields_reset(rx);
        }
        if (sedge_fields_forward(tx, data + k * len, len, fwd) != 0 ||
            sedge_fields_inverse(rx, fwd, len, inv) != 0) {
            die("call failed");
        }
        if (memcmp(fwd, rf + k * len, len) != 0) {
            if (fwd_bad++ < 5u) {
                fprintf(stderr, "forward differs at record %zu\n", k);
            }
        }
        if (memcmp(inv, data + k * len, len) != 0) {
            if (inv_bad++ < 5u) {
                fprintf(stderr, "inverse differs at record %zu\n", k);
            }
        }
    }
    printf("%s: %zu records x %zu bytes, %zu fields, %zu relations, uplink %zu bytes\n",
           argv[1], n, len, sedge_fields_field_count(tx), sedge_fields_relation_count(tx), un);
    printf("  forward identical to Rust: %llu / %zu; inverse restores: %llu / %zu\n",
           (unsigned long long)n - fwd_bad, n, (unsigned long long)n - inv_bad, n);
    free(data);
    free(up);
    free(rf);
    free(m1);
    free(m2);
    free(fwd);
    free(inv);
    free(ser);
    return fwd_bad || inv_bad;
}

static const uint8_t *cur, *end;

static const uint8_t *take(size_t n)
{
    const uint8_t *p = cur;
    if ((size_t)(end - cur) < n) {
        die("truncated case file");
    }
    cur += n;
    return p;
}

static size_t u32_at(void)
{
    const uint8_t *p = take(4u);
    return (size_t)p[0] | ((size_t)p[1] << 8) | ((size_t)p[2] << 16) | ((size_t)p[3] << 24);
}

static int cases(const char *path)
{
    size_t fn, nc = 0, n, m, len, count, reset, k, sl;
    unsigned long long ok_cases = 0, verdict_bad = 0, ser_bad = 0, recs = 0, fwd_bad = 0,
                       inv_bad = 0, with_rel = 0, with_delta = 0;
    uint8_t *file = read_file(path, &fn), *m1, *m2, *fwd, *inv, *ser;
    sedge_fields *tx, *rx;
    cur = file;
    end = file + fn;
    while (cur < end) {
        const uint8_t *up, *tb, *in, *rf;
        int rust_ok, c;
        n = u32_at();
        up = take(n);
        rust_ok = *take(1u);
        c = load(up, n, nc % 8u, &m1, &m2, &tx, &rx);
        nc++;
        if ((c == SEDGE_FIELDS_OK) != (rust_ok != 0)) {
            if (verdict_bad++ < 5u) {
                fprintf(stderr, "case %zu: Rust %s, C %s\n", nc - 1u, rust_ok ? "accepts" : "rejects",
                        sedge_fields_error_message(c));
            }
        }
        if (!rust_ok) {
            free(m1);
            free(m2);
            continue;
        }
        m = u32_at();
        tb = take(m);
        len = u32_at();
        count = u32_at();
        reset = u32_at();
        in = take(count * len);
        rf = take(count * len);
        if (c != SEDGE_FIELDS_OK) {
            free(m1);
            free(m2);
            continue;
        }
        ok_cases++;
        if (sedge_fields_relation_count(tx) > 0u) {
            with_rel++;
        }
        for (k = 0; k < sedge_fields_field_count(tx); k++) {
            sedge_fields_field f;
            if (sedge_fields_get_field(tx, k, &f) == 0 && f.delta) {
                with_delta++;
                break;
            }
        }
        ser = xmalloc(m);
        if (sedge_fields_to_bytes(tx, ser, m, &sl) != 0 || sl != m || memcmp(ser, tb, m) != 0 ||
            sedge_fields_record_len(tx) != len) {
            ser_bad++;
        }
        free(ser);
        fwd = xmalloc(len);
        inv = xmalloc(len);
        for (k = 0; k < count; k++) {
            if (reset != 0u && k > 0u && k % reset == 0u) {
                sedge_fields_reset(tx);
                sedge_fields_reset(rx);
            }
            if (sedge_fields_forward(tx, in + k * len, len, fwd) != 0 ||
                sedge_fields_inverse(rx, fwd, len, inv) != 0) {
                die("call failed");
            }
            recs++;
            if (memcmp(fwd, rf + k * len, len) != 0 && fwd_bad++ < 5u) {
                fprintf(stderr, "case %zu: forward differs at record %zu\n", nc - 1u, k);
            }
            if (memcmp(inv, in + k * len, len) != 0 && inv_bad++ < 5u) {
                fprintf(stderr, "case %zu: inverse differs at record %zu\n", nc - 1u, k);
            }
        }
        free(fwd);
        free(inv);
        free(m1);
        free(m2);
    }
    printf("%s: %zu cases, %llu accepted (%llu with relations, %llu with deltas)\n", path, nc,
           ok_cases, with_rel, with_delta);
    printf("  verdict differs: %llu; to_bytes differs: %llu; records %llu, forward differs: %llu, "
           "inverse fails: %llu\n",
           verdict_bad, ser_bad, recs, fwd_bad, inv_bad);
    free(file);
    return verdict_bad || ser_bad || fwd_bad || inv_bad;
}

int main(int argc, char **argv)
{
    if (argc == 3 && strcmp(argv[1], "--cases") == 0) {
        return cases(argv[2]);
    }
    if (argc == 4 || argc == 5) {
        return real(argc, argv);
    }
    fprintf(stderr, "usage: crosscheck_fields DATA UPLINK RUST_FWD [RESET]\n"
                    "       crosscheck_fields --cases FILE\n");
    return 2;
}
