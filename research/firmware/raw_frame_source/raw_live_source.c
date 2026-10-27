#include "raw_live_source.h"

static int needed(size_t stride, size_t row, uint32_t rows, size_t *n) {
    if (!rows || stride < row || !row) return RAW_FRAME_ERR_INVALID_PARAM;
    if ((size_t)(rows - 1) > (SIZE_MAX - row) / stride) return RAW_FRAME_ERR_INVALID_PARAM;
    *n = (size_t)(rows - 1) * stride + row;
    return RAW_FRAME_OK;
}
static int range(uint32_t start, size_t n) {
    return start && n && n <= UINT32_MAX - start;
}
static int overlap(uint32_t a, size_t n, uint32_t b, size_t m) {
    return a < b + m && b < a + n;
}
int raw_live_init(raw_live_source *s, const raw_live_ops *ops, void *opaque,
                  uint32_t w, uint32_t h, uint32_t timeout) {
    if (!s || !ops || ops->abi != RAW_LIVE_ABI || ops->size != sizeof(*ops) ||
        !ops->acquire || !ops->release || !ops->map_readonly || !ops->unmap ||
        !w || !h || (w & 1) || w > 640 || h > 480 ||
        !timeout || timeout > RAW_LIVE_MAX_TIMEOUT_MS)
        return RAW_FRAME_ERR_INVALID_PARAM;
    /* Caller zero-initializes context. Rebinding an active lease is forbidden. */
    if (s->initialized || s->leased.token || s->mapped[0].base || s->mapped[1].base)
        return RAW_FRAME_ERR_DEVICE_BUSY;
    s->ops = *ops; s->opaque = opaque; s->width = w; s->height = h;
    s->timeout_ms = timeout; s->initialized = 1;
    return RAW_FRAME_OK;
}
int raw_live_drain(raw_live_source *s) {
    if (!s || !s->initialized) return RAW_FRAME_ERR_NOT_INIT;
    /* Keep the upstream lease while ANY CPU mapping remains. */
    for (int i = 1; i >= 0; --i) {
        if (s->mapped[i].base) {
            int e = s->ops.unmap(s->opaque, &s->mapped[i]);
            if (e) return e;
            s->mapped[i] = (raw_live_mapping){0};
        }
    }
    if (s->leased.token) {
        int e = s->ops.release(s->opaque, s->leased.token);
        if (e) return e;
        s->leased = (raw_live_frame){0};
    }
    return RAW_FRAME_OK;
}
int raw_live_shutdown(raw_live_source *s) {
    int e = raw_live_drain(s);
    if (!e) s->initialized = 0;
    return e;
}
static int validate(raw_live_source *s, uint32_t dst, size_t out, size_t n[2], int *planes) {
    raw_live_frame *f = &s->leased;
    if (!f->token || f->flags != RAW_LIVE_READY_LINEAR_8BIT_BT601_LIMITED ||
        f->width != s->width || f->height != s->height)
        return RAW_FRAME_ERR_UNSUPPORTED_FMT;
    *planes = f->format == RAW_FRAME_PIXFMT_YUY2 ? 1 : 2;
    if (f->format != RAW_FRAME_PIXFMT_YUY2 && f->format != RAW_FRAME_PIXFMT_NV16 &&
        f->format != RAW_FRAME_PIXFMT_NV12) return RAW_FRAME_ERR_UNSUPPORTED_FMT;
    if (f->format == RAW_FRAME_PIXFMT_NV12 && (f->height & 1))
        return RAW_FRAME_ERR_UNSUPPORTED_FMT;
    for (int i = 0; i < *planes; ++i) {
        size_t row = f->width * (f->format == RAW_FRAME_PIXFMT_YUY2 ? 2u : 1u);
        uint32_t rows = i && f->format == RAW_FRAME_PIXFMT_NV12 ? f->height / 2 : f->height;
        int e = needed(f->plane[i].stride, row, rows, &n[i]);
        if (e || f->plane[i].bytes < n[i] || !range(f->plane[i].physical, n[i]) ||
            overlap(f->plane[i].physical, n[i], dst, out))
            return RAW_FRAME_ERR_INVALID_PARAM;
    }
    if (*planes == 2 && overlap(f->plane[0].physical, n[0], f->plane[1].physical, n[1]))
        return RAW_FRAME_ERR_INVALID_PARAM;
    return RAW_FRAME_OK;
}
int raw_live_fill(raw_live_source *s, void *dst, size_t bytes, uint32_t physical, uint32_t *sequence) {
    if (!s || !s->initialized) return RAW_FRAME_ERR_NOT_INIT;
    size_t output = (size_t)s->width * s->height * 2u;
    if (!dst || !sequence || bytes < output || !range(physical, output))
        return RAW_FRAME_ERR_INVALID_PARAM;
    int e = raw_live_drain(s);
    if (e) return e;
    s->leased = (raw_live_frame){0};
    e = s->ops.acquire(s->opaque, s->timeout_ms, &s->leased);
    size_t n[2] = {0}; int planes = 0;
    if (!e) e = validate(s, physical, output, n, &planes);
    for (int i = 0; !e && i < planes; ++i) {
        e = s->ops.map_readonly(s->opaque, &s->leased.plane[i], n[i], &s->mapped[i]);
        if (!e && (!s->mapped[i].base || !s->mapped[i].data || s->mapped[i].length < n[i]))
            e = RAW_FRAME_ERR_MMAP_FAILED;
    }
    uint32_t seq = s->leased.sequence;
    if (!e) {
        raw_live_frame *f = &s->leased;
        size_t stride = (size_t)s->width * 2u;
        if (f->format == RAW_FRAME_PIXFMT_YUY2)
            e = raw_frame_copy_yuy2(s->mapped[0].data, f->plane[0].stride, dst, stride, f->width, f->height);
        else if (f->format == RAW_FRAME_PIXFMT_NV16)
            e = raw_frame_convert_nv16_to_yuy2(s->mapped[0].data, f->plane[0].stride,
                s->mapped[1].data, f->plane[1].stride, dst, stride, f->width, f->height);
        else e = raw_frame_convert_nv12_to_yuy2(s->mapped[0].data, f->plane[0].stride,
                s->mapped[1].data, f->plane[1].stride, dst, stride, f->width, f->height);
        if (!e) raw_frame_memory_barrier();
    }
    int cleanup = raw_live_drain(s);
    if (cleanup) return cleanup;
    if (!e) *sequence = seq;
    return e;
}

#ifdef RAW_LIVE_TARGET_ARM
extern int open(const char *, int, ...), close(int), munmap(void *, unsigned long);
extern void *mmap(void *, unsigned long, int, int, int, long);
int raw_live_target_map_readonly(void *opaque, const raw_live_plane *p, size_t n, raw_live_mapping *m) {
    (void)opaque;
    if (!p || !m || !range(p->physical, n) || p->bytes < n)
        return RAW_FRAME_ERR_INVALID_PARAM;
    size_t delta = p->physical & 4095u;
    if (n > SIZE_MAX - delta - 4095u) return RAW_FRAME_ERR_INVALID_PARAM;
    size_t length = (n + delta + 4095u) & ~(size_t)4095u;
    if (length > UINT32_MAX - (p->physical & ~4095u)) return RAW_FRAME_ERR_INVALID_PARAM;
    int fd = open("/dev/stream", 0); /* O_RDONLY, no writes to camera-owned frame */
    if (fd < 0) return RAW_FRAME_ERR_IO;
    void *base = mmap(0, length, 1, 1, fd, (long)(p->physical & ~4095u));
    close(fd);
    if (base == (void *)-1) return RAW_FRAME_ERR_MMAP_FAILED;
    m->base = base; m->data = (const uint8_t *)base + delta; m->length = length;
    return RAW_FRAME_OK;
}
int raw_live_target_unmap(void *opaque, raw_live_mapping *m) {
    (void)opaque;
    return munmap(m->base, m->length) ? RAW_FRAME_ERR_IO : RAW_FRAME_OK;
}
#endif
