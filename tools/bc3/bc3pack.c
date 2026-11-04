/* bc3pack: a copy of a texture pack (XRTP v2) with the art in BC3 (DXT5).
 *
 *     bc3pack textures.pack textures_bc3.pack [max_entries]
 *
 * The source is only read. Every art entry (kind 0) whose size is whole 4x4
 * blocks is encoded level by level into BC3 and flagged XRTP_FLAG_BC3 (the
 * runtime uploads those as DXGI_FORMAT_BC3_UNORM); fonts, text and buttons
 * stay A8R8G8B8 so letters keep their edge. Entries sharing texels (one
 * page under two keys) share them in the copy too, and the old pack's dead
 * space is left behind.
 *
 * The encoder: colour endpoints on the block's principal axis (alpha-weighted,
 * so invisible texels do not pull the colour), refined once by least
 * squares; alpha in the 8-value mode between the block's min and max.
 * Built by tools\bc3\compilar.ps1 (clang-cl, /O2).
 */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define FLAG_BC3 0x10u
#define KIND_MASK 0x0Fu

typedef struct { uint64_t hash; uint32_t w, h, levels, flags; uint64_t off, src; } Entry;

static int cmp_off(const void *a, const void *b)
{
    const Entry *x = *(const Entry *const *)a, *y = *(const Entry *const *)b;
    return x->src < y->src ? -1 : x->src > y->src;
}

static int cmp_hash(const void *a, const void *b)
{
    const Entry *x = a, *y = b;
    return x->hash < y->hash ? -1 : x->hash > y->hash;
}

static uint16_t to565(const float c[3])
{
    int r = (int)floorf(c[0] * 31.0f / 255.0f + 0.5f), g = (int)floorf(c[1] * 63.0f / 255.0f + 0.5f);
    int b = (int)floorf(c[2] * 31.0f / 255.0f + 0.5f);
    r = r < 0 ? 0 : r > 31 ? 31 : r;
    g = g < 0 ? 0 : g > 63 ? 63 : g;
    b = b < 0 ? 0 : b > 31 ? 31 : b;
    return (uint16_t)(r << 11 | g << 5 | b);
}

static void from565(uint16_t v, float c[3])
{
    int r = v >> 11, g = v >> 5 & 63, b = v & 31;
    c[0] = (float)(r << 3 | r >> 2);
    c[1] = (float)(g << 2 | g >> 4);
    c[2] = (float)(b << 3 | b >> 2);
}

/* indices for endpoints e0, e1 (4-colour mode); returns the weighted error */
static float pick(const float px[16][3], const float wt[16], uint16_t c0, uint16_t c1, uint8_t idx[16])
{
    float a[3], b[3], pal[4][3], err = 0;
    int i, k, j;
    from565(c0, a);
    from565(c1, b);
    for (k = 0; k < 3; k++) {
        pal[0][k] = a[k];
        pal[1][k] = b[k];
        pal[2][k] = (2 * a[k] + b[k]) / 3;
        pal[3][k] = (a[k] + 2 * b[k]) / 3;
    }
    for (i = 0; i < 16; i++) {
        float best = 1e30f;
        for (j = 0; j < 4; j++) {
            float d0 = px[i][0] - pal[j][0], d1 = px[i][1] - pal[j][1], d2 = px[i][2] - pal[j][2];
            float d = d0 * d0 * 0.3f + d1 * d1 * 0.59f + d2 * d2 * 0.11f;
            if (d < best) {
                best = d;
                idx[i] = (uint8_t)j;
            }
        }
        err += best * wt[i];
    }
    return err;
}

static void color_block(const uint8_t *bgra[4], uint8_t out[8])
{
    float px[16][3], wt[16], mean[3] = {0, 0, 0}, sw = 0, cov[6] = {0}, axis[3] = {1, 1, 1};
    float lo = 1e30f, hi = -1e30f, e0[3], e1[3], err;
    uint8_t idx[16], idx2[16];
    uint16_t c0, c1;
    int i, k, it;
    uint32_t bits = 0;

    for (i = 0; i < 16; i++) {
        const uint8_t *p = bgra[i / 4] + (i % 4) * 4;
        px[i][0] = p[2];
        px[i][1] = p[1];
        px[i][2] = p[0];
        wt[i] = p[3] / 255.0f + 0.02f;
        for (k = 0; k < 3; k++)
            mean[k] += px[i][k] * wt[i];
        sw += wt[i];
    }
    for (k = 0; k < 3; k++)
        mean[k] /= sw;
    for (i = 0; i < 16; i++) {
        float d0 = px[i][0] - mean[0], d1 = px[i][1] - mean[1], d2 = px[i][2] - mean[2];
        cov[0] += wt[i] * d0 * d0; cov[1] += wt[i] * d0 * d1; cov[2] += wt[i] * d0 * d2;
        cov[3] += wt[i] * d1 * d1; cov[4] += wt[i] * d1 * d2; cov[5] += wt[i] * d2 * d2;
    }
    for (it = 0; it < 8; it++) {
        float x = cov[0] * axis[0] + cov[1] * axis[1] + cov[2] * axis[2];
        float y = cov[1] * axis[0] + cov[3] * axis[1] + cov[4] * axis[2];
        float z = cov[2] * axis[0] + cov[4] * axis[1] + cov[5] * axis[2];
        float n = sqrtf(x * x + y * y + z * z);
        if (n < 1e-6f)
            break;
        axis[0] = x / n; axis[1] = y / n; axis[2] = z / n;
    }
    for (i = 0; i < 16; i++) {
        float t;
        if (wt[i] < 0.05f)
            continue;           /* invisible: no say in the range */
        t = (px[i][0] - mean[0]) * axis[0] + (px[i][1] - mean[1]) * axis[1] + (px[i][2] - mean[2]) * axis[2];
        if (t < lo) lo = t;
        if (t > hi) hi = t;
    }
    if (lo > hi)
        lo = hi = 0;
    for (k = 0; k < 3; k++) {
        e0[k] = mean[k] + axis[k] * hi;
        e1[k] = mean[k] + axis[k] * lo;
    }
    c0 = to565(e0);
    c1 = to565(e1);
    err = pick(px, wt, c0, c1, idx);

    /* least squares on those indices: px ~ a*e0 + b*e1 */
    {
        static const float wa[4] = {1, 0, 2.0f / 3, 1.0f / 3};
        float aa = 0, ab = 0, bb = 0, ax[3] = {0}, bx[3] = {0}, det;
        for (i = 0; i < 16; i++) {
            float a = wa[idx[i]], b = 1 - a, w = wt[i];
            aa += w * a * a; ab += w * a * b; bb += w * b * b;
            for (k = 0; k < 3; k++) {
                ax[k] += w * a * px[i][k];
                bx[k] += w * b * px[i][k];
            }
        }
        det = aa * bb - ab * ab;
        if (fabsf(det) > 1e-4f) {
            float f0[3], f1[3], err2;
            uint16_t d0, d1;
            for (k = 0; k < 3; k++) {
                f0[k] = (ax[k] * bb - bx[k] * ab) / det;
                f1[k] = (bx[k] * aa - ax[k] * ab) / det;
            }
            d0 = to565(f0);
            d1 = to565(f1);
            err2 = pick(px, wt, d0, d1, idx2);
            if (err2 < err) {
                c0 = d0;
                c1 = d1;
                memcpy(idx, idx2, 16);
            }
        }
    }
    /* c0 > c1 keeps the 4-colour order (BC3 is 4-colour either way) */
    if (c0 < c1) {
        uint16_t t = c0;
        c0 = c1;
        c1 = t;
        for (i = 0; i < 16; i++)
            idx[i] = idx[i] < 2 ? (uint8_t)(1 - idx[i]) : (uint8_t)(5 - idx[i]);
    } else if (c0 == c1) {
        memset(idx, 0, 16);
    }
    for (i = 15; i >= 0; i--)
        bits = bits << 2 | idx[i];
    out[0] = (uint8_t)c0; out[1] = (uint8_t)(c0 >> 8);
    out[2] = (uint8_t)c1; out[3] = (uint8_t)(c1 >> 8);
    out[4] = (uint8_t)bits; out[5] = (uint8_t)(bits >> 8);
    out[6] = (uint8_t)(bits >> 16); out[7] = (uint8_t)(bits >> 24);
}

static void alpha_block(const uint8_t *bgra[4], uint8_t out[8])
{
    int a[16], i, j, lo = 255, hi = 0, pal[8];
    uint64_t bits = 0;
    for (i = 0; i < 16; i++) {
        a[i] = bgra[i / 4][(i % 4) * 4 + 3];
        if (a[i] < lo) lo = a[i];
        if (a[i] > hi) hi = a[i];
    }
    out[0] = (uint8_t)hi;
    out[1] = (uint8_t)lo;
    if (hi == lo) {
        memset(out + 2, 0, 6);
        return;
    }
    pal[0] = hi;
    pal[1] = lo;
    for (j = 1; j < 7; j++)
        pal[j + 1] = ((7 - j) * hi + j * lo + 3) / 7;
    for (i = 15; i >= 0; i--) {
        int best = 0, bd = 1 << 30;
        for (j = 0; j < 8; j++) {
            int d = abs(a[i] - pal[j]);
            if (d < bd) {
                bd = d;
                best = j;
            }
        }
        bits = bits << 3 | (uint64_t)best;
    }
    for (i = 0; i < 6; i++)
        out[2 + i] = (uint8_t)(bits >> (8 * i));
}

/* One level of w x h BGRA texels into BC3 blocks (edge blocks clamp). */
static void encode_level(const uint8_t *src, uint32_t w, uint32_t h, uint8_t *dst)
{
    uint32_t bx, by, r;
    uint8_t tmp[4][16];
    for (by = 0; by < (h + 3) / 4; by++)
        for (bx = 0; bx < (w + 3) / 4; bx++) {
            const uint8_t *rows[4];
            for (r = 0; r < 4; r++) {
                uint32_t y = by * 4 + r < h ? by * 4 + r : h - 1, c;
                for (c = 0; c < 4; c++) {
                    uint32_t x = bx * 4 + c < w ? bx * 4 + c : w - 1;
                    memcpy(tmp[r] + c * 4, src + ((size_t)y * w + x) * 4, 4);
                }
                rows[r] = tmp[r];
            }
            alpha_block(rows, dst);
            color_block(rows, dst + 8);
            dst += 16;
        }
}

static size_t raw_bytes(uint32_t w, uint32_t h, uint32_t levels)
{
    size_t n = 0;
    while (levels--) {
        n += (size_t)w * h * 4;
        w = w > 1 ? w / 2 : 1;
        h = h > 1 ? h / 2 : 1;
    }
    return n;
}

static size_t bc3_bytes(uint32_t w, uint32_t h, uint32_t levels)
{
    size_t n = 0;
    while (levels--) {
        n += (size_t)((w + 3) / 4) * ((h + 3) / 4) * 16;
        w = w > 1 ? w / 2 : 1;
        h = h > 1 ? h / 2 : 1;
    }
    return n;
}

int main(int argc, char **argv)
{
    FILE *in, *out;
    uint8_t hdr[32];
    uint32_t count, i, limit;
    uint64_t index_off, written = 32, raw_total = 0, bc3_total = 0;
    Entry *e, **by_off;
    uint8_t *buf = NULL, *enc = NULL;
    size_t cap = 0, ecap = 0;
    unsigned converted = 0, kept = 0;

    if (argc < 3) {
        fprintf(stderr, "uso: bc3pack origen.pack destino.pack [max_entradas]\n");
        return 2;
    }
    in = fopen(argv[1], "rb");
    if (!in || fread(hdr, 1, 32, in) != 32 || memcmp(hdr, "XRTP", 4)) {
        fprintf(stderr, "no es un pack: %s\n", argv[1]);
        return 1;
    }
    memcpy(&count, hdr + 8, 4);
    memcpy(&index_off, hdr + 16, 8);
    e = calloc(count, sizeof *e);
    by_off = calloc(count, sizeof *by_off);
    _fseeki64(in, (long long)index_off, SEEK_SET);
    for (i = 0; i < count; i++) {
        uint8_t r[32];
        if (fread(r, 1, 32, in) != 32)
            return 1;
        memcpy(&e[i].hash, r, 8);
        memcpy(&e[i].w, r + 8, 4);
        memcpy(&e[i].h, r + 12, 4);
        memcpy(&e[i].levels, r + 16, 4);
        memcpy(&e[i].flags, r + 20, 4);
        memcpy(&e[i].off, r + 24, 8);
        e[i].src = e[i].off;
        by_off[i] = &e[i];
    }
    limit = argc > 3 ? (uint32_t)atoi(argv[3]) : count;
    qsort(by_off, count, sizeof *by_off, cmp_off);
    out = fopen(argv[2], "wb");
    if (!out) {
        fprintf(stderr, "no puedo escribir %s\n", argv[2]);
        return 1;
    }
    fwrite(hdr, 1, 32, out);    /* rewritten at the end */
    for (i = 0; i < count; i++) {
        Entry *x = by_off[i];
        uint64_t src_off = x->off;
        size_t n = (x->flags & FLAG_BC3) ? bc3_bytes(x->w, x->h, x->levels) : raw_bytes(x->w, x->h, x->levels);
        int to_bc3 = !(x->flags & FLAG_BC3) && (x->flags & KIND_MASK) == 0
                     && !((x->w | x->h) & 3) && converted < limit;
        uint32_t j;
        if (i && by_off[i - 1]->src == x->src) {
            /* same texels as the previous key: share them */
            x->off = by_off[i - 1]->off;
            x->flags = by_off[i - 1]->flags;
            continue;
        }
        if (n > cap) {
            cap = n;
            buf = realloc(buf, cap);
        }
        _fseeki64(in, (long long)src_off, SEEK_SET);
        if (fread(buf, 1, n, in) != n) {
            fprintf(stderr, "entrada %016llX: lectura corta\n", (unsigned long long)x->hash);
            return 1;
        }
        x->off = written;
        if (to_bc3) {
            size_t m = bc3_bytes(x->w, x->h, x->levels), so = 0, dof = 0;
            uint32_t w = x->w, h = x->h;
            if (m > ecap) {
                ecap = m;
                enc = realloc(enc, ecap);
            }
            for (j = 0; j < x->levels; j++) {
                encode_level(buf + so, w, h, enc + dof);
                so += (size_t)w * h * 4;
                dof += (size_t)((w + 3) / 4) * ((h + 3) / 4) * 16;
                w = w > 1 ? w / 2 : 1;
                h = h > 1 ? h / 2 : 1;
            }
            fwrite(enc, 1, m, out);
            written += m;
            raw_total += n;
            bc3_total += m;
            x->flags |= FLAG_BC3;
            converted++;
        } else {
            fwrite(buf, 1, n, out);
            written += n;
            kept++;
        }
        if ((converted + kept) % 200 == 0)
            fprintf(stderr, "  %u/%u\n", i + 1, count);
    }
    qsort(e, count, sizeof *e, cmp_hash);
    for (i = 0; i < count; i++) {
        uint8_t r[32];
        memcpy(r, &e[i].hash, 8);
        memcpy(r + 8, &e[i].w, 4);
        memcpy(r + 12, &e[i].h, 4);
        memcpy(r + 16, &e[i].levels, 4);
        memcpy(r + 20, &e[i].flags, 4);
        memcpy(r + 24, &e[i].off, 8);
        fwrite(r, 1, 32, out);
    }
    memcpy(hdr + 16, &written, 8);
    _fseeki64(out, 0, SEEK_SET);
    fwrite(hdr, 1, 32, out);
    fclose(out);
    fclose(in);
    printf("%u en BC3 (%.2f GB -> %.2f GB), %u sin tocar; pack nuevo: %.2f GB\n", converted,
           raw_total / 1073741824.0, bc3_total / 1073741824.0, kept, (written + count * 32.0) / 1073741824.0);
    return 0;
}
