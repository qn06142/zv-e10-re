#ifndef RAW_LIVE_SOURCE_H
#define RAW_LIVE_SOURCE_H
#include "raw_frame_source.h"

/* Internal adapter ABI, NOT a reconstructed Sony firmware structure.
 * The adapter must own a stable completed frame until release succeeds.
 * Neither DMM open nor a ping-pong index alone establishes such ownership. */
#define RAW_LIVE_ABI 1u
#define RAW_LIVE_READY_LINEAR_8BIT_BT601_LIMITED 0x0fu
#define RAW_LIVE_MAX_TIMEOUT_MS 10u
typedef struct {
    uint32_t physical;
    size_t bytes;                 /* accessible bytes from physical */
    size_t stride;
} raw_live_plane;
typedef struct {
    uintptr_t token;              /* nonzero, opaque stable lease */
    uint32_t sequence;
    uint32_t width, height;
    raw_frame_pixfmt_t format;    /* explicit, never inferred from DMM size */
    uint32_t flags;
    raw_live_plane plane[2];
} raw_live_frame;
typedef struct {
    const uint8_t *data;
    void *base;
    size_t length;
} raw_live_mapping;
typedef struct {
    uint32_t abi, size;
    /* Must honor timeout, return no lease on error, and never wait on GUI locks.
     * Defensive cleanup also handles an erroneous nonzero token on failure. */
    int (*acquire)(void *, uint32_t timeout_ms, raw_live_frame *);
    /* An error retains the token: retry is allowed; no new acquire until done. */
    int (*release)(void *, uintptr_t token);
    int (*map_readonly)(void *, const raw_live_plane *, size_t, raw_live_mapping *);
    int (*unmap)(void *, raw_live_mapping *);
} raw_live_ops;
typedef struct {
    raw_live_ops ops;
    void *opaque;
    uint32_t width, height, timeout_ms;
    int initialized;
    raw_live_frame leased;
    raw_live_mapping mapped[2];
} raw_live_source;

int raw_live_init(raw_live_source *, const raw_live_ops *, void *, uint32_t, uint32_t, uint32_t);
/* Serialized worker API. Must be called ONLY after USB source readiness.
 * It never submits USB events and never frees a producer's DMM allocation. */
int raw_live_fill(raw_live_source *, void *, size_t, uint32_t destination_physical, uint32_t *);
/* Retains unresolved mappings/lease on error; safe to retry. */
int raw_live_drain(raw_live_source *);
int raw_live_shutdown(raw_live_source *);
/* Diagnostic byte tunnel: copy exactly width*height*2 bytes from plane0+offset.
 * No format, stride, color or image-dimension interpretation; source still must
 * supply a completed stable lease and a bounded readable byte span. Not a Sony ABI. */
int raw_live_fill_opaque(raw_live_source *,void *,size_t,uint32_t,size_t,uint32_t *);


#ifdef RAW_LIVE_TARGET_ARM
int raw_live_target_map_readonly(void *, const raw_live_plane *, size_t, raw_live_mapping *);
int raw_live_target_unmap(void *, raw_live_mapping *);
#endif
#endif
