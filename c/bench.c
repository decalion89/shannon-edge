/* Benchmark the C fast profile on a file of fixed-length packets, like
 * examples/packet_fast_bench.rs (default layout): compress every packet,
 * then decompress and verify every one; best of R runs.
 *
 *   bench PACKETS.bin PACKET_LEN [R]
 *
 * Host tool (POSIX clock_gettime, stdio, malloc; the codec uses none).
 */
#define _POSIX_C_SOURCE 199309L
#include "sedge_fast.h"

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
    size_t len, n, i, cap, total = 0, bytes;
    int r, runs = argc > 3 ? atoi(argv[3]) : 3;
    unsigned char *data, *pay, *q;
    size_t *plen;
    double best_c = 1e30, best_d = 1e30;
    void *mt, *mr;
    if (argc < 3 || (f = fopen(argv[1], "rb")) == NULL) {
        fprintf(stderr, "usage: %s PACKETS.bin PACKET_LEN [RUNS]\n", argv[0]);
        return 2;
    }
    fseek(f, 0, SEEK_END);
    sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    len = (size_t)strtoul(argv[2], NULL, 10);
    data = malloc((size_t)sz);
    if (len == 0 || sz <= 0 || fread(data, 1, (size_t)sz, f) != (size_t)sz) {
        return 2;
    }
    fclose(f);
    n = (size_t)sz / len;
    cap = sedge_fast_max_payload(len);
    pay = malloc(n * cap);
    plen = malloc(n * sizeof *plen);
    q = malloc(len);
    bytes = sedge_fast_memory_bytes(len, NULL, 0);
    mt = malloc(bytes);
    mr = malloc(bytes);
    for (r = 0; r < runs; r++) {
        sedge_fast *tx, *rx;
        double t;
        if (sedge_fast_init(&tx, mt, bytes, len, NULL, NULL, 0) != 0 ||
            sedge_fast_init(&rx, mr, bytes, len, NULL, NULL, 0) != 0) {
            return 2;
        }
        t = now();
        for (i = 0; i < n; i++) {
            sedge_fast_compress(tx, data + i * len, pay + i * cap, cap, &plen[i]);
        }
        t = now() - t;
        best_c = t < best_c ? t : best_c;
        t = now();
        for (i = 0; i < n; i++) {
            sedge_fast_decompress(rx, pay + i * cap, plen[i], q);
            if (memcmp(q, data + i * len, len) != 0) {
                fprintf(stderr, "packet %zu differs\n", i);
                return 1;
            }
        }
        t = now() - t;
        best_d = t < best_d ? t : best_d;
    }
    for (i = 0; i < n; i++) {
        total += plen[i];
    }
    printf("%zu packets x %zu bytes (%zu bytes) -> %zu bytes (%.2fx), C fast profile, memory %.0f KiB, "
           "compress %.1f MB/s, decompress %.1f MB/s (verified, best of %d)\n",
           n, len, n * len, total, (double)(n * len) / (double)total, (double)bytes / 1024.0,
           (double)(n * len) / best_c / 1e6, (double)(n * len) / best_d / 1e6, runs);
    return 0;
}
