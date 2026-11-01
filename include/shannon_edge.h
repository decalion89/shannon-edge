/* shannon-edge C API.
 *
 * Link with libshannon_edge (build: `cargo build --release`; the library is
 * target/release/libshannon_edge.so / .dylib / shannon_edge.dll).
 *
 * Conventions: functions return 0 (SEDGE_OK) or a negative SEDGE_E_* code;
 * output buffers are allocated by the library and released with sedge_free;
 * models and sessions are opaque, not thread-safe, released with *_free.
 */
#ifndef SHANNON_EDGE_H
#define SHANNON_EDGE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SEDGE_OK                0
#define SEDGE_E_ARGUMENT       -1
#define SEDGE_E_TRUNCATED      -2
#define SEDGE_E_BAD_MAGIC      -3
#define SEDGE_E_VERSION        -4
#define SEDGE_E_METHOD         -5
#define SEDGE_E_MEM_BITS       -6
#define SEDGE_E_TOO_LARGE      -7
#define SEDGE_E_CHECKSUM       -8
#define SEDGE_E_BLOCK_TABLE    -9
#define SEDGE_E_DICT_REQUIRED -10
#define SEDGE_E_DICT_MISMATCH -11
#define SEDGE_E_BAD_MODEL     -12
#define SEDGE_E_OUT_OF_SYNC   -13
#define SEDGE_E_NOT_SESSION   -14

typedef struct SedgeModel SedgeModel;
typedef struct SedgeSession SedgeSession;

const char *sedge_version(void);
const char *sedge_error_message(int32_t code);
void sedge_free(uint8_t *p, size_t n);

/* Whole buffers. dict may be NULL with dict_len 0; mem_bits 0 = default. */
int32_t sedge_compress(const uint8_t *data, size_t len, const uint8_t *dict, size_t dict_len,
                       int32_t mem_bits, uint8_t **out, size_t *out_len);
int32_t sedge_decompress(const uint8_t *data, size_t len, const uint8_t *dict, size_t dict_len,
                         uint8_t **out, size_t *out_len);

/* Primed models: read a dictionary once, compress many messages from it. */
SedgeModel *sedge_model_new(const uint8_t *dict, size_t dict_len, int32_t mem_bits);
SedgeModel *sedge_model_load(const uint8_t *data, size_t len, int32_t *err);
int32_t sedge_model_save(const SedgeModel *m, uint8_t **out, size_t *out_len);
int32_t sedge_model_compress(SedgeModel *m, const uint8_t *data, size_t len, uint8_t **out,
                             size_t *out_len);
int32_t sedge_model_decompress(SedgeModel *m, const uint8_t *data, size_t len, uint8_t **out,
                               size_t *out_len);
void sedge_model_free(SedgeModel *m);

/* Sessions: both sides keep learning from every record, in order.
 * model may be NULL (start empty at mem_bits) or a primed model (copied).
 * flags: 0, or SEDGE_SESSION_LEAN for frames without sequence number and CRC
 * (only for links that already guarantee integrity and order). */
#define SEDGE_SESSION_LEAN 1u
SedgeSession *sedge_session_new(const SedgeModel *model, int32_t mem_bits, uint32_t flags);
/* Fixed-length records (e.g. telemetry packets): column contexts. Fresh
 * sessions without a model only; both sides must use the same length. */
int32_t sedge_session_set_record_len(SedgeSession *s, size_t len);
int32_t sedge_session_compress(SedgeSession *s, const uint8_t *data, size_t len, uint8_t **out,
                               size_t *out_len);
int32_t sedge_session_decompress(SedgeSession *s, const uint8_t *data, size_t len, uint8_t **out,
                                 size_t *out_len);
void sedge_session_free(SedgeSession *s);

/* Flight profile: small integer-only codec for telemetry samples (1..16 bits),
 * both ends learning from every packet, lean frames (no CRC: the link layer
 * must guarantee integrity and order). Memory ~12 * 2^table_bits bytes. */
typedef struct SedgeFlight SedgeFlight;
SedgeFlight *sedge_flight_new(uint32_t bits, uint32_t table_bits);
int32_t sedge_flight_compress(SedgeFlight *s, const uint16_t *samples, size_t n, uint8_t **out,
                              size_t *out_len);
int32_t sedge_flight_decompress(SedgeFlight *s, const uint8_t *data, size_t len, uint16_t **out,
                                size_t *out_n);
void sedge_free_samples(uint16_t *p, size_t n);
void sedge_flight_free(SedgeFlight *s);

#ifdef __cplusplus
}
#endif
#endif /* SHANNON_EDGE_H */
