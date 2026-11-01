/* Benchmark the C flight profile on a file of 16-bit little-endian samples,
 * as examples/flight_surprise.rs runs it (256-sample packets, bits = bit
 * length of the largest sample): compress every packet with its surprise,
 * then decompress and verify every one; best of R runs.
 *
 *   bench_flight SAMPLES.u16 [TABLE_BITS] [R]
 *
 * Host tool (POSIX clock_gettime, stdio, malloc; the codec uses none).
 */
#define _POSIX_C_SOURCE 199309L
#include "sedge_flight.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static double now(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (double)t.tv_sec + (double)t.tv_nsec * 1e-9;
}

int main(int argc, char **argv)
{
    FILE *f;
    long sz;
    size_t n, i, cap, np, mem, total = 0, m;
    int r, runs = argc > 3 ? atoi(argv[3]) : 3;
    uint32_t tb = argc > 2 ? (uint32_t)atoi(argv[2]) : 14u, bits = 1;
    unsigned char *raw;
    uint16_t *s, *d, mx = 0;
    uint32_t *sur, *sur2;
    uint8_t *frames;
    size_t *flen;
    double best_c = 1e30, best_d = 1e30;
    void *mt, *mr;
    if (argc < 2 || (f = fopen(argv[1], "rb")) == NULL) {
        fprintf(stderr, "usage: %s SAMPLES.u16 [TABLE_BITS] [RUNS]\n", argv[0]);
        return 2;
    }
    fseek(f, 0, SEEK_END);
    sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    raw = malloc((size_t)sz + 1u);
    if (sz < 2 || raw == NULL || fread(raw, 1, (size_t)sz, f) != (size_t)sz) {
        return 2;
    }
    fclose(f);
    n = (size_t)sz / 2u;
    s = malloc(n * sizeof *s);
    for (i = 0; i < n; i++) {
        s[i] = (uint16_t)(raw[2u * i] | raw[2u * i + 1u] << 8);
        mx = s[i] > mx ? s[i] : mx;
    }
    while (bits < 16u && (mx >> bits) != 0u) {
        bits++;
    }
    np = (n + 255u) / 256u;
    cap = sedge_flight_max_frame(256u, bits);
    mem = sedge_flight_memory_bytes(bits, tb);
    frames = malloc(np * cap);
    flen = malloc(np * sizeof *flen);
    sur = malloc(n * sizeof *sur);
    sur2 = malloc(256u * sizeof *sur2);
    d = malloc(256u * sizeof *d);
    mt = malloc(mem);
    mr = malloc(mem);
    if (s == NULL || frames == NULL || flen == NULL || sur == NULL || sur2 == NULL || d == NULL ||
        mt == NULL || mr == NULL) {
        return 2;
    }
    for (r = 0; r < runs; r++) {
        sedge_flight *tx, *rx;
        double t, tc;
        if (sedge_flight_init(&tx, mt, mem, bits, tb) != 0 ||
            sedge_flight_init(&rx, mr, mem, bits, tb) != 0) {
            return 2;
        }
        total = 0;
        t = now();
        for (i = 0; i < np; i++) {
            size_t k = n - i * 256u < 256u ? n - i * 256u : 256u;
            (void)sedge_flight_compress_scored(tx, s + i * 256u, k, frames + i * cap, cap, &flen[i],
                                               sur + i * 256u);
            total += flen[i];
        }
        tc = now() - t;
        best_c = tc < best_c ? tc : best_c;
        t = now();
        for (i = 0; i < np; i++) {
            size_t k = n - i * 256u < 256u ? n - i * 256u : 256u;
            if (sedge_flight_decompress_scored(rx, frames + i * cap, flen[i], d, 256u, &m, sur2) != 0 ||
                m != k || memcmp(d, s + i * 256u, k * sizeof *d) != 0 ||
                memcmp(sur2, sur + i * 256u, k * sizeof *sur2) != 0) {
                fprintf(stderr, "MISMATCH at frame %lu\n", (unsigned long)i);
                return 1;
            }
        }
        t = now() - t;
        best_d = t < best_d ? t : best_d;
        printf("C compress %.3f Msamples/s  decompress %.3f Msamples/s\n", (double)n / 1e6 / tc,
               (double)n / 1e6 / t);
    }
    printf("%lu samples (%u-bit, table_bits %u) -> %lu bytes; best of %d: %.3f / %.3f Msamples/s\n",
           (unsigned long)n, bits, tb, (unsigned long)total, runs, (double)n / 1e6 / best_c,
           (double)n / 1e6 / best_d);
    return 0;
}
