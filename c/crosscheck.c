/* Cross-check: compress a file of fixed-length packets with the C codec and
 * compare every payload with the one the Rust crate produced; decompress
 * and verify every packet too.
 *
 *   crosscheck PACKETS LEN RUST_PAYLOADS [--recipes F] [--classes F]
 *              [--prime N] [--epochs E] [--learn]
 *
 * RUST_PAYLOADS: for each compressed packet, a 4-byte little-endian length
 * then the payload (the Rust dumper is shown in README.md). --prime N:
 * both ends are primed with the first N packets, the rest are compressed.
 * --recipes/--classes: layout files (LEN bytes each). --learn: also run
 * the C learn_classes (10000, 900000 ppm) and learn_recipes on the priming
 * history and compare them with the layout files.
 * Exit status 0 only if every payload is identical and every packet
 * decodes. Host tool (uses stdio and malloc; the codec does not).
 */
#include "sedge_fast.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

unsigned long sedge_fast_test_fallbacks;

static unsigned char *read_file(const char *path, size_t *n)
{
    FILE *f = fopen(path, "rb");
    unsigned char *b;
    long sz;
    if (f == NULL || fseek(f, 0, SEEK_END) != 0 || (sz = ftell(f)) < 0 || fseek(f, 0, SEEK_SET) != 0) {
        fprintf(stderr, "cannot read %s\n", path);
        exit(2);
    }
    b = malloc((size_t)sz + 1u);
    if (b == NULL || fread(b, 1, (size_t)sz, f) != (size_t)sz) {
        fprintf(stderr, "cannot read %s\n", path);
        exit(2);
    }
    fclose(f);
    *n = (size_t)sz;
    return b;
}

static sedge_fast *session(size_t len, const uint8_t *r, const uint8_t *c, unsigned flags)
{
    size_t bytes = sedge_fast_memory_bytes(len, r, flags);
    sedge_fast *s = NULL;
    void *m = malloc(bytes);
    int e = m ? sedge_fast_init(&s, m, bytes, len, r, c, flags) : SEDGE_FAST_E_MEMORY;
    if (e != 0) {
        fprintf(stderr, "init: %s\n", sedge_fast_error_message(e));
        exit(2);
    }
    return s;
}

int main(int argc, char **argv)
{
    size_t npk, len, nrust, i, k, prime = 0, pos = 0, mismatches = 0, bad = 0, total_c = 0, total_r = 0;
    size_t first_mismatch = (size_t)-1, cap, plen, nl;
    unsigned long epochs = 0;
    int learn = 0, a;
    unsigned char *packets, *rust, *recipes = NULL, *classes = NULL;
    uint8_t *out, *q;
    sedge_fast *tx, *rx;
    if (argc < 4) {
        fprintf(stderr, "usage: %s PACKETS LEN RUST_PAYLOADS [--recipes F] [--classes F] "
                        "[--prime N] [--epochs E] [--learn]\n", argv[0]);
        return 2;
    }
    packets = read_file(argv[1], &npk);
    len = (size_t)strtoul(argv[2], NULL, 10);
    rust = read_file(argv[3], &nrust);
    for (a = 4; a < argc; a++) {
        if (!strcmp(argv[a], "--recipes") && a + 1 < argc) {
            recipes = read_file(argv[++a], &nl);
            if (nl != len) return 2;
        } else if (!strcmp(argv[a], "--classes") && a + 1 < argc) {
            classes = read_file(argv[++a], &nl);
            if (nl != len) return 2;
        } else if (!strcmp(argv[a], "--prime") && a + 1 < argc) {
            prime = (size_t)strtoul(argv[++a], NULL, 10);
        } else if (!strcmp(argv[a], "--epochs") && a + 1 < argc) {
            epochs = strtoul(argv[++a], NULL, 10);
        } else if (!strcmp(argv[a], "--learn")) {
            learn = 1;
        } else {
            fprintf(stderr, "unknown argument %s\n", argv[a]);
            return 2;
        }
    }
    if (len == 0 || npk % len != 0 || prime > npk / len) {
        fprintf(stderr, "bad packet length or prime count\n");
        return 2;
    }
    npk /= len;
    tx = session(len, recipes, classes, epochs ? SEDGE_FAST_EPOCHS : 0u);
    rx = session(len, recipes, classes, epochs ? SEDGE_FAST_EPOCHS : 0u);
    if (sedge_fast_prime(tx, packets, prime) != 0 || sedge_fast_prime(rx, packets, prime) != 0 ||
        (epochs && (sedge_fast_set_epochs(tx, epochs) != 0 || sedge_fast_set_epochs(rx, epochs) != 0))) {
        fprintf(stderr, "prime/epochs failed\n");
        return 2;
    }
    cap = sedge_fast_max_payload(len);
    out = malloc(cap);
    q = malloc(len);
    for (i = prime; i < npk; i++) {
        const uint8_t *p = packets + i * len;
        size_t rl;
        if (sedge_fast_compress(tx, p, out, cap, &plen) != 0) {
            bad++;
            continue;
        }
        total_c += plen;
        if (pos + 4 > nrust) {
            mismatches++;
        } else {
            rl = (size_t)rust[pos] | (size_t)rust[pos + 1] << 8 | (size_t)rust[pos + 2] << 16 |
                 (size_t)rust[pos + 3] << 24;
            pos += 4;
            if (rl > nrust - pos || rl != plen || memcmp(rust + pos, out, plen) != 0) {
                if (mismatches++ == 0) {
                    first_mismatch = i;
                }
            }
            total_r += rl;
            pos += rl > nrust - pos ? nrust - pos : rl;
        }
        if (sedge_fast_decompress(rx, out, plen, q) != 0 || memcmp(p, q, len) != 0 ||
            sedge_fast_last_overrun(rx) > SEDGE_FAST_MAX_OVERRUN) {
            bad++;
        }
    }
    printf("%s: %zu packets x %zu bytes compressed (after %zu priming), C %zu bytes, Rust %zu bytes\n",
           argv[1], npk - prime, len, prime, total_c, total_r);
    printf("payloads identical to Rust: %zu / %zu%s; decode failures: %zu; "
           "bit-by-bit symbols (both ends): %lu\n",
           npk - prime - mismatches, npk - prime, pos == nrust ? "" : " (Rust file has extra data)", bad,
           sedge_fast_test_fallbacks);
    if (mismatches) {
        printf("first mismatch at packet %zu\n", first_mismatch);
    }
    if (learn && recipes && classes && prime > 0) {
        uint8_t *lc = malloc(len), *lr = malloc(len);
        void *scratch = malloc(SEDGE_FAST_LEARN_SCRATCH_BYTES);
        size_t same_c = 0, same_r = 0;
        sedge_fast_learn_classes(len, packets, prime, 10000, 900000, lc);
        sedge_fast_learn_recipes(len, packets, prime, scratch, SEDGE_FAST_LEARN_SCRATCH_BYTES, lr);
        for (k = 0; k < len; k++) {
            same_c += lc[k] == classes[k];
            same_r += lr[k] == recipes[k];
        }
        printf("C learn_classes = Rust on %zu / %zu columns; C learn_recipes = Rust on %zu / %zu columns\n",
               same_c, len, same_r, len);
        if (same_c != len) {
            mismatches++;
        }
    }
    return mismatches || bad || pos != nrust;
}
