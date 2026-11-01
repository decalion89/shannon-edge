/* sedge_fast: the shannon-edge fast packet profile in portable C99.
 *
 * Bit-exact with the Rust `shannon_edge::packet_fast::FastPacketSession`:
 * same payload bytes for the same packets, layout, priming and epochs, so
 * either side can talk to the other. See c/README.md.
 *
 * Properties: C99, no malloc (the caller provides one memory block, sized by
 * sedge_fast_memory_bytes), no recursion, no floating point, integer
 * arithmetic only, only <stdint.h>, <stddef.h> and <string.h>. The state is
 * position-independent: copying it (sedge_fast_copy) clones a session.
 *
 * Conventions: functions return SEDGE_FAST_OK (0) or a negative
 * SEDGE_FAST_E_* code. A session is not thread-safe.
 */
#ifndef SEDGE_FAST_H
#define SEDGE_FAST_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Error codes (ARGUMENT and OUT_OF_SYNC match include/shannon_edge.h). */
#define SEDGE_FAST_OK              0
#define SEDGE_FAST_E_ARGUMENT     -1  /* bad length, recipe, class, pointer */
#define SEDGE_FAST_E_OUT_OF_SYNC -13  /* decompress_indexed: wait for epoch */
#define SEDGE_FAST_E_MEMORY      -20  /* memory block too small */
#define SEDGE_FAST_E_BUFFER      -21  /* compress: output buffer too small */
#define SEDGE_FAST_E_STATE       -22  /* prime after epochs; epochs without
                                         memory reserved for them */

/* Packet length range. */
#define SEDGE_FAST_MAX_LEN 65536u

/* Context recipes for a column's delta tables (number of tables). */
#define SEDGE_FAST_RECIPE_LEFT_CHANGED            0u /*  2, default */
#define SEDGE_FAST_RECIPE_LEFT_DELTA              1u /* 10 */
#define SEDGE_FAST_RECIPE_LAST_DELTA              2u /* 10 */
#define SEDGE_FAST_RECIPE_ABOVE_HIGH              3u /* 16 */
#define SEDGE_FAST_RECIPE_LEFT_CHANGED_LAST_DELTA 4u /* 20 */
#define SEDGE_FAST_RECIPE_COUNT                   5u

/* Column coding classes. */
#define SEDGE_FAST_CLASS_NORMAL 0u /* "same as above?", then the delta */
#define SEDGE_FAST_CLASS_STATIC 1u /* one shared "any changed?" per packet */
#define SEDGE_FAST_CLASS_ALWAYS 2u /* the delta directly, 0 included */
#define SEDGE_FAST_CLASS_COUNT  3u

/* Flag for sedge_fast_memory_bytes / sedge_fast_init: reserve room for the
 * epoch snapshot (needed by sedge_fast_set_epochs; doubles the model). */
#define SEDGE_FAST_EPOCHS 1u

/* A valid payload never makes the decoder read more than this many bytes
 * past its end (see sedge_fast_last_overrun). */
#define SEDGE_FAST_MAX_OVERRUN 7u

/* Memory block size, as a constant expression for static allocation.
 * `tables` is the total number of delta tables: 2 * len with the default
 * recipes, otherwise the sum over columns of the recipe's tables (at most
 * 20 * len). `epochs` is 0 or 1. Equal to sedge_fast_memory_bytes. */
#define SEDGE_FAST_MEMORY_BYTES(len, tables, epochs) \
    (8u + 128u + (1u + (epochs)) * \
     (((8u + 1032u * (size_t)(tables) + 137u * (size_t)(len)) + 7u) & ~(size_t)7u))

/* Largest payload of one packet of `len` bytes (a proven bound; typical
 * payloads are far smaller). */
#define SEDGE_FAST_MAX_PAYLOAD(len) (14u * (size_t)(len) + 8u)

/* Scratch memory for sedge_fast_learn_recipes. */
#define SEDGE_FAST_LEARN_SCRATCH_BYTES (8u + 20u * 1032u)

typedef struct sedge_fast sedge_fast;

/* Memory block size for packets of `len` bytes (1..=65536). `recipes` is
 * NULL (default recipe on every column) or `len` recipe bytes; `flags` is 0
 * or SEDGE_FAST_EPOCHS. Returns 0 for an invalid argument or overflow. */
size_t sedge_fast_memory_bytes(size_t len, const uint8_t *recipes,
                               unsigned flags);

/* Largest payload sedge_fast_compress can produce: SEDGE_FAST_MAX_PAYLOAD. */
size_t sedge_fast_max_payload(size_t len);

/* Create a session in `mem` (any alignment; `mem_bytes` at least
 * sedge_fast_memory_bytes(len, recipes, flags)). `recipes` and `classes`
 * are NULL (defaults: LEFT_CHANGED, NORMAL) or `len` bytes each; both ends
 * must use the same layout. On success *out is the session (inside `mem`).
 * Rust: FastPacketSession::new / with_recipes / with_layout. */
int sedge_fast_init(sedge_fast **out, void *mem, size_t mem_bytes,
                    size_t len, const uint8_t *recipes,
                    const uint8_t *classes, unsigned flags);

/* Clone `src` into another block of at least the same memory_bytes. */
int sedge_fast_copy(sedge_fast **out, void *mem, size_t mem_bytes,
                    const sedge_fast *src);

/* Learn from `n` historical packets (n * len contiguous bytes) before the
 * link starts; both ends must prime with the same packets. Must precede
 * sedge_fast_set_epochs (else SEDGE_FAST_E_STATE). */
int sedge_fast_prime(sedge_fast *s, const uint8_t *packets, size_t n);

/* Restart from the current state every `every` packets on both ends (the
 * Rust with_epochs). Needs SEDGE_FAST_EPOCHS at init. Resets the count. */
int sedge_fast_set_epochs(sedge_fast *s, uint64_t every);

/* Compress one packet of len bytes into out[0..cap); *out_len receives the
 * payload length. With cap >= sedge_fast_max_payload(len) it cannot fail.
 * SEDGE_FAST_E_BUFFER: the payload did not fit; the packet was still
 * learned (count advanced), so treat it as a lost packet. */
int sedge_fast_compress(sedge_fast *s, const uint8_t *packet, uint8_t *out,
                        size_t cap, size_t *out_len);

/* Decompress the next packet into packet[0..len). Any payload (garbage,
 * truncated, empty) decodes to some packet without error, as in Rust;
 * integrity is the link layer's job. */
int sedge_fast_decompress(sedge_fast *s, const uint8_t *payload, size_t n,
                          uint8_t *packet);

/* Decompress the packet with sender sequence number `index` (0-based).
 * After a gap, returns SEDGE_FAST_E_OUT_OF_SYNC until the next epoch
 * boundary, where decoding resumes; an index below sedge_fast_count is
 * also SEDGE_FAST_E_OUT_OF_SYNC. */
int sedge_fast_decompress_indexed(sedge_fast *s, uint64_t index,
                                  const uint8_t *payload, size_t n,
                                  uint8_t *packet);

size_t sedge_fast_packet_len(const sedge_fast *s);
/* Packets processed since init/prime/set_epochs: the next expected index. */
uint64_t sedge_fast_count(const sedge_fast *s);
/* Bytes the last decompress read past the end of its payload. More than
 * SEDGE_FAST_MAX_OVERRUN proves the payload truncated or corrupt (an
 * optional check; Rust's fast profile does not make it). */
size_t sedge_fast_last_overrun(const sedge_fast *s);
/* Model bytes (one copy of the state, the snapshot excluded). */
size_t sedge_fast_model_bytes(const sedge_fast *s);

/* Ground side: coding class per column from `n` historical packets (n * len
 * contiguous bytes) by how often it changed. A column that changed in a
 * fraction r of the packet pairs is STATIC if r < static_max_ppm / 1e6,
 * ALWAYS if r > always_min_ppm / 1e6, else NORMAL. Integer-only and equal
 * to the Rust learn_classes(len, h, static_max_ppm / 1e6,
 * always_min_ppm / 1e6) (typical: 10000, 900000). */
int sedge_fast_learn_classes(size_t len, const uint8_t *history, size_t n,
                             uint32_t static_max_ppm, uint32_t always_min_ppm,
                             uint8_t *classes);

/* Ground side: context recipe per column from `n` historical packets, by
 * the ideal cost of its changed bytes under every recipe (Rust
 * learn_recipes). The cost uses fixed-point log2 instead of f64, so a
 * near-tie may pick another recipe than Rust: that changes compression
 * slightly, never compatibility (the recipes are an input of init). Needs
 * SEDGE_FAST_LEARN_SCRATCH_BYTES of scratch memory. */
int sedge_fast_learn_recipes(size_t len, const uint8_t *history, size_t n,
                             void *scratch, size_t scratch_bytes,
                             uint8_t *recipes);

const char *sedge_fast_error_message(int code);

#ifdef __cplusplus
}
#endif

#endif /* SEDGE_FAST_H */
