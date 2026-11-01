/* sedge_fields: shannon-edge record transforms in portable C99.
 *
 * The sender and receiver side of the Rust `shannon_edge::fields`
 * RecordTransform: field relations and field deltas, loaded from the
 * "SEDGREL1" uplink (docs/FORMAT.md, "Record transforms"). Bit-exact with
 * Rust: the same uplink and records give the same transformed records, so
 * either end of a link can be C or Rust. Learning a transform
 * (RecordTransform::learn) is ground-side only and stays in Rust.
 *
 * Properties: C99, no malloc (the caller provides one memory block, which
 * also holds the previous-record state of the deltas), no recursion, no
 * floating point, integer arithmetic only, only <stdint.h>, <stddef.h> and
 * <string.h>.
 *
 * Conventions: functions return SEDGE_FIELDS_OK (0) or a negative
 * SEDGE_FIELDS_E_* code. A transform is not thread-safe.
 */
#ifndef SEDGE_FIELDS_H
#define SEDGE_FIELDS_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Error codes (ARGUMENT and BAD_MODEL match include/shannon_edge.h). */
#define SEDGE_FIELDS_OK            0
#define SEDGE_FIELDS_E_ARGUMENT   -1  /* bad pointer, or a record of the wrong length */
#define SEDGE_FIELDS_E_BAD_MODEL -12  /* the uplink is not a valid transform */
#define SEDGE_FIELDS_E_MEMORY    -20  /* memory block too small */
#define SEDGE_FIELDS_E_BUFFER    -21  /* output buffer too small */

/* Field flags, as in the uplink. */
#define SEDGE_FIELDS_INTEGER    0x01u
#define SEDGE_FIELDS_SIGNED     0x02u
#define SEDGE_FIELDS_BIG_ENDIAN 0x04u
#define SEDGE_FIELDS_DELTA      0x08u

/* Uplink limits: at most 65535 fields of up to 255 bytes, 65535 relations. */
#define SEDGE_FIELDS_MAX_FIELDS    65535u
#define SEDGE_FIELDS_MAX_RELATIONS 65535u

/* Memory block size, as a constant expression for static allocation:
 * alignment slack (8) + header (32) + 8 bytes per field + 8 bytes per
 * relation + the previous record of each side (2 * record_len). Equal to
 * sedge_fields_memory_bytes for an uplink with these counts. */
#define SEDGE_FIELDS_MEMORY_BYTES(nfields, nrelations, record_len)          \
    (40u + 8u * (size_t)(nfields) + 8u * (size_t)(nrelations) +           \
     2u * (size_t)(record_len))

/* Length of the uplink for these counts (sedge_fields_to_bytes output). */
#define SEDGE_FIELDS_UPLINK_BYTES(nfields, nrelations)                       \
    (12u + 2u * (size_t)(nfields) + 8u * (size_t)(nrelations))

typedef struct sedge_fields sedge_fields;

/* One field (Rust fields::Field, plus its delta flag). */
typedef struct {
    uint32_t offset;   /* byte offset in the record */
    uint32_t width;    /* bytes: 1, 2, 4 or 8 for integers; 1..255 opaque */
    int integer;       /* integer field (relations and deltas apply) */
    int is_signed;     /* two's-complement signed (as stored in the uplink) */
    int big_endian;    /* big-endian byte order (as stored in the uplink) */
    int delta;         /* field delta (integer fields only) */
} sedge_fields_field;

/* x_target = floor((a * x_i + b * x_j) / 2) + r (Rust fields::Relation). */
typedef struct {
    uint16_t target, i, j;
    int8_t a, b;
} sedge_fields_relation;

/* Memory block size for the transform in uplink[0..n), or 0 if the uplink
 * is malformed (bad magic, width or flags, wrong length) or the size does
 * not fit size_t. sedge_fields_init checks the rest (indices). */
size_t sedge_fields_memory_bytes(const uint8_t *uplink, size_t n);

/* Load a transform from uplink[0..n) into `mem` (any alignment, mem_bytes
 * at least sedge_fields_memory_bytes). The uplink is untrusted: everything
 * Rust from_bytes checks is checked (magic, widths, flags, every index,
 * no target used twice or as a predictor, no trailing bytes) and rejected
 * with SEDGE_FIELDS_E_BAD_MODEL. The uplink is not referenced afterwards.
 * Starts with no previous record on either side. On any error *out is
 * NULL, and a transform loaded earlier in the same block must not be used
 * again (a bad index invalidates it).
 * Rust: RecordTransform::from_bytes(uplink). */
int sedge_fields_init(sedge_fields **out, void *mem, size_t mem_bytes,
                      const uint8_t *uplink, size_t n);

/* Sender: transform one record rec[0..len) into out[0..len). Records must
 * be fed in order. out may equal rec (in place) or overlap it.
 * SEDGE_FIELDS_E_ARGUMENT if len is not the record length (Rust panics).
 * Rust: forward(rec). */
int sedge_fields_forward(sedge_fields *t, const uint8_t *rec, size_t len,
                         uint8_t *out);

/* Receiver: undo sedge_fields_forward, records in the same order. Same
 * rules for out and len. Rust: inverse(rec). */
int sedge_fields_inverse(sedge_fields *t, const uint8_t *rec, size_t len,
                         uint8_t *out);

/* Forget the previous record on both sides (e.g. at an epoch boundary).
 * Rust: reset(). */
void sedge_fields_reset(sedge_fields *t);

/* Serialise to out[0..cap); *out_len receives the length
 * (SEDGE_FIELDS_UPLINK_BYTES, also on SEDGE_FIELDS_E_BUFFER).
 * Rust: to_bytes(). */
int sedge_fields_to_bytes(const sedge_fields *t, uint8_t *out, size_t cap,
                          size_t *out_len);

/* Rust layout().len(): the record length in bytes (0 for a bad handle). */
size_t sedge_fields_record_len(const sedge_fields *t);

/* Rust layout().fields().len() and relations().len(). */
size_t sedge_fields_field_count(const sedge_fields *t);
size_t sedge_fields_relation_count(const sedge_fields *t);

/* Field k (Rust layout().fields()[k] and deltas()[k]). */
int sedge_fields_get_field(const sedge_fields *t, size_t k,
                           sedge_fields_field *f);

/* Relation k (Rust relations()[k]). */
int sedge_fields_get_relation(const sedge_fields *t, size_t k,
                              sedge_fields_relation *r);

const char *sedge_fields_error_message(int code);

#ifdef __cplusplus
}
#endif

#endif /* SEDGE_FIELDS_H */
