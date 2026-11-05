/* Cross-check of the flight profile: compress a file of samples with the C
 * codec and compare every frame and every per-sample surprise with what the
 * Rust crate produced; decompress and verify every frame too.
 *
 *   crosscheck_flight SAMPLES.u16 RUST.frames RUST.u32 [TABLE_BITS]
 *
 * As examples/flight_surprise.rs: SAMPLES are 16-bit little-endian, bits
 * per sample = bit length of the largest (at least 1), 256-sample packets,
 * TABLE_BITS 14 by default. RUST.frames: per frame, a 4-byte little-endian
 * length then the bytes; RUST.u32: one little-endian u32 per sample (the
 * Rust dumper is shown in README.md). Also prints the Kraft alarm counts
 * for t = ceil(log2 N). Exit status 0 only if everything matches.
 * Host tool (stdio, malloc; the codec uses neither).
 */
#include "sedge_flight.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

static uint32_t le32(const unsigned char *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

int main(int argc, char **argv)
{
    size_t nraw, nfr, nsu, n, i, at = 0, rpos = 0, frames = 0, same_frames = 0, same_sur = 0;
    size_t bytes = 0, mem, cap, len, m, alarms = 0, cusum_alarms = 0;
    unsigned char *raw, *rf, *rs, *out;
    uint16_t *s, *d, mx = 0;
    uint32_t *sur, *sur2, bits = 1, tb = argc > 4 ? (uint32_t)atoi(argv[4]) : 14u, t;
    void *mt, *mr;
    sedge_flight *tx, *rx;
    sedge_flight_cusum cu;
    int bad_decode = 0;
    if (argc < 4) {
        fprintf(stderr, "usage: %s SAMPLES.u16 RUST.frames RUST.u32 [TABLE_BITS]\n", argv[0]);
        return 2;
    }
    raw = read_file(argv[1], &nraw);
    rf = read_file(argv[2], &nfr);
    rs = read_file(argv[3], &nsu);
    n = nraw / 2u;
    s = malloc(n * sizeof *s + 2u);
    sur = malloc(n * sizeof *sur + 4u);
    sur2 = malloc(256u * sizeof *sur2);
    d = malloc(256u * sizeof *d);
    for (i = 0; i < n; i++) {
        s[i] = (uint16_t)(raw[2u * i] | raw[2u * i + 1u] << 8);
        mx = s[i] > mx ? s[i] : mx;
    }
    while (bits < 16u && (mx >> bits) != 0u) {
        bits++;
    }
    mem = sedge_flight_memory_bytes(bits, tb);
    cap = sedge_flight_max_frame(256u, bits);
    mt = malloc(mem);
    mr = malloc(mem);
    out = malloc(cap);
    if (s == NULL || sur == NULL || sur2 == NULL || d == NULL || mt == NULL || mr == NULL ||
        out == NULL || sedge_flight_init(&tx, mt, mem, bits, tb) != 0 ||
        sedge_flight_init(&rx, mr, mem, bits, tb) != 0) {
        fprintf(stderr, "bad parameters or out of memory\n");
        return 2;
    }
    for (at = 0; at < n; at += 256u) {
        size_t k = n - at < 256u ? n - at : 256u;
        uint32_t rlen;
        if (sedge_flight_compress_scored(tx, s + at, k, out, cap, &len, sur + at) != 0) {
            fprintf(stderr, "compress failed\n");
            return 1;
        }
        bytes += len;
        frames++;
        if (rpos + 4u <= nfr) {
            rlen = le32(rf + rpos);
            if (rlen == len && rpos + 4u + rlen <= nfr && memcmp(rf + rpos + 4u, out, len) == 0) {
                same_frames++;
            }
            rpos += 4u + rlen;
        }
        if (sedge_flight_decompress_scored(rx, out, len, d, 256u, &m, sur2) != 0 || m != k ||
            memcmp(d, s + at, k * sizeof *d) != 0 || memcmp(sur2, sur + at, k * sizeof *sur2) != 0) {
            bad_decode++;
        }
    }
    for (i = 0; i < n && 4u * i + 4u <= nsu; i++) {
        same_sur += le32(rs + 4u * i) == sur[i];
    }
    t = sedge_flight_kraft_t(n);
    sedge_flight_cusum_init(&cu);
    for (i = 0; i < n; i++) {
        alarms += (size_t)sedge_flight_kraft_alarm(sur[i], bits, t);
        cusum_alarms += (size_t)sedge_flight_cusum_update(&cu, sur[i], bits, t);
    }
    printf("%s: %lu samples, %u-bit, table_bits %u\n", argv[1], (unsigned long)n, bits, tb);
    printf("  frames identical to Rust:   %lu / %lu (C %lu bytes, Rust file %lu frames)\n",
           (unsigned long)same_frames, (unsigned long)frames, (unsigned long)bytes,
           (unsigned long)(rpos == nfr ? frames : 0u));
    printf("  surprise identical to Rust: %lu / %lu (Rust file %lu values)\n",
           (unsigned long)same_sur, (unsigned long)n, (unsigned long)(nsu / 4u));
    printf("  C frames decoded by C: %s\n", bad_decode ? "MISMATCH" : "all identical");
    printf("  Kraft t = %u: %lu per-sample alarms, %lu samples in cumulative alarm\n", t,
           (unsigned long)alarms, (unsigned long)cusum_alarms);
    return (same_frames == frames && rpos == nfr && same_sur == n && nsu == 4u * n &&
            !bad_decode) ? 0 : 1;
}
