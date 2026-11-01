/* sedge_fast: the shannon-edge fast packet profile in portable C99.
 * Bit-exact port of src/packet_fast.rs and the parts of src/coder.rs it
 * uses. Every arithmetic step is on uint32_t (or narrower, explicitly cast),
 * so it behaves the same on 16-, 32- and 64-bit targets of either
 * endianness; uint64_t only holds packet counts.
 */
#include "sedge_fast.h"

#include <string.h>

/* Compile-time checks of the layout behind SEDGE_FAST_MEMORY_BYTES. */
#define SF_STATIC_ASSERT(name, cond) typedef char sf_assert_##name[(cond) ? 1 : -1]

/* Inlining hint for the hot helpers (speed); none when optimizing for size
 * (gcc and clang define __OPTIMIZE_SIZE__ at -Os). Override with
 * -DSEDGE_FAST_INLINE=... */
#ifdef SEDGE_FAST_INLINE
#define SF_INLINE SEDGE_FAST_INLINE
#elif defined(__OPTIMIZE_SIZE__)
#define SF_INLINE
#else
#define SF_INLINE inline
#endif

#define SF_INC 32u          /* frequency increment */
#define SF_LIMIT 32768u     /* total that triggers halving */
#define SF_HEADER 128u      /* bytes reserved for struct sedge_fast */
#define SF_MAGIC 0x53664331u

/* Tests only: count the symbols coded bit by bit (interval narrower than
 * the frequency total), to show the cross-checks exercise that path. */
#ifdef SEDGE_FAST_TEST_HOOKS
extern unsigned long sedge_fast_test_fallbacks;
#define SF_FALLBACK() (sedge_fast_test_fallbacks++)
#else
#define SF_FALLBACK() ((void)0)
#endif

/* Adaptive frequencies of the deltas, with a Fenwick tree. */
typedef struct {
    uint16_t f[256];
    uint16_t tree[257]; /* partial sums never exceed SF_LIMIT */
    uint16_t syms;      /* 255 (deltas 1..255) or 256 (deltas 0..255) */
    uint32_t total;
} sf_freq;

/* Per-column state. */
typedef struct {
    uint32_t base;      /* index of the column's first delta table */
    uint8_t run;        /* packets since the column last changed, <= 15 */
    uint8_t changed_last;
    uint8_t last_delta; /* delta of the last change (0 before the first) */
    uint8_t rc;         /* recipe | class << 4 */
} sf_col;

/* Scalar model state, first in the model region (snapshotted with it). */
typedef struct {
    uint16_t group[2];  /* static group's "changed?" probabilities */
    uint8_t group_last;
    uint8_t desynced;
    uint8_t pad[2];
} sf_mhdr;

struct sedge_fast {
    uint32_t magic;
    uint32_t len;
    uint32_t nfreq;
    uint8_t has_static;
    uint8_t has_origin_mem;
    uint8_t origin_set;
    uint8_t pad;
    uint64_t epoch;  /* epoch length in packets, 0 = none */
    uint64_t count;  /* packets processed */
    uint64_t phase;  /* count % epoch (kept incrementally) */
    size_t overrun;
    size_t used;       /* bytes from the session start */
    size_t model_size; /* bytes of one model copy */
    size_t origin_off; /* snapshot offset (model is at SF_HEADER) */
    size_t freq_off, same_off, cols_off, above_off; /* within the model */
};

SF_STATIC_ASSERT(freq_size, sizeof(sf_freq) == 1032u);
SF_STATIC_ASSERT(col_size, sizeof(sf_col) == 8u);
SF_STATIC_ASSERT(mhdr_size, sizeof(sf_mhdr) == 8u);
SF_STATIC_ASSERT(header_size, sizeof(struct sedge_fast) <= SF_HEADER);

/* Pointers into one model copy. */
typedef struct {
    sf_mhdr *h;
    sf_freq *freq;
    uint16_t *same; /* 64 contexts per column */
    sf_col *cols;
    uint8_t *above;
    uint32_t len;
    int has_static;
} sf_view;

static unsigned char *sf_bytes(sedge_fast *s) { return (unsigned char *)(void *)s; }

static sf_view sf_view_of(sedge_fast *s)
{
    sf_view v;
    unsigned char *m = sf_bytes(s) + SF_HEADER;
    v.h = (sf_mhdr *)(void *)m;
    v.freq = (sf_freq *)(void *)(m + s->freq_off);
    v.same = (uint16_t *)(void *)(m + s->same_off);
    v.cols = (sf_col *)(void *)(m + s->cols_off);
    v.above = m + s->above_off;
    v.len = s->len;
    v.has_static = s->has_static;
    return v;
}

/* ---------------------------------------------------------------- coder */

typedef struct {
    uint32_t x1, x2;
    uint8_t *out;
    size_t n, cap; /* bytes produced (may exceed cap: then not stored) */
} sf_enc;

typedef struct {
    uint32_t x1, x2, x;
    const uint8_t *in;
    size_t len, pos;
} sf_dec;

static SF_INLINE void enc_norm(sf_enc *e)
{
    while (((e->x1 ^ e->x2) & UINT32_C(0xff000000)) == 0u) {
        if (e->n < e->cap) {
            e->out[e->n] = (uint8_t)(e->x2 >> 24);
        }
        e->n++;
        e->x1 <<= 8;
        e->x2 = (e->x2 << 8) | 0xffu;
    }
}

static SF_INLINE void enc_bit(sf_enc *e, uint32_t bit, uint32_t p1)
{
    uint32_t xmid = e->x1 + ((e->x2 - e->x1) >> 12) * p1;
    if (bit != 0u) {
        e->x2 = xmid;
    } else {
        e->x1 = xmid + 1u;
    }
    enc_norm(e);
}

/* Returns 0, coding nothing, when the interval is narrower than total. */
static SF_INLINE int enc_freq(sf_enc *e, uint32_t cum, uint32_t freq, uint32_t total)
{
    uint32_t r = (e->x2 - e->x1) / total;
    if (r == 0u) {
        return 0;
    }
    e->x1 += r * cum;
    e->x2 = e->x1 + r * freq - 1u;
    enc_norm(e);
    return 1;
}

static void enc_push(sf_enc *e, uint8_t b)
{
    if (e->n < e->cap) {
        e->out[e->n] = b;
    }
    e->n++;
}

/* Rust Encoder::finish_short: the shortest byte string that, padded with
 * zeros, lies in [x1, x2]; then drop at most 4 trailing zero bytes. */
static void enc_finish(sf_enc *e)
{
    uint32_t k, i, dropped = 0;
    for (k = 1; k <= 4u; k++) {
        uint32_t mask = (k == 4u) ? 0u : ((UINT32_C(1) << (32u - 8u * k)) - 1u);
        uint32_t v;
        if ((e->x1 & mask) == 0u) {
            v = e->x1;
        } else if ((e->x1 | mask) == UINT32_C(0xffffffff)) {
            continue; /* rounding up reaches 2^32 > x2 */
        } else {
            v = (e->x1 | mask) + 1u;
        }
        if (v <= e->x2) {
            for (i = 0; i < k; i++) {
                enc_push(e, (uint8_t)(v >> (24u - 8u * i)));
            }
            break;
        }
    }
    while (dropped < 4u && e->n > 0u && e->n <= e->cap && e->out[e->n - 1u] == 0u) {
        e->n--;
        dropped++;
    }
}

static SF_INLINE uint32_t dec_byte(sf_dec *d)
{
    uint32_t b = d->pos < d->len ? (uint32_t)d->in[d->pos] : 0u;
    d->pos++;
    return b;
}

static void dec_init(sf_dec *d, const uint8_t *in, size_t len)
{
    int i;
    d->x1 = 0u;
    d->x2 = UINT32_C(0xffffffff);
    d->x = 0u;
    d->in = in;
    d->len = len;
    d->pos = 0u;
    for (i = 0; i < 4; i++) {
        d->x = (d->x << 8) | dec_byte(d);
    }
}

static SF_INLINE void dec_norm(sf_dec *d)
{
    while (((d->x1 ^ d->x2) & UINT32_C(0xff000000)) == 0u) {
        d->x1 <<= 8;
        d->x2 = (d->x2 << 8) | 0xffu;
        d->x = (d->x << 8) | dec_byte(d);
    }
}

static SF_INLINE uint32_t dec_bit(sf_dec *d, uint32_t p1)
{
    uint32_t xmid = d->x1 + ((d->x2 - d->x1) >> 12) * p1;
    uint32_t bit;
    if (d->x <= xmid) {
        d->x2 = xmid;
        bit = 1u;
    } else {
        d->x1 = xmid + 1u;
        bit = 0u;
    }
    dec_norm(d);
    return bit;
}

/* ---------------------------------------------------- frequency tables */

static void freq_rebuild(sf_freq *f)
{
    uint32_t i, total = 0;
    f->tree[0] = 0u;
    for (i = 1; i <= 256u; i++) {
        f->tree[i] = f->f[i - 1u];
    }
    for (i = 1; i <= 256u; i++) {
        uint32_t p = i + (i & (0u - i));
        total += f->f[i - 1u];
        if (p <= 256u) {
            f->tree[p] = (uint16_t)(f->tree[p] + f->tree[i]);
        }
    }
    f->total = total;
}

static void freq_init(sf_freq *f, uint32_t syms)
{
    uint32_t i;
    for (i = 0; i < 256u; i++) {
        f->f[i] = (uint16_t)(i < syms ? 1u : 0u);
    }
    f->syms = (uint16_t)syms;
    freq_rebuild(f);
}

/* The Fenwick walks below are written with masks instead of data-dependent
 * branches (which mispredict about once per level); they visit the same
 * nodes and compute the same values as the Rust loops. */

/* Sum of the frequencies of the symbols below s (s <= 255): the nodes of
 * the prefixes of s's bits, from the top bit down. */
static SF_INLINE uint32_t freq_cum(const sf_freq *f, uint32_t s)
{
    uint32_t c = 0, idx = 0, b;
    for (b = 8; b-- > 0u;) {
        uint32_t m = 0u - ((s >> b) & 1u);
        idx += (UINT32_C(1) << b) & m;
        c += (uint32_t)f->tree[idx] & m;
    }
    return c;
}

/* The symbol whose range contains v (v < total), and its cumulative start.
 * The Rust walk starts at mask 256, but tree[256] == total > v, so that
 * step is never taken and every later index stays below 256. */
static SF_INLINE uint32_t freq_find(const sf_freq *f, uint32_t v, uint32_t *cum_out)
{
    uint32_t pos = 0, cum = 0, mask;
    for (mask = 128u; mask != 0u; mask >>= 1) {
        uint32_t t = f->tree[pos + mask];
        uint32_t m = 0u - (uint32_t)(t <= v);
        pos += mask & m;
        v -= t & m;
        cum += t & m;
    }
    *cum_out = cum;
    return pos < (uint32_t)f->syms - 1u ? pos : (uint32_t)f->syms - 1u;
}

static SF_INLINE void freq_update(sf_freq *f, uint32_t s)
{
    uint32_t i, j;
    if (f->total + SF_INC > SF_LIMIT) {
        for (i = 0; i < f->syms; i++) {
            uint32_t h = (uint32_t)f->f[i] >> 1;
            f->f[i] = (uint16_t)(h != 0u ? h : 1u);
        }
        freq_rebuild(f);
    }
    f->f[s] = (uint16_t)(f->f[s] + SF_INC);
    f->total += SF_INC;
    /* j = s + 1, then j += lowbit(j) while j <= 256: at most 9 nodes; the
     * steps past 256 add 0 to tree[0] (never read) instead of branching. */
    j = s + 1u;
    for (i = 0; i < 9u; i++) {
        uint32_t in = 0u - (uint32_t)(j <= 256u);
        uint32_t idx = j & in;
        f->tree[idx] = (uint16_t)(f->tree[idx] + (SF_INC & in));
        j += j & (0u - j);
    }
}

static SF_INLINE void enc_symbol(sf_freq *f, uint32_t s, sf_enc *e)
{
    if (!enc_freq(e, freq_cum(f, s), f->f[s], f->total)) {
        uint32_t i;
        SF_FALLBACK();
        for (i = 8; i-- > 0u;) {
            enc_bit(e, (s >> i) & 1u, 2048u);
        }
    }
    freq_update(f, s);
}

static SF_INLINE uint32_t dec_symbol(sf_freq *f, sf_dec *d)
{
    uint32_t total = f->total;
    uint32_t r = (d->x2 - d->x1) / total;
    uint32_t s;
    if (r != 0u) {
        uint32_t cum, v = (d->x - d->x1) / r;
        if (v > total - 1u) {
            v = total - 1u;
        }
        s = freq_find(f, v, &cum);
        d->x1 += r * cum;
        d->x2 = d->x1 + r * f->f[s] - 1u;
        dec_norm(d);
    } else {
        uint32_t i;
        SF_FALLBACK();
        s = 0;
        for (i = 0; i < 8u; i++) {
            s = (s << 1) | dec_bit(d, 2048u);
        }
        if (s > (uint32_t)f->syms - 1u) {
            s = (uint32_t)f->syms - 1u;
        }
    }
    freq_update(f, s);
    return s;
}

/* --------------------------------------------------------------- model */

static SF_INLINE uint32_t sf_p1(uint32_t p16)
{
    uint32_t p1 = p16 >> 4;
    return p1 < 1u ? 1u : (p1 > 4095u ? 4095u : p1);
}

/* p16 += (target - p16) >> 4 with an arithmetic shift, target 0 or 65536. */
static SF_INLINE uint16_t sf_adapt(uint32_t p16, uint32_t bit)
{
    if (bit != 0u) {
        return (uint16_t)(p16 + ((UINT32_C(65536) - p16) >> 4));
    }
    return (uint16_t)(p16 - ((p16 + 15u) >> 4));
}

/* Size and sign class of a delta: 0 (none), 1, 2..3, 4..15, 16+; x2 sign. */
static SF_INLINE uint32_t delta_class(uint32_t d)
{
    uint32_t neg = d >= 128u ? 1u : 0u;
    uint32_t a = neg ? 256u - d : d;
    uint32_t b = a == 0u ? 0u : a == 1u ? 1u : a <= 3u ? 2u : a <= 15u ? 3u : 4u;
    return b * 2u + neg;
}

static uint32_t recipe_tables(uint32_t r)
{
    static const uint8_t t[SEDGE_FAST_RECIPE_COUNT] = {2, 10, 10, 16, 20};
    return t[r];
}

static SF_INLINE uint32_t recipe_context(uint32_t r, uint32_t lc, uint32_t ld,
                               uint32_t last, uint32_t above)
{
    switch (r) {
    case SEDGE_FAST_RECIPE_LEFT_CHANGED:
        return lc;
    case SEDGE_FAST_RECIPE_LEFT_DELTA:
        return delta_class(ld);
    case SEDGE_FAST_RECIPE_LAST_DELTA:
        return delta_class(last);
    case SEDGE_FAST_RECIPE_ABOVE_HIGH:
        return above >> 4;
    default:
        return lc * 10u + delta_class(last);
    }
}

#define SF_CLASS(c) ((uint32_t)(c)->rc >> 4)
#define SF_RECIPE(c) ((uint32_t)(c)->rc & 15u)

/* Code one packet (encoder). The caller copies the packet to `above`.
 * The coder state and the model pointers are copied to locals: byte stores
 * may alias anything reached through a pointer, which would keep them in
 * memory instead of registers. */
static void enc_packet(const sf_view *v, const uint8_t *pk, sf_enc *ep)
{
    uint32_t k, len = v->len, group_changed = 1u, lc = 0u, ld = 0u;
    sf_enc st = *ep, *e = &st;
    sf_col *cols = v->cols;
    sf_freq *freq = v->freq;
    uint16_t *samep = v->same;
    const uint8_t *above = v->above;
    if (v->has_static) {
        uint32_t g = v->h->group_last, p16 = v->h->group[g], changed = 0u;
        for (k = 0; k < len; k++) {
            if (SF_CLASS(&cols[k]) == SEDGE_FAST_CLASS_STATIC && pk[k] != above[k]) {
                changed = 1u;
                break;
            }
        }
        enc_bit(e, changed, sf_p1(p16));
        v->h->group[g] = sf_adapt(p16, changed);
        group_changed = changed;
        v->h->group_last = (uint8_t)changed;
    }
    for (k = 0; k < len; k++) {
        sf_col *c = &cols[k];
        uint32_t a = above[k], cls = SF_CLASS(c);
        uint32_t d = ((uint32_t)pk[k] - a) & 0xffu;
        uint32_t ctx, p16, same;
        if (cls == SEDGE_FAST_CLASS_STATIC && !group_changed) {
            lc = 0u;
            ld = 0u;
            continue;
        }
        if (cls == SEDGE_FAST_CLASS_ALWAYS) {
            enc_symbol(freq + c->base + recipe_context(SF_RECIPE(c), lc, ld, c->last_delta, a),
                       d, e);
            lc = d != 0u;
            ld = d;
            if (d != 0u) {
                c->last_delta = (uint8_t)d;
            }
            continue;
        }
        /* 1. Same as above? */
        ctx = k * 64u + (uint32_t)c->run * 4u + lc * 2u + c->changed_last;
        p16 = samep[ctx];
        same = d == 0u;
        enc_bit(e, same, sf_p1(p16));
        samep[ctx] = sf_adapt(p16, same);
        if (same) {
            c->run = (uint8_t)(c->run < 15u ? c->run + 1u : 15u);
            c->changed_last = 0u;
            lc = 0u;
            ld = 0u;
        } else {
            sf_freq *f = freq + c->base +
                         recipe_context(SF_RECIPE(c), lc, ld, c->last_delta, a);
            c->run = 0u;
            c->changed_last = 1u;
            /* 2. The delta from above, one symbol. */
            enc_symbol(f, d - 1u, e);
            lc = 1u;
            ld = d;
            c->last_delta = (uint8_t)d;
        }
    }
    *ep = st;
}

/* Decode one packet into `above` (in place) and `out` (locals: as above). */
static void dec_packet(const sf_view *v, sf_dec *dp, uint8_t *out)
{
    uint32_t k, len = v->len, group_changed = 1u, lc = 0u, ld = 0u;
    sf_dec st = *dp, *dc = &st;
    sf_col *cols = v->cols;
    sf_freq *freq = v->freq;
    uint16_t *samep = v->same;
    uint8_t *above = v->above;
    if (v->has_static) {
        uint32_t g = v->h->group_last, p16 = v->h->group[g];
        uint32_t bit = dec_bit(dc, sf_p1(p16));
        v->h->group[g] = sf_adapt(p16, bit);
        group_changed = bit;
        v->h->group_last = (uint8_t)bit;
    }
    for (k = 0; k < len; k++) {
        sf_col *c = &cols[k];
        uint32_t a = above[k], cls = SF_CLASS(c);
        uint32_t ctx, p16, same, d;
        if (cls == SEDGE_FAST_CLASS_STATIC && !group_changed) {
            lc = 0u;
            ld = 0u;
            out[k] = (uint8_t)a;
            continue;
        }
        if (cls == SEDGE_FAST_CLASS_ALWAYS) {
            d = dec_symbol(freq + c->base +
                               recipe_context(SF_RECIPE(c), lc, ld, c->last_delta, a),
                           dc);
            lc = d != 0u;
            ld = d;
            if (d != 0u) {
                c->last_delta = (uint8_t)d;
            }
            above[k] = out[k] = (uint8_t)(a + d);
            continue;
        }
        ctx = k * 64u + (uint32_t)c->run * 4u + lc * 2u + c->changed_last;
        p16 = samep[ctx];
        same = dec_bit(dc, sf_p1(p16));
        samep[ctx] = sf_adapt(p16, same);
        if (same) {
            c->run = (uint8_t)(c->run < 15u ? c->run + 1u : 15u);
            c->changed_last = 0u;
            lc = 0u;
            ld = 0u;
            out[k] = (uint8_t)a;
        } else {
            sf_freq *f = freq + c->base +
                         recipe_context(SF_RECIPE(c), lc, ld, c->last_delta, a);
            c->run = 0u;
            c->changed_last = 1u;
            d = dec_symbol(f, dc) + 1u;
            lc = 1u;
            ld = d;
            c->last_delta = (uint8_t)d;
            above[k] = out[k] = (uint8_t)(a + d);
        }
    }
    *dp = st;
}

/* ------------------------------------------------------------- session */

/* a % b for b > 0 without a 64-bit division (no libgcc helper). */
static uint64_t sf_mod64(uint64_t a, uint64_t b)
{
    uint64_t r = 0;
    uint32_t i;
    if (a < b) {
        return a;
    }
    if ((a >> 32) == 0u) {
        return (uint64_t)((uint32_t)a % (uint32_t)b);
    }
    for (i = 64; i-- > 0u;) {
        uint64_t top = r >> 63;
        r = (r << 1) | ((a >> i) & 1u);
        if (top != 0u || r >= b) {
            r -= b;
        }
    }
    return r;
}

typedef struct {
    size_t nfreq, freq_off, same_off, cols_off, above_off, model, used;
} sf_layout;

/* a * b + c, or 0 with *ok cleared on overflow. */
static size_t sf_mad(size_t a, size_t b, size_t c, int *ok)
{
    if (b != 0u && a > ((size_t)-1 - c) / b) {
        *ok = 0;
        return 0;
    }
    return a * b + c;
}

static int sf_layout_of(size_t len, const uint8_t *recipes, unsigned flags, sf_layout *l)
{
    size_t k, off;
    int ok = 1;
    if (len < 1u || len - 1u > SEDGE_FAST_MAX_LEN - 1u || (flags & ~SEDGE_FAST_EPOCHS) != 0u) {
        return 0;
    }
    l->nfreq = 0;
    for (k = 0; k < len; k++) {
        uint32_t r = recipes ? recipes[k] : SEDGE_FAST_RECIPE_LEFT_CHANGED;
        if (r >= SEDGE_FAST_RECIPE_COUNT) {
            return 0;
        }
        l->nfreq += recipe_tables(r);
    }
    l->freq_off = sizeof(sf_mhdr);
    l->same_off = sf_mad(l->nfreq, sizeof(sf_freq), l->freq_off, &ok);
    l->cols_off = sf_mad(len, 128u, l->same_off, &ok);
    l->above_off = sf_mad(len, sizeof(sf_col), l->cols_off, &ok);
    off = sf_mad(len, 1u, l->above_off, &ok);
    if (!ok || off > (size_t)-1 - 7u) {
        return 0;
    }
    l->model = (off + 7u) & ~(size_t)7u;
    l->used = sf_mad(l->model, (flags & SEDGE_FAST_EPOCHS) ? 2u : 1u, SF_HEADER, &ok);
    if (!ok || l->used > (size_t)-1 - 8u) {
        return 0;
    }
    return 1;
}

size_t sedge_fast_memory_bytes(size_t len, const uint8_t *recipes, unsigned flags)
{
    sf_layout l;
    if (!sf_layout_of(len, recipes, flags, &l)) {
        return 0;
    }
    return l.used + 8u; /* + alignment slack */
}

size_t sedge_fast_max_payload(size_t len) { return SEDGE_FAST_MAX_PAYLOAD(len); }

/* The 8-aligned start inside mem, or NULL if `need` bytes do not fit. */
static void *sf_align(void *mem, size_t mem_bytes, size_t need)
{
    size_t adj = (size_t)((8u - ((uintptr_t)mem & 7u)) & 7u);
    if (mem == NULL || mem_bytes < adj || mem_bytes - adj < need) {
        return NULL;
    }
    return (unsigned char *)mem + adj;
}

static int sf_valid(const sedge_fast *s) { return s != NULL && s->magic == SF_MAGIC; }

int sedge_fast_init(sedge_fast **out, void *mem, size_t mem_bytes, size_t len,
                    const uint8_t *recipes, const uint8_t *classes, unsigned flags)
{
    sf_layout l;
    sedge_fast *s;
    sf_view v;
    size_t k;
    uint32_t base = 0;
    if (out == NULL) {
        return SEDGE_FAST_E_ARGUMENT;
    }
    *out = NULL;
    if (mem == NULL || !sf_layout_of(len, recipes, flags, &l)) {
        return SEDGE_FAST_E_ARGUMENT;
    }
    if (classes != NULL) {
        for (k = 0; k < len; k++) {
            if (classes[k] >= SEDGE_FAST_CLASS_COUNT) {
                return SEDGE_FAST_E_ARGUMENT;
            }
        }
    }
    s = (sedge_fast *)sf_align(mem, mem_bytes, l.used);
    if (s == NULL) {
        return SEDGE_FAST_E_MEMORY;
    }
    memset(s, 0, SF_HEADER + l.model);
    s->magic = SF_MAGIC;
    s->len = (uint32_t)len;
    s->nfreq = (uint32_t)l.nfreq;
    s->has_origin_mem = (uint8_t)((flags & SEDGE_FAST_EPOCHS) != 0u);
    s->used = l.used;
    s->model_size = l.model;
    s->origin_off = SF_HEADER + l.model;
    s->freq_off = l.freq_off;
    s->same_off = l.same_off;
    s->cols_off = l.cols_off;
    s->above_off = l.above_off;
    v = sf_view_of(s);
    v.h->group[0] = v.h->group[1] = 32768u;
    for (k = 0; k < len; k++) {
        uint32_t r = recipes ? recipes[k] : SEDGE_FAST_RECIPE_LEFT_CHANGED;
        uint32_t cl = classes ? classes[k] : SEDGE_FAST_CLASS_NORMAL;
        uint32_t t, n = recipe_tables(r);
        sf_col *c = &v.cols[k];
        c->base = base;
        c->rc = (uint8_t)(r | cl << 4);
        for (t = 0; t < n; t++) {
            freq_init(&v.freq[base + t], cl == SEDGE_FAST_CLASS_ALWAYS ? 256u : 255u);
        }
        base += n;
        if (cl == SEDGE_FAST_CLASS_STATIC) {
            s->has_static = 1u;
        }
    }
    for (k = 0; k < len * 64u; k++) {
        v.same[k] = 32768u;
    }
    *out = s;
    return SEDGE_FAST_OK;
}

int sedge_fast_copy(sedge_fast **out, void *mem, size_t mem_bytes, const sedge_fast *src)
{
    sedge_fast *s;
    if (out == NULL) {
        return SEDGE_FAST_E_ARGUMENT;
    }
    *out = NULL;
    if (mem == NULL || !sf_valid(src)) {
        return SEDGE_FAST_E_ARGUMENT;
    }
    s = (sedge_fast *)sf_align(mem, mem_bytes, src->used);
    if (s == NULL) {
        return SEDGE_FAST_E_MEMORY;
    }
    if (s != src) {
        memmove(s, src, src->used);
    }
    *out = s;
    return SEDGE_FAST_OK;
}

static void sf_restart(sedge_fast *s, uint64_t index, uint64_t phase)
{
    memcpy(sf_bytes(s) + SF_HEADER, sf_bytes(s) + s->origin_off, s->model_size);
    s->count = index;
    s->phase = phase;
}

static void sf_begin_packet(sedge_fast *s)
{
    if (s->epoch != 0u && s->count != 0u && s->phase == 0u) {
        sf_restart(s, s->count, 0u);
    }
    s->count++;
    if (s->epoch != 0u && ++s->phase == s->epoch) {
        s->phase = 0u;
    }
}

int sedge_fast_prime(sedge_fast *s, const uint8_t *packets, size_t n)
{
    size_t i;
    sf_view v;
    if (!sf_valid(s) || (packets == NULL && n != 0u)) {
        return SEDGE_FAST_E_ARGUMENT;
    }
    if (s->origin_set) {
        return SEDGE_FAST_E_STATE;
    }
    v = sf_view_of(s);
    for (i = 0; i < n; i++) {
        const uint8_t *p = packets + i * s->len;
        sf_enc e; /* discards its output: only the model matters */
        e.x1 = 0u;
        e.x2 = UINT32_C(0xffffffff);
        e.out = NULL;
        e.n = 0u;
        e.cap = 0u;
        sf_begin_packet(s);
        enc_packet(&v, p, &e);
        memcpy(v.above, p, (size_t)s->len);
    }
    s->count = 0u;
    s->phase = 0u;
    return SEDGE_FAST_OK;
}

int sedge_fast_set_epochs(sedge_fast *s, uint64_t every)
{
    if (!sf_valid(s) || every == 0u) {
        return SEDGE_FAST_E_ARGUMENT;
    }
    if (!s->has_origin_mem) {
        return SEDGE_FAST_E_STATE;
    }
    s->epoch = every;
    s->count = 0u;
    s->phase = 0u;
    memcpy(sf_bytes(s) + s->origin_off, sf_bytes(s) + SF_HEADER, s->model_size);
    s->origin_set = 1u;
    return SEDGE_FAST_OK;
}

int sedge_fast_compress(sedge_fast *s, const uint8_t *packet, uint8_t *out, size_t cap,
                        size_t *out_len)
{
    sf_enc e;
    sf_view v;
    if (out_len != NULL) {
        *out_len = 0u;
    }
    if (!sf_valid(s) || packet == NULL || out_len == NULL || (out == NULL && cap != 0u)) {
        return SEDGE_FAST_E_ARGUMENT;
    }
    v = sf_view_of(s);
    sf_begin_packet(s);
    e.x1 = 0u;
    e.x2 = UINT32_C(0xffffffff);
    e.out = out;
    e.n = 0u;
    e.cap = cap;
    enc_packet(&v, packet, &e);
    memcpy(v.above, packet, (size_t)s->len);
    enc_finish(&e);
    if (e.n > cap) {
        return SEDGE_FAST_E_BUFFER;
    }
    *out_len = e.n;
    return SEDGE_FAST_OK;
}

int sedge_fast_decompress(sedge_fast *s, const uint8_t *payload, size_t n, uint8_t *packet)
{
    sf_dec d;
    sf_view v;
    if (!sf_valid(s) || packet == NULL || (payload == NULL && n != 0u)) {
        return SEDGE_FAST_E_ARGUMENT;
    }
    v = sf_view_of(s);
    sf_begin_packet(s);
    dec_init(&d, payload, n);
    dec_packet(&v, &d, packet);
    s->overrun = d.pos > n ? d.pos - n : 0u;
    return SEDGE_FAST_OK;
}

int sedge_fast_decompress_indexed(sedge_fast *s, uint64_t index, const uint8_t *payload,
                                  size_t n, uint8_t *packet)
{
    sf_mhdr *h;
    if (!sf_valid(s) || packet == NULL || (payload == NULL && n != 0u)) {
        return SEDGE_FAST_E_ARGUMENT;
    }
    h = sf_view_of(s).h;
    if (index < s->count) {
        return SEDGE_FAST_E_OUT_OF_SYNC;
    }
    if (index > s->count) {
        h->desynced = 1u;
        s->count = index;
    }
    if (h->desynced) {
        uint64_t phase = s->epoch != 0u ? sf_mod64(index, s->epoch) : 1u;
        if (s->epoch == 0u || phase != 0u) {
            s->count = index + 1u;
            if (s->epoch != 0u) {
                s->phase = phase + 1u == s->epoch ? 0u : phase + 1u;
            }
            return SEDGE_FAST_E_OUT_OF_SYNC;
        }
        sf_restart(s, index, 0u);
        sf_view_of(s).h->desynced = 0u;
    }
    return sedge_fast_decompress(s, payload, n, packet);
}

size_t sedge_fast_packet_len(const sedge_fast *s) { return sf_valid(s) ? (size_t)s->len : 0u; }

uint64_t sedge_fast_count(const sedge_fast *s) { return sf_valid(s) ? s->count : 0u; }

size_t sedge_fast_last_overrun(const sedge_fast *s) { return sf_valid(s) ? s->overrun : 0u; }

size_t sedge_fast_model_bytes(const sedge_fast *s) { return sf_valid(s) ? s->model_size : 0u; }

/* ------------------------------------------------------------- learning */

/* Ground-side functions; flight builds can leave them out with
 * -DSEDGE_FAST_NO_LEARN. */
#ifndef SEDGE_FAST_NO_LEARN


int sedge_fast_learn_classes(size_t len, const uint8_t *history, size_t n,
                             uint32_t static_max_ppm, uint32_t always_min_ppm, uint8_t *classes)
{
    size_t k, i;
    uint64_t pairs = n > 1u ? (uint64_t)n - 1u : 1u;
    if (len < 1u || classes == NULL || (history == NULL && n != 0u)) {
        return SEDGE_FAST_E_ARGUMENT;
    }
    for (k = 0; k < len; k++) {
        uint64_t c = 0, scaled;
        for (i = 1; i < n; i++) {
            c += history[(i - 1u) * len + k] != history[i * len + k];
        }
        scaled = c * UINT64_C(1000000);
        if (scaled < (uint64_t)static_max_ppm * pairs) {
            classes[k] = SEDGE_FAST_CLASS_STATIC;
        } else if (scaled > (uint64_t)always_min_ppm * pairs) {
            classes[k] = SEDGE_FAST_CLASS_ALWAYS;
        } else {
            classes[k] = SEDGE_FAST_CLASS_NORMAL;
        }
    }
    return SEDGE_FAST_OK;
}

/* log2(x) in Q24 fixed point for 1 <= x < 2^16, by repeated squaring. */
static uint32_t sf_log2_q24(uint32_t x)
{
    uint32_t ip = 0, frac = 0, i;
    uint64_t y;
    while ((x >> ip) > 1u) {
        ip++;
    }
    y = ((uint64_t)x << 30) >> ip; /* x / 2^ip in Q30, in [1, 2) */
    for (i = 0; i < 24u; i++) {
        y = (y * y) >> 30;
        frac <<= 1;
        if (y >= (UINT64_C(2) << 30)) {
            y >>= 1;
            frac |= 1u;
        }
    }
    return (ip << 24) | frac;
}

int sedge_fast_learn_recipes(size_t len, const uint8_t *history, size_t n, void *scratch,
                             size_t scratch_bytes, uint8_t *recipes)
{
    sf_freq *tables;
    size_t k, i;
    if (len < 1u || len - 1u > SEDGE_FAST_MAX_LEN - 1u || recipes == NULL ||
        (history == NULL && n != 0u)) {
        return SEDGE_FAST_E_ARGUMENT;
    }
    tables = (sf_freq *)sf_align(scratch, scratch_bytes, 20u * sizeof(sf_freq));
    if (tables == NULL) {
        return SEDGE_FAST_E_MEMORY;
    }
    /* Columns are independent: the left neighbour's context comes from the
     * packets, not from its model. */
    for (k = 0; k < len; k++) {
        uint64_t best = 0;
        uint32_t r, best_r = 0;
        for (r = 0; r < SEDGE_FAST_RECIPE_COUNT; r++) {
            uint32_t t, nt = recipe_tables(r), above = 0, last = 0;
            uint64_t cost = 0;
            for (t = 0; t < nt; t++) {
                freq_init(&tables[t], 255u);
            }
            for (i = 0; i < n; i++) {
                const uint8_t *p = history + i * len;
                uint32_t d = ((uint32_t)p[k] - above) & 0xffu;
                if (d != 0u) {
                    uint32_t ld = 0, s = d - 1u;
                    sf_freq *f;
                    if (k > 0u) {
                        uint32_t prev = i > 0u ? history[(i - 1u) * len + k - 1u] : 0u;
                        ld = ((uint32_t)p[k - 1u] - prev) & 0xffu;
                    }
                    f = &tables[recipe_context(r, ld != 0u, ld, last, above)];
                    cost += sf_log2_q24(f->total) - sf_log2_q24(f->f[s]);
                    freq_update(f, s);
                    last = d;
                }
                above = p[k];
            }
            if (r == 0u || cost < best) {
                best = cost;
                best_r = r;
            }
        }
        recipes[k] = (uint8_t)best_r;
    }
    return SEDGE_FAST_OK;
}

#endif /* SEDGE_FAST_NO_LEARN */

const char *sedge_fast_error_message(int code)
{
    switch (code) {
    case SEDGE_FAST_OK:
        return "ok";
    case SEDGE_FAST_E_ARGUMENT:
        return "invalid argument";
    case SEDGE_FAST_E_OUT_OF_SYNC:
        return "session out of sync: waiting for the next epoch";
    case SEDGE_FAST_E_MEMORY:
        return "memory block too small";
    case SEDGE_FAST_E_BUFFER:
        return "output buffer too small (packet consumed)";
    case SEDGE_FAST_E_STATE:
        return "invalid state: prime before epochs; epochs need SEDGE_FAST_EPOCHS";
    default:
        return "unknown error";
    }
}
