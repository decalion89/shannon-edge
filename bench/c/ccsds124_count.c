/*
 * Compress-only CCSDS 124 driver for instruction counting on other
 * architectures (e.g. RISC-V under QEMU): compresses the first N packets of
 * a file packet by packet with the open C implementation
 * (github.com/tanagraspace/ccsds124), with the automatic parameter schedule
 * of ccsds124_compress, and prints the total size. Run with N = 0 to measure
 * the start-up cost to subtract.
 *
 *   ccsds124_count PACKETS.bin PACKET_LEN N PT FT RT R
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "ccsds124.h"

int main(int argc, char **argv) {
    if (argc < 8) {
        fprintf(stderr, "usage: %s PACKETS PLEN N PT FT RT R\n", argv[0]);
        return 2;
    }
    size_t plen = (size_t)atoi(argv[2]), n = (size_t)atoi(argv[3]);
    int pt = atoi(argv[4]), ft = atoi(argv[5]), rt = atoi(argv[6]), r = atoi(argv[7]);
    FILE *f = fopen(argv[1], "rb");
    if (!f) return 1;
    uint8_t *in = malloc(n * plen + 1);
    if (fread(in, 1, n * plen, f) != n * plen) return 1;
    fclose(f);
    ccsds124_compressor_t comp;
    if (ccsds124_compressor_init(&comp, plen * 8, NULL, (uint8_t)r, pt, ft, rt) != CCSDS124_OK) return 1;
    ccsds124_compressor_reset(&comp);
    size_t total = 0;
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
        if (ccsds124_compress_packet(&comp, &v, &out, &p) != CCSDS124_OK) return 1;
        total += (out.num_bits + 7) / 8;
    }
    printf("%zu packets -> %zu bytes\n", n, total);
    return 0;
}
