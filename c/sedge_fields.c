/* sedge_fields: shannon-edge record transforms in portable C99.
 * See sedge_fields.h and c/README.md. Mirrors src/fields.rs.
 *
 * All field arithmetic is on uint64_t, which wraps exactly like Rust's
 * wrapping i64 operations followed by a mask to the field width. Signed
 * values are sign-extended by OR-ing the high bits, the halving of a
 * relation is an arithmetic shift written as (s >> 1) | (s & 2^63), and no
 * signed integer is ever shifted, overflowed or narrowed out of range.
 */
#include "sedge_fields.h"

#include <string.h>

#define SFD_MAGIC   0x53524c31u /* "SRL1" */
#define SFD_HEADER  32u
#define SFD_TARGET  0x80u       /* internal flag: the field is a target */
#define SFD_TOP     ((uint64_t)1 << 63)

struct sedge_fields {
    uint32_t magic;
    uint32_t nf;        /* fields */
    uint32_t nr;        /* relations */
    uint32_t len;       /* record length */
    uint32_t has_delta; /* any field delta */
    uint8_t have_fwd;   /* prev_fwd holds a record (Rust prev_fwd.is_some()) */
    uint8_t have_inv;   /* prev_inv holds a record */
    uint8_t pad[10];
};

/* One field, 8 bytes. flags: the uplink bits 0-3 (delta cleared for opaque
 * fields, as Rust does) plus SFD_TARGET. */
typedef struct {
    uint32_t offset;
    uint8_t width;
    uint8_t flags;
    uint8_t pad[2];
} sfd_field;

/* One relation, 8 bytes; a and b are the raw uplink bytes. */
typedef struct {
    uint16_t t, i, j;
    uint8_t a, b;
} sfd_rel;

typedef char sfd_check_header[sizeof(struct sedge_fields) <= SFD_HEADER ? 1 : -1];
typedef char sfd_check_field[sizeof(sfd_field) == 8u ? 1 : -1];
typedef char sfd_check_rel[sizeof(sfd_rel) == 8u ? 1 : -1];

/* Block layout (after aligning to 8): header, fields, relations,
 * prev_fwd[len], prev_inv[len]. */
static sfd_field *sfd_fields(const sedge_fields *t)
{
    return (sfd_field *)(void *)((unsigned char *)(uintptr_t)t + SFD_HEADER);
}

static sfd_rel *sfd_rels(const sedge_fields *t)
{
    return (sfd_rel *)(void *)((unsigned char *)sfd_fields(t) + 8u * (size_t)t->nf);
}

static uint8_t *sfd_prev(const sedge_fields *t, int inv)
{
    uint8_t *p = (uint8_t *)(void *)((unsigned char *)sfd_rels(t) + 8u * (size_t)t->nr);
    return inv ? p + t->len : p;
}

static int sfd_valid(const sedge_fields *t)
{
    return t != NULL && t->magic == SFD_MAGIC;
}

/* ------------------------------------------------------------ field values */

/* Raw field bits, zero-extended (Rust Layout::get). */
static uint64_t sfd_get(const uint8_t *rec, const sfd_field *f)
{
    const uint8_t *p = rec + f->offset;
    uint64_t v = 0;
    uint32_t i, w = f->width;
    if (f->flags & SEDGE_FIELDS_BIG_ENDIAN) {
        for (i = 0; i < w; i++) {
            v = (v << 8) | p[i];
        }
    } else {
        for (i = w; i-- > 0u;) {
            v = (v << 8) | p[i];
        }
    }
    return v;
}

/* Store the low 8 * width bits of v (Rust Layout::put). */
static void sfd_put(uint8_t *rec, const sfd_field *f, uint64_t v)
{
    uint8_t *p = rec + f->offset;
    uint32_t i, w = f->width;
    if (f->flags & SEDGE_FIELDS_BIG_ENDIAN) {
        for (i = w; i-- > 0u; v >>= 8) {
            p[i] = (uint8_t)(v & 0xffu);
        }
    } else {
        for (i = 0; i < w; i++, v >>= 8) {
            p[i] = (uint8_t)(v & 0xffu);
        }
    }
}

/* All ones in the field's width (integer widths 1, 2, 4, 8). Constant
 * shifts only, so 32-bit CPUs need no 64-bit shift helper. */
static uint64_t sfd_mask(const sfd_field *f)
{
    switch (f->width) {
    case 1:
        return 0xffu;
    case 2:
        return 0xffffu;
    case 4:
        return 0xffffffffu;
    default:
        return ~(uint64_t)0;
    }
}

/* v (field bits) sign-extended to 64 bits if the field is signed, as a
 * two's-complement uint64_t (Rust Layout::value). v <= mask, so its sign
 * bit is set exactly when v > mask / 2. */
static uint64_t sfd_extend(uint64_t v, const sfd_field *f)
{
    uint64_t m = sfd_mask(f);
    if ((f->flags & SEDGE_FIELDS_SIGNED) && v > (m >> 1)) {
        v |= ~m; /* no-op for 64-bit fields */
    }
    return v;
}

/* Raw uplink byte as a sign-extended 64-bit two's-complement value. */
static uint64_t sfd_i8(uint8_t a)
{
    return (a & 0x80u) ? (uint64_t)a | ~(uint64_t)0xffu : (uint64_t)a;
}

/* floor((a * x_i + b * x_j) / 2), wrapping, as two's complement. */
static uint64_t sfd_pred(const sedge_fields *t, const uint8_t *rec, const sfd_rel *r)
{
    const sfd_field *f = sfd_fields(t);
    uint64_t s = sfd_i8(r->a) * sfd_extend(sfd_get(rec, &f[r->i]), &f[r->i]) +
                 sfd_i8(r->b) * sfd_extend(sfd_get(rec, &f[r->j]), &f[r->j]);
    return (s >> 1) | (s & SFD_TOP); /* arithmetic shift right by 1 */
}

/* --------------------------------------------------------------- loading */

static uint32_t sfd_u16(const uint8_t *b)
{
    return (uint32_t)b[0] | ((uint32_t)b[1] << 8);
}

/* Structural checks of an uplink: magic, field count, widths, flags and
 * exact length. Gives the counts and the record length. */
static int sfd_scan(const uint8_t *b, size_t n, uint32_t *nf, uint32_t *nr, uint32_t *len)
{
    static const uint8_t magic[8] = {'S', 'E', 'D', 'G', 'R', 'E', 'L', '1'};
    uint32_t f, k, w, fl, sum = 0;
    size_t i, rest;
    if (n < 12u || b == NULL) {
        return 0;
    }
    for (i = 0; i < 8u; i++) {
        if (b[i] != magic[i]) {
            return 0;
        }
    }
    f = sfd_u16(b + 8);
    if (f == 0u || (n - 12u) / 2u < f) {
        return 0;
    }
    for (k = 0; k < f; k++) {
        w = b[10u + 2u * (size_t)k];
        fl = b[11u + 2u * (size_t)k];
        if (w == 0u || (fl >> 4) != 0u ||
            ((fl & SEDGE_FIELDS_INTEGER) && w != 1u && w != 2u && w != 4u && w != 8u)) {
            return 0;
        }
        sum += w;
    }
    i = 10u + 2u * (size_t)f;
    rest = n - 12u - 2u * (size_t)f;
    *nr = sfd_u16(b + i);
    if (rest % 8u != 0u || rest / 8u != *nr) {
        return 0;
    }
    *nf = f;
    *len = sum;
    return 1;
}

/* Bytes needed, as uint32_t (at most about 34.6 MB). */
static uint32_t sfd_need(uint32_t nf, uint32_t nr, uint32_t len)
{
    return 40u + 8u * nf + 8u * nr + 2u * len;
}

size_t sedge_fields_memory_bytes(const uint8_t *uplink, size_t n)
{
    uint32_t nf, nr, len, need;
    if (!sfd_scan(uplink, n, &nf, &nr, &len)) {
        return 0;
    }
    need = sfd_need(nf, nr, len);
#if SIZE_MAX < 0xffffffffu
    if (need > SIZE_MAX) {
        return 0;
    }
#endif
    return (size_t)need;
}

int sedge_fields_init(sedge_fields **out, void *mem, size_t mem_bytes,
                      const uint8_t *uplink, size_t n)
{
    uint32_t nf, nr, len, need, k, fl;
    size_t adj, at;
    sedge_fields *t;
    sfd_field *f;
    sfd_rel *r;
    if (out == NULL) {
        return SEDGE_FIELDS_E_ARGUMENT;
    }
    *out = NULL;
    if (mem == NULL || (uplink == NULL && n != 0u)) {
        return SEDGE_FIELDS_E_ARGUMENT;
    }
    if (!sfd_scan(uplink, n, &nf, &nr, &len)) {
        return SEDGE_FIELDS_E_BAD_MODEL;
    }
    need = sfd_need(nf, nr, len);
#if SIZE_MAX < 0xffffffffu
    if (need > SIZE_MAX) {
        return SEDGE_FIELDS_E_MEMORY;
    }
#endif
    if (mem_bytes < (size_t)need) {
        return SEDGE_FIELDS_E_MEMORY;
    }
    adj = (size_t)((8u - ((uintptr_t)mem & 7u)) & 7u);
    t = (sedge_fields *)(void *)((unsigned char *)mem + adj);
    memset(t, 0, SFD_HEADER); /* magic 0: invalid until fully checked */
    t->nf = nf;
    t->nr = nr;
    t->len = len;
    f = sfd_fields(t);
    r = sfd_rels(t);
    for (k = 0, len = 0; k < nf; k++) {
        f[k].offset = len;
        f[k].width = uplink[10u + 2u * (size_t)k];
        fl = uplink[11u + 2u * (size_t)k];
        if (!(fl & SEDGE_FIELDS_INTEGER)) {
            fl &= ~SEDGE_FIELDS_DELTA; /* Rust: delta && integer */
        }
        f[k].flags = (uint8_t)fl;
        f[k].pad[0] = f[k].pad[1] = 0;
        len += f[k].width;
        if (fl & SEDGE_FIELDS_DELTA) {
            t->has_delta = 1;
        }
    }
    at = 12u + 2u * (size_t)nf;
    for (k = 0; k < nr; k++, at += 8u) {
        uint32_t tg = sfd_u16(uplink + at), i = sfd_u16(uplink + at + 2u),
                 j = sfd_u16(uplink + at + 4u);
        if (tg >= nf || i >= nf || j >= nf || !(f[tg].flags & SEDGE_FIELDS_INTEGER) ||
            !(f[i].flags & SEDGE_FIELDS_INTEGER) || !(f[j].flags & SEDGE_FIELDS_INTEGER) ||
            tg == i || tg == j || (f[tg].flags & SFD_TARGET)) {
            return SEDGE_FIELDS_E_BAD_MODEL;
        }
        f[tg].flags = (uint8_t)(f[tg].flags | SFD_TARGET);
        r[k].t = (uint16_t)tg;
        r[k].i = (uint16_t)i;
        r[k].j = (uint16_t)j;
        r[k].a = uplink[at + 6u];
        r[k].b = uplink[at + 7u];
    }
    /* Predictors must not be targets, so the inverse never reads a field
     * it has not restored. */
    for (k = 0; k < nr; k++) {
        if ((f[r[k].i].flags | f[r[k].j].flags) & SFD_TARGET) {
            return SEDGE_FIELDS_E_BAD_MODEL;
        }
    }
    memset(sfd_prev(t, 0), 0, 2u * (size_t)t->len);
    t->magic = SFD_MAGIC;
    *out = t;
    return SEDGE_FIELDS_OK;
}

/* ------------------------------------------------------ forward / inverse */

int sedge_fields_forward(sedge_fields *t, const uint8_t *rec, size_t len, uint8_t *out)
{
    const sfd_field *f;
    const sfd_rel *r;
    uint8_t *prev;
    uint32_t k;
    if (!sfd_valid(t) || rec == NULL || out == NULL || len != (size_t)t->len) {
        return SEDGE_FIELDS_E_ARGUMENT;
    }
    if (out != rec) {
        memmove(out, rec, len);
    }
    /* Work in out only: relations read their predictors and their own
     * target, and no target is a predictor or used twice, so every value
     * read is still the original. */
    f = sfd_fields(t);
    r = sfd_rels(t);
    for (k = 0; k < t->nr; k++) {
        const sfd_field *ft = &f[r[k].t];
        uint64_t p = sfd_pred(t, out, &r[k]);
        sfd_put(out, ft, (sfd_get(out, ft) - p) & sfd_mask(ft));
    }
    if (t->has_delta) {
        prev = sfd_prev(t, 0);
        for (k = 0; k < t->nf; k++) {
            if (f[k].flags & SEDGE_FIELDS_DELTA) {
                uint64_t m = sfd_mask(&f[k]), cur = sfd_get(out, &f[k]);
                if (t->have_fwd) {
                    /* zigzag((cur - prev) mod 2^bits, as a signed value) */
                    uint64_t d = (cur - sfd_get(prev, &f[k])) & m;
                    uint64_t neg = d > (m >> 1) ? ~(uint64_t)0 : 0u;
                    sfd_put(out, &f[k], ((d << 1) ^ neg) & m);
                }
                sfd_put(prev, &f[k], cur);
            }
        }
        t->have_fwd = 1;
    }
    return SEDGE_FIELDS_OK;
}

int sedge_fields_inverse(sedge_fields *t, const uint8_t *rec, size_t len, uint8_t *out)
{
    const sfd_field *f;
    const sfd_rel *r;
    uint8_t *prev;
    uint32_t k;
    if (!sfd_valid(t) || rec == NULL || out == NULL || len != (size_t)t->len) {
        return SEDGE_FIELDS_E_ARGUMENT;
    }
    if (out != rec) {
        memmove(out, rec, len);
    }
    f = sfd_fields(t);
    r = sfd_rels(t);
    if (t->has_delta) {
        prev = sfd_prev(t, 1);
        for (k = 0; k < t->nf; k++) {
            if (f[k].flags & SEDGE_FIELDS_DELTA) {
                uint64_t v = sfd_get(out, &f[k]);
                if (t->have_inv) {
                    uint64_t d = (v >> 1) ^ (0u - (v & 1u)); /* unzigzag */
                    v = (sfd_get(prev, &f[k]) + d) & sfd_mask(&f[k]);
                    sfd_put(out, &f[k], v);
                }
                sfd_put(prev, &f[k], v);
            }
        }
        t->have_inv = 1;
    }
    for (k = t->nr; k-- > 0u;) {
        const sfd_field *ft = &f[r[k].t];
        uint64_t p = sfd_pred(t, out, &r[k]);
        sfd_put(out, ft, (sfd_get(out, ft) + p) & sfd_mask(ft));
    }
    return SEDGE_FIELDS_OK;
}

void sedge_fields_reset(sedge_fields *t)
{
    if (sfd_valid(t)) {
        t->have_fwd = 0;
        t->have_inv = 0;
    }
}

/* ------------------------------------------------------------ serialising */

static void sfd_put16(uint8_t *b, uint32_t v)
{
    b[0] = (uint8_t)(v & 0xffu);
    b[1] = (uint8_t)((v >> 8) & 0xffu);
}

int sedge_fields_to_bytes(const sedge_fields *t, uint8_t *out, size_t cap, size_t *out_len)
{
    static const uint8_t magic[8] = {'S', 'E', 'D', 'G', 'R', 'E', 'L', '1'};
    const sfd_field *f;
    const sfd_rel *r;
    uint32_t k;
    size_t need, at;
    if (out_len != NULL) {
        *out_len = 0u;
    }
    if (!sfd_valid(t) || out_len == NULL || (out == NULL && cap != 0u)) {
        return SEDGE_FIELDS_E_ARGUMENT;
    }
    /* Fits size_t: the block holding the transform is larger. */
    need = SEDGE_FIELDS_UPLINK_BYTES(t->nf, t->nr);
    *out_len = need;
    if (cap < need) {
        return SEDGE_FIELDS_E_BUFFER;
    }
    f = sfd_fields(t);
    r = sfd_rels(t);
    memcpy(out, magic, 8u);
    sfd_put16(out + 8, t->nf);
    for (k = 0; k < t->nf; k++) {
        out[10u + 2u * (size_t)k] = f[k].width;
        out[11u + 2u * (size_t)k] = (uint8_t)(f[k].flags & 0x0fu);
    }
    at = 10u + 2u * (size_t)t->nf;
    sfd_put16(out + at, t->nr);
    at += 2u;
    for (k = 0; k < t->nr; k++, at += 8u) {
        sfd_put16(out + at, r[k].t);
        sfd_put16(out + at + 2u, r[k].i);
        sfd_put16(out + at + 4u, r[k].j);
        out[at + 6u] = r[k].a;
        out[at + 7u] = r[k].b;
    }
    return SEDGE_FIELDS_OK;
}

/* ------------------------------------------------------------- accessors */

size_t sedge_fields_record_len(const sedge_fields *t)
{
    return sfd_valid(t) ? (size_t)t->len : 0u;
}

size_t sedge_fields_field_count(const sedge_fields *t)
{
    return sfd_valid(t) ? (size_t)t->nf : 0u;
}

size_t sedge_fields_relation_count(const sedge_fields *t)
{
    return sfd_valid(t) ? (size_t)t->nr : 0u;
}

int sedge_fields_get_field(const sedge_fields *t, size_t k, sedge_fields_field *f)
{
    const sfd_field *g;
    if (!sfd_valid(t) || f == NULL || k >= (size_t)t->nf) {
        return SEDGE_FIELDS_E_ARGUMENT;
    }
    g = &sfd_fields(t)[k];
    f->offset = g->offset;
    f->width = g->width;
    f->integer = (g->flags & SEDGE_FIELDS_INTEGER) != 0;
    f->is_signed = (g->flags & SEDGE_FIELDS_SIGNED) != 0;
    f->big_endian = (g->flags & SEDGE_FIELDS_BIG_ENDIAN) != 0;
    f->delta = (g->flags & SEDGE_FIELDS_DELTA) != 0;
    return SEDGE_FIELDS_OK;
}

static int8_t sfd_to_i8(uint8_t a)
{
    return (int8_t)(a < 128u ? (int)a : (int)a - 256);
}

int sedge_fields_get_relation(const sedge_fields *t, size_t k, sedge_fields_relation *r)
{
    const sfd_rel *s;
    if (!sfd_valid(t) || r == NULL || k >= (size_t)t->nr) {
        return SEDGE_FIELDS_E_ARGUMENT;
    }
    s = &sfd_rels(t)[k];
    r->target = s->t;
    r->i = s->i;
    r->j = s->j;
    r->a = sfd_to_i8(s->a);
    r->b = sfd_to_i8(s->b);
    return SEDGE_FIELDS_OK;
}

const char *sedge_fields_error_message(int code)
{
    switch (code) {
    case SEDGE_FIELDS_OK:
        return "ok";
    case SEDGE_FIELDS_E_ARGUMENT:
        return "invalid argument";
    case SEDGE_FIELDS_E_BAD_MODEL:
        return "invalid record transform";
    case SEDGE_FIELDS_E_MEMORY:
        return "memory block too small";
    case SEDGE_FIELDS_E_BUFFER:
        return "output buffer too small";
    default:
        return "unknown error";
    }
}
