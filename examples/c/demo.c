/* Minimal C use of shannon-edge: one-shot compression and a session.
 *
 *   cargo build --release
 *   cc examples/c/demo.c -Iinclude -Ltarget/release -lshannon_edge -o demo
 *   LD_LIBRARY_PATH=target/release ./demo
 */
#include <shannon_edge.h>
#include <stdio.h>
#include <string.h>

static int check(int32_t rc, const char *what) {
    if (rc != SEDGE_OK) {
        fprintf(stderr, "%s failed: %s\n", what, sedge_error_message(rc));
        return 1;
    }
    return 0;
}

int main(void) {
    const char *text = "the quick brown fox jumps over the lazy dog; "
                       "the quick brown fox jumps over the lazy dog again";
    uint8_t *packed, *back;
    size_t packed_len, back_len;

    if (check(sedge_compress((const uint8_t *)text, strlen(text), NULL, 0, 0, &packed, &packed_len),
              "compress"))
        return 1;
    if (check(sedge_decompress(packed, packed_len, NULL, 0, &back, &back_len), "decompress"))
        return 1;
    int ok = back_len == strlen(text) && memcmp(back, text, back_len) == 0;
    printf("sedge %s: %zu -> %zu bytes, round trip %s\n", sedge_version(), strlen(text), packed_len,
           ok ? "OK" : "FAILED");
    sedge_free(packed, packed_len);
    sedge_free(back, back_len);

    SedgeSession *tx = sedge_session_new(NULL, 18, 0), *rx = sedge_session_new(NULL, 18, 0);
    size_t total = 0;
    char rec[96];
    for (int i = 0; i < 200 && ok; i++) {
        int n = snprintf(rec, sizeof rec, "{\"device\":\"s-%d\",\"seq\":%d,\"temp\":%d.%d}", i % 3, i,
                         20 + i % 7, i % 10);
        if (check(sedge_session_compress(tx, (uint8_t *)rec, (size_t)n, &packed, &packed_len), "session compress") ||
            check(sedge_session_decompress(rx, packed, packed_len, &back, &back_len), "session decompress"))
            return 1;
        ok = back_len == (size_t)n && memcmp(back, rec, back_len) == 0;
        total += packed_len;
        sedge_free(packed, packed_len);
        sedge_free(back, back_len);
    }
    printf("session: 200 records -> %zu bytes, %s\n", total, ok ? "all verified" : "MISMATCH");
    sedge_session_free(tx);
    sedge_session_free(rx);

    /* Flight profile: 12-bit housekeeping samples in 256-sample packets. */
    SedgeFlight *ftx = sedge_flight_new(12, 14), *frx = sedge_flight_new(12, 14);
    uint16_t samples[256];
    uint16_t *decoded;
    size_t n_decoded, flight_total = 0;
    unsigned level = 2000, seed = 1;
    for (int p = 0; p < 40 && ok; p++) {
        for (int i = 0; i < 256; i++) {
            seed = seed * 1103515245u + 12345u;
            samples[i] = (uint16_t)(level + (seed >> 16) % 7);
        }
        if (check(sedge_flight_compress(ftx, samples, 256, &packed, &packed_len), "flight compress") ||
            check(sedge_flight_decompress(frx, packed, packed_len, &decoded, &n_decoded), "flight decompress"))
            return 1;
        ok = n_decoded == 256 && memcmp(decoded, samples, sizeof samples) == 0;
        flight_total += packed_len;
        sedge_free(packed, packed_len);
        sedge_free_samples(decoded, n_decoded);
    }
    printf("flight: 40 packets x 256 samples (12-bit, %d bytes raw) -> %zu bytes, %s\n", 40 * 256 * 12 / 8,
           flight_total, ok ? "all verified" : "MISMATCH");
    sedge_flight_free(ftx);
    sedge_flight_free(frx);
    return ok ? 0 : 1;
}
