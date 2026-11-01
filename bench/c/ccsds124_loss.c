/*
 * CCSDS 124.0-B-1 (POCKET+) under simulated packet loss.
 *
 * Compresses a file of fixed-length packets packet by packet with the open
 * C implementation (github.com/tanagraspace/ccsds124, MIT), drops packets
 * with the same i.i.d. loss pattern as examples/packet_robust.rs (same
 * xorshift generator and seed), tells the decompressor about each gap
 * (ccsds124_decompressor_notify_packet_loss) and counts how many packets
 * come out exactly right. Also writes the size in bytes of every
 * compressed packet (byte-padded, as ccsds124_compress does) so that
 * packet-level erasure coding can be evaluated on the same payloads.
 *
 * Build (from a ccsds124 checkout, after `make` in implementations/c):
 *   cc -O2 -std=c99 -I implementations/c/include bench/c/ccsds124_loss.c \
 *      implementations/c/build/libccsds124.a -o ccsds124_loss
 * Run:
 *   ccsds124_loss PACKETS.bin PACKET_LEN SKIP PT FT RT R LOSS_PER_MILLE [SIZES_OUT]
 * SKIP packets at the start are excluded (the "history" of packet_robust).
 */
#define _POSIX_C_SOURCE 199309L
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "ccsds124.h"

static uint64_t rng_next(uint64_t *s) {
    *s ^= *s >> 12;
    *s ^= *s << 25;
    *s ^= *s >> 27;
    return *s * 0x2545f4914f6cdd1dULL;
}

typedef struct {
    size_t bits;
    uint8_t *data;
} packet_t;

int main(int argc, char **argv) {
    if (argc < 9) {
        fprintf(stderr, "usage: %s PACKETS PLEN SKIP PT FT RT R LOSS_PER_MILLE [SIZES_OUT]\n", argv[0]);
        return 2;
    }
    size_t plen = (size_t)atoi(argv[2]), skip = (size_t)atoi(argv[3]);
    int pt = atoi(argv[4]), ft = atoi(argv[5]), rt = atoi(argv[6]), r = atoi(argv[7]);
    uint64_t loss = (uint64_t)atoi(argv[8]);
    FILE *f = fopen(argv[1], "rb");
    if (!f) return 1;
    fseek(f, 0, SEEK_END);
    size_t size = (size_t)ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *raw = malloc(size);
    if (fread(raw, 1, size, f) != size) return 1;
    fclose(f);
    size_t n = size / plen - skip;
    const uint8_t *in = raw + skip * plen;

    /* Compress, with the automatic parameter schedule of ccsds124_compress. */
    ccsds124_compressor_t comp;
    if (ccsds124_compressor_init(&comp, plen * 8, NULL, (uint8_t)r, pt, ft, rt) != CCSDS124_OK) return 1;
    ccsds124_compressor_reset(&comp);
    packet_t *pk = calloc(n, sizeof *pk);
    size_t total = 0;
    FILE *sizes = argc > 9 ? fopen(argv[9], "w") : NULL;
    struct timespec t0, t1;
    double busy = 0.0; /* time inside the compressor only */
    for (size_t i = 0; i < n; i++) {
        bitvector_t v;
        bitbuffer_t out;
        ccsds124_params_t p;
        bitvector_init(&v, plen * 8);
        bitbuffer_init(&out);
        bitvector_from_bytes(&v, in + i * plen, plen);
        p.min_robustness = (uint8_t)r;
        if (i == 0) {
            p.send_mask_flag = 1;
            p.uncompressed_flag = 1;
            p.new_mask_flag = 0;
        } else {
            if (comp.ft_counter == 1) { p.send_mask_flag = 1; comp.ft_counter = comp.ft_limit; }
            else { comp.ft_counter--; p.send_mask_flag = 0; }
            if (comp.pt_counter == 1) { p.new_mask_flag = 1; comp.pt_counter = comp.pt_limit; }
            else { comp.pt_counter--; p.new_mask_flag = 0; }
            if (comp.rt_counter == 1) { p.uncompressed_flag = 1; comp.rt_counter = comp.rt_limit; }
            else { comp.rt_counter--; p.uncompressed_flag = 0; }
            if (i <= (size_t)r) { p.send_mask_flag = 1; p.uncompressed_flag = 1; p.new_mask_flag = 0; }
        }
        clock_gettime(CLOCK_MONOTONIC, &t0);
        if (ccsds124_compress_packet(&comp, &v, &out, &p) != CCSDS124_OK) return 1;
        clock_gettime(CLOCK_MONOTONIC, &t1);
        busy += (double)(t1.tv_sec - t0.tv_sec) + 1e-9 * (double)(t1.tv_nsec - t0.tv_nsec);
        pk[i].bits = out.num_bits;
        pk[i].data = malloc((out.num_bits + 7) / 8 + 1);
        size_t bytes = bitbuffer_to_bytes(&out, pk[i].data, (out.num_bits + 7) / 8 + 1);
        total += bytes;
        if (sizes) fprintf(sizes, "%zu\n", bytes);
    }
    if (sizes) fclose(sizes);

    /* Decompress under loss. */
    ccsds124_decompressor_t dec;
    ccsds124_decompressor_init(&dec, plen * 8, NULL, (uint8_t)r);
    uint64_t s = 0x5eed + loss;
    size_t correct = 0, guaranteed = 0, wrong_guaranteed = 0, gap = 0;
    uint8_t *buf = malloc(plen);
    for (size_t i = 0; i < n; i++) {
        if (rng_next(&s) % 1000 < loss) { gap++; continue; }
        if (gap) { ccsds124_decompressor_notify_packet_loss(&dec, (uint32_t)gap); gap = 0; }
        bitvector_t o;
        bitvector_init(&o, plen * 8);
        ccsds124_decompress_result_t res;
        int rc = ccsds124_decompress_packet_checked(&dec, pk[i].data, pk[i].bits, &o, &res);
        if (rc < 0) continue;
        bitvector_to_bytes(&o, buf, plen);
        int ok = memcmp(buf, in + i * plen, plen) == 0;
        correct += ok;
        if (rc == CCSDS124_OK) { guaranteed++; wrong_guaranteed += !ok; }
    }
    printf("R=%d pt=%d ft=%d rt=%d: %zu packets, %zu bytes, compress %.1f MB/s; loss %llu/1000: "
           "correct %.2f%%, guaranteed %.2f%%, guaranteed-but-wrong %zu\n",
           r, pt, ft, rt, n, total, (double)(n * plen) / busy / 1e6, (unsigned long long)loss,
           100.0 * correct / n, 100.0 * guaranteed / n, wrong_guaranteed);
    return 0;
}
