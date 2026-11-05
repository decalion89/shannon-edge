/* sedge_flight: the shannon-edge flight profile in portable C99.
 *
 * Bit-exact with the Rust `shannon_edge::flight::FlightSession`: the same
 * samples give the same frames and the same per-sample surprise (the cost
 * of each sample in 1/256 bits), so a C encoder on board can talk to a Rust
 * decoder on the ground, or the other way round. See c/README.md.
 *
 * Properties: C99, no malloc (the caller provides one memory block, sized by
 * SEDGE_FLIGHT_MEMORY_BYTES), no recursion, no floating point, integer
 * arithmetic only, only <stdint.h>, <stddef.h> and <string.h>.
 *
 * Conventions: functions return SEDGE_FLIGHT_OK (0) or a negative
 * SEDGE_FLIGHT_E_* code. A session is not thread-safe.
 *
 * Names: the Rust C ABI (include/shannon_edge.h) already exports
 * sedge_flight_new / _compress / _decompress / _free for the Rust library.
 * This port avoids those four names so a ground tool can link both; Rust's
 * compress and decompress are the _scored functions with surprise = NULL.
 */
#ifndef SEDGE_FLIGHT_H
#define SEDGE_FLIGHT_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Error codes (the first three match include/shannon_edge.h). */
#define SEDGE_FLIGHT_OK           0
#define SEDGE_FLIGHT_E_ARGUMENT  -1  /* bad parameter, pointer, or a sample
                                        that does not fit bits_per_sample */
#define SEDGE_FLIGHT_E_TRUNCATED -2  /* frame ends inside its sample count */
#define SEDGE_FLIGHT_E_TOO_LARGE -7  /* sample count impossible for the frame */
#define SEDGE_FLIGHT_E_MEMORY   -20  /* memory block too small */
#define SEDGE_FLIGHT_E_BUFFER   -21  /* output buffer too small */

/* Parameter ranges (as in Rust FlightSession::new). */
#define SEDGE_FLIGHT_MIN_BITS        1u
#define SEDGE_FLIGHT_MAX_BITS       16u
#define SEDGE_FLIGHT_MIN_TABLE_BITS 12u
#define SEDGE_FLIGHT_MAX_TABLE_BITS 24u

/* A valid frame never makes the decoder read more than this many bytes
 * past its end (see sedge_flight_last_overrun). */
#define SEDGE_FLIGHT_MAX_OVERRUN 7u

/* Memory block size, as a constant expression for static allocation:
 * alignment slack (8) + session header (64) + mixer weights (16 per bit)
 * + 4-byte counters: order-0 table 2^min(tb, bits + 1), order-1 and
 * order-2 tables 2^tb each, residual table 2^min(tb, 16). Equal to
 * sedge_flight_memory_bytes. Arguments must be in range. */
#define SEDGE_FLIGHT_MEMORY_BYTES(bits, table_bits)                              \
    (72u + 16u * (size_t)(bits) +                                                \
     4u * (((size_t)1 << ((table_bits) < (bits) + 1u ? (table_bits) : (bits) + 1u)) + \
           ((size_t)2 << (table_bits)) +                                         \
           ((size_t)1 << ((table_bits) < 16u ? (table_bits) : 16u))))

/* Largest frame for n samples of `bits` bits (a proven bound; see README).
 * Any buffer this big makes compression infallible. */
#define SEDGE_FLIGHT_MAX_FRAME(n, bits) (14u + (size_t)(n) * (3u * (size_t)(bits) + 4u))

typedef struct sedge_flight sedge_flight;

/* Memory block size for a session; 0 if a parameter is out of range. */
size_t sedge_flight_memory_bytes(uint32_t bits_per_sample, uint32_t table_bits);

/* SEDGE_FLIGHT_MAX_FRAME, or 0 if out of range or it overflows size_t. */
size_t sedge_flight_max_frame(size_t n_samples, uint32_t bits_per_sample);

/* Create a session in `mem` (any alignment; `mem_bytes` at least
 * sedge_flight_memory_bytes). Samples have `bits_per_sample` bits (1..16);
 * the model tables have 2^table_bits entries (12..24). Both ends of a link
 * must use the same parameters and process the same frames in order. On
 * success *out is the session (inside `mem`).
 * Rust: FlightSession::new(bits_per_sample, table_bits). */
int sedge_flight_init(sedge_flight **out, void *mem, size_t mem_bytes,
                      uint32_t bits_per_sample, uint32_t table_bits);

/* Compress one packet of `n` samples into out[0..cap) and learn from it;
 * *out_len receives the frame length. If `surprise` is not NULL, it
 * receives n values: the cost of each sample in 1/256 bits.
 * Rust: compress_scored (and compress, with surprise = NULL).
 *
 * SEDGE_FLIGHT_E_ARGUMENT: a sample does not fit in bits_per_sample bits
 *   (Rust panics); nothing was learned.
 * SEDGE_FLIGHT_E_BUFFER: the frame did not fit; *out_len is the size it
 *   needed. The packet WAS learned, so this end is now ahead of the
 *   receiver: restart both ends. cap >= SEDGE_FLIGHT_MAX_FRAME(n, bits)
 *   rules this out. */
int sedge_flight_compress_scored(sedge_flight *s, const uint16_t *samples,
                                 size_t n, uint8_t *out, size_t cap,
                                 size_t *out_len, uint32_t *surprise);

/* Decompress one frame into samples[0..cap) and learn from it; *n_out
 * receives the sample count. If `surprise` is not NULL, it receives the
 * same per-sample costs the sender computed (it needs room for cap values).
 * Rust: decompress_scored (and decompress, with surprise = NULL).
 *
 * Errors leave the session unchanged:
 * SEDGE_FLIGHT_E_TRUNCATED, _E_TOO_LARGE: as Rust's Error::Truncated and
 *   Error::TooLarge (the frame cannot hold its sample count).
 * SEDGE_FLIGHT_E_BUFFER: more than `cap` samples; *n_out is the count.
 * Any other frame (garbage included) decodes to some samples, as in Rust:
 * integrity is the link layer's job. */
int sedge_flight_decompress_scored(sedge_flight *s, const uint8_t *frame,
                                   size_t len, uint16_t *samples, size_t cap,
                                   size_t *n_out, uint32_t *surprise);

/* Rust bits_per_sample(). */
uint32_t sedge_flight_bits_per_sample(const sedge_flight *s);

/* Bytes the last decompress read past the end of its frame. More than
 * SEDGE_FLIGHT_MAX_OVERRUN proves the frame truncated or corrupt (an
 * optional check; Rust does not make it). */
size_t sedge_flight_last_overrun(const sedge_flight *s);

const char *sedge_flight_error_message(int code);

/* ------------------------------------------------ Kraft anomaly detector
 *
 * Training-free thresholds from docs/KRAFT_DETECTION.md. For a calibrated
 * model, P(surprise >= (b + t) bits) <= 2^-t for every sample, whatever
 * came before, so N samples give at most N * 2^-t false alarms on average.
 * b is bits_per_sample.
 *
 * Per-sample rule (the one validated on ESA-ADB): alarm when
 *     surprise >= (b + t) * 256,   t = sedge_flight_kraft_t(N)
 * which allows one expected false alarm in N samples. */

/* ceil(log2 n): 0 for n <= 1. Integer only. */
uint32_t sedge_flight_kraft_t(uint64_t n_samples);

/* (bits + t) * 256, the surprise threshold in 1/256 bits (saturates at
 * UINT32_MAX). */
uint32_t sedge_flight_kraft_threshold(uint32_t bits_per_sample, uint32_t t);

/* 1 if surprise >= sedge_flight_kraft_threshold(bits, t), else 0. */
int sedge_flight_kraft_alarm(uint32_t surprise, uint32_t bits_per_sample,
                             uint32_t t);

#ifndef SEDGE_FLIGHT_NO_CUSUM
/* EXPERIMENTAL: cumulative Kraft rule. Not validated for operations: it
 * gains on ESA-AD Mission 1 lightweight but collapses where the model is
 * even mildly overconfident (bench/results/esa_adb.md).
 *
 * Per channel, four CUSUMs S_e = max(0, S_e + x_e) of the log e-values
 *     x_e = log2((1 - e) + e * 2^(cost - b)),  e = 2^-1, 2^-4, 2^-8, 2^-12
 * (cost = surprise / 256 bits). Alarm while max_e S_e >= t + 2 bits.
 *
 * Fixed point: x_e and S_e are in units of 2^-32 bits (int64_t). Each x_e
 * is rounded down (never above the exact value, so the e-value bound still
 * holds) and is at most 2^-28 bits below it (checked exhaustively by
 * test_flight.c against long double). S_e saturates at 2^30 bits. */
#define SEDGE_FLIGHT_CUSUM_N 4u
typedef struct {
    int64_t s[SEDGE_FLIGHT_CUSUM_N]; /* S_e, Q32 bits; e = 2^-1, -4, -8, -12 */
} sedge_flight_cusum;

/* Zero all four sums. */
void sedge_flight_cusum_init(sedge_flight_cusum *c);

/* Add one sample's surprise; returns 1 when max_e S_e >= (t + 2) bits
 * (t <= 2^28), else 0. */
int sedge_flight_cusum_update(sedge_flight_cusum *c, uint32_t surprise,
                              uint32_t bits_per_sample, uint32_t t);

/* max_e S_e in Q32 bits (for logging). */
int64_t sedge_flight_cusum_score(const sedge_flight_cusum *c);

/* log2((1 - 2^-k) + 2^-k * 2^(surprise/256 - bits)) in Q32 bits, rounded
 * down, for k in 1..32 and bits in 1..16 (0 otherwise). */
int64_t sedge_flight_log_evalue(uint32_t surprise, uint32_t bits_per_sample,
                                uint32_t k);
#endif

#ifdef __cplusplus
}
#endif

#endif /* SEDGE_FLIGHT_H */
