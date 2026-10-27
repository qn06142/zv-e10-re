/**
 * @file raw_live_sony.c
 * @brief Concrete Sony Completed-YC Frame Source Backend Implementation.
 *
 * Implements the concrete Sony live-source backend conforming to raw_live_ops,
 * integrating with Revision 2.5 transport while enforcing USB completion fences,
 * 10 ms timeout caps, lease retention semantics, and pure scalar ARMv7-A execution.
 */

#include "raw_live_sony.h"
#include <string.h>

#ifdef RAW_LIVE_TARGET_ARM
extern int open(const char *, int, ...);
extern int close(int);
extern void *mmap(void *, unsigned long, int, int, int, long);
extern int munmap(void *, unsigned long);
#endif


/* Forward declarations */
static int sony_validate_metadata(const raw_live_sony_context_t *ctx);

/* =========================================================================
 * 1. Context Lifecycle and Configuration
 * ========================================================================= */

int raw_live_sony_init(raw_live_sony_context_t *ctx) {
    if (!ctx) {
        return RAW_FRAME_ERR_INVALID_PARAM;
    }
    memset(ctx, 0, sizeof(*ctx));
    ctx->target_queue_id = SONY_VDF_QUEUE_ID;
    ctx->pin_key = SONY_VDF_PIN_KEY;
    ctx->owned_staging_unit = SONY_DMM_UNIT_UVC_WORKSPACE;
    ctx->staging_physical = 0x15b00000u; /* Default DMM Unit 0x276 physical base */
    ctx->is_subscribed = 1;

    /* Initialize canonical 640x480 NV16 BT.601 limited-range metadata defaults */
    ctx->last_size_info = (PIN_YC_IMAGE_SIZE_INFO){
        .image_attach = 1,
        .unit_type = 0x1ddu,
        .unit_handle = 0,
        .record_size_x = SONY_FRAME_WIDTH,
        .record_size_y = SONY_FRAME_HEIGHT,
        .canvas_size_x = SONY_FRAME_WIDTH,
        .canvas_size_y = SONY_FRAME_HEIGHT,
        .valid_size_x = SONY_FRAME_WIDTH,
        .valid_size_y = SONY_FRAME_HEIGHT,
        .target_size_x = SONY_FRAME_WIDTH,
        .target_size_y = SONY_FRAME_HEIGHT,
        .yc_compress = 0,
        .data_placement = 2, /* NV16 */
        .yc_bit_depth = 8
    };
    ctx->last_state_info = (PIN_YC_YC_STATE_INFO){
        .y_range = 0,     /* Limited range 16-235 */
        .colorimetry = 0, /* BT.601 */
        .chroma_phase = 0,
        .scanline = 0
    };

    return RAW_FRAME_OK;
}

void raw_live_sony_set_host_ebusy(raw_live_sony_context_t *ctx, int ebusy) {
    if (ctx) {
        ctx->host_ebusy = ebusy ? 1 : 0;
    }
}

int raw_live_sony_validate_destination(raw_live_sony_context_t *ctx, uint32_t dest_unit_type,
                                       uint32_t dest_phys, size_t dest_len) {
    if (!ctx) {
        return RAW_FRAME_ERR_INVALID_PARAM;
    }
    /* Strictly enforce that destination is exclusively owned staging Unit 0x276 */
    if (dest_unit_type != SONY_DMM_UNIT_UVC_WORKSPACE && dest_unit_type != ctx->owned_staging_unit) {
        return RAW_FRAME_ERR_INVALID_PARAM;
    }
    if (dest_len < SONY_YUY2_FRAME_BYTES) {
        return RAW_FRAME_ERR_INVALID_PARAM;
    }
    if (!dest_phys || dest_phys > UINT32_MAX - dest_len) {
        return RAW_FRAME_ERR_INVALID_PARAM;
    }
    return RAW_FRAME_OK;
}

/* =========================================================================
 * 2. Helper: Metadata Validation
 * ========================================================================= */

static int sony_validate_metadata(const raw_live_sony_context_t *ctx) {
    const PIN_YC_IMAGE_SIZE_INFO *s = &ctx->last_size_info;
    const PIN_YC_YC_STATE_INFO *st = &ctx->last_state_info;
    const dmm_extent_t *ext = &ctx->last_extent;

    /* Image must be attached and uncompressed linear raster */
    if (!s->image_attach || s->yc_compress != 0) {
        return RAW_FRAME_ERR_UNSUPPORTED_FMT;
    }

    /* Valid geometry must match standard 640x480 UVC transport */
    if (s->record_size_x != SONY_FRAME_WIDTH || s->record_size_y != SONY_FRAME_HEIGHT) {
        return RAW_FRAME_ERR_UNSUPPORTED_FMT;
    }

    /* Data placement must be either packed YUY2 (1) or semi-planar NV16/NV12 (2) */
    if (s->data_placement != 1 && s->data_placement != 2) {
        return RAW_FRAME_ERR_UNSUPPORTED_FMT;
    }

    /* Color range must be limited range (0 = 16-235) and colorimetry ITU-R BT.601 */
    if (st->y_range != 0 || st->colorimetry != 0) {
        return RAW_FRAME_ERR_UNSUPPORTED_FMT;
    }

    /* DMM extent must contain valid physical plane addresses */
    if (!ext->planes[0].phy_addr) {
        return RAW_FRAME_ERR_INVALID_PARAM;
    }

    if (s->data_placement == 2) {
        /* Semi-planar NV16 requires valid chroma plane without memory overlap */
        if (!ext->planes[1].phy_addr) {
            return RAW_FRAME_ERR_INVALID_PARAM;
        }
        uint32_t y_start = ext->planes[0].phy_addr;
        uint32_t y_end = y_start + SONY_NV16_LUMA_BYTES;
        uint32_t uv_start = ext->planes[1].phy_addr;
        uint32_t uv_end = uv_start + SONY_NV16_CHROMA_BYTES;

        if (y_start < uv_end && uv_start < y_end) {
            return RAW_FRAME_ERR_INVALID_PARAM; /* Overlap detected */
        }
    }

    return RAW_FRAME_OK;
}

/* =========================================================================
 * 3. raw_live_ops Implementation Callbacks
 * ========================================================================= */

int raw_live_sony_acquire(void *opaque, uint32_t timeout_ms, raw_live_frame *out) {
    if (!opaque || !out) {
        return RAW_FRAME_ERR_INVALID_PARAM;
    }
    raw_live_sony_context_t *ctx = (raw_live_sony_context_t *)opaque;

    /* Defensive reset of caller output token */
    out->token = 0;

    /* Strictly enforce timeout <= 10 ms (RAW_LIVE_MAX_TIMEOUT_MS) */
    if (!timeout_ms || timeout_ms > RAW_LIVE_MAX_TIMEOUT_MS) {
        ctx->total_errors++;
        return RAW_FRAME_ERR_INVALID_PARAM;
    }

    /* Must be subscribed to VDF completed preview stream */
    if (!ctx->is_subscribed) {
        ctx->total_errors++;
        return RAW_FRAME_ERR_NOT_INIT;
    }

    /* Cannot acquire a new frame if a previous lease has not been released */
    if (ctx->active_lease_token != 0) {
        ctx->total_errors++;
        return RAW_FRAME_ERR_DEVICE_BUSY;
    }

    /* USB Completion Fence: never acquire or mutate while host EBUSY persists */
    if (ctx->host_ebusy) {
        ctx->total_fence_blocks++;
        return RAW_FRAME_ERR_DEVICE_BUSY;
    }

    /* Acquire Frame Lease via IPC MemoryHandle Open (opcode 0x400, subcmd 3) */
    if (ctx->ipc_msg) {
        int err = ctx->ipc_msg(ctx->transport_ctx, ctx->target_queue_id,
                                SONY_IPC_OPCODE_MEMORY_HANDLE,
                                SONY_IPC_SUBCMD_MEM_OPEN,
                                0,
                                &ctx->last_extent, sizeof(ctx->last_extent),
                                timeout_ms);
        if (err) {
            if (err == RAW_FRAME_ERR_TIMEOUT) {
                ctx->total_timeouts++;
            } else {
                ctx->total_errors++;
            }
            return err;
        }
    } else if (!ctx->simulated_frame_ready) {
        /* Default standalone simulation: synthesize a standard ISP preview extent */
        ctx->last_extent.unit_handle = (uint16_t)((ctx->sequence & 0x7fff) + 1);
        ctx->last_extent.num_planes = 2;
        ctx->last_extent.total_size = SONY_YUY2_FRAME_BYTES;
        ctx->last_extent.planes[0].phy_addr = 0x20000000u;
        ctx->last_extent.planes[0].size_or_stride = SONY_FRAME_WIDTH;
        ctx->last_extent.planes[1].phy_addr = 0x2004b000u;
        ctx->last_extent.planes[1].size_or_stride = SONY_FRAME_WIDTH;

        ctx->last_size_info = (PIN_YC_IMAGE_SIZE_INFO){
            .image_attach = 1,
            .unit_type = 0x1ddu,
            .unit_handle = ctx->last_extent.unit_handle,
            .record_size_x = SONY_FRAME_WIDTH,
            .record_size_y = SONY_FRAME_HEIGHT,
            .canvas_size_x = SONY_FRAME_WIDTH,
            .canvas_size_y = SONY_FRAME_HEIGHT,
            .valid_size_x = SONY_FRAME_WIDTH,
            .valid_size_y = SONY_FRAME_HEIGHT,
            .target_size_x = SONY_FRAME_WIDTH,
            .target_size_y = SONY_FRAME_HEIGHT,
            .yc_compress = 0,
            .data_placement = 2, /* NV16 */
            .yc_bit_depth = 8
        };

        ctx->last_state_info = (PIN_YC_YC_STATE_INFO){
            .y_range = 0,     /* Limited range BT.601 */
            .colorimetry = 0, /* BT.601 */
            .chroma_phase = 0,
            .scanline = 0
        };
    }

    /* Validate frame metadata and plane layout */
    int val_err = sony_validate_metadata(ctx);
    if (val_err != RAW_FRAME_OK) {
        /* On metadata rejection, close any acquired handle immediately */
        if (ctx->ipc_msg && ctx->last_extent.unit_handle) {
            ctx->ipc_msg(ctx->transport_ctx, ctx->target_queue_id,
                         SONY_IPC_OPCODE_MEMORY_HANDLE,
                         SONY_IPC_SUBCMD_MEM_CLOSE,
                         ctx->last_extent.unit_handle, NULL, 0, 10);
        }
        ctx->total_errors++;
        return val_err;
    }

    /* Form non-zero opaque lease token */
    uintptr_t token = (uintptr_t)ctx->last_extent.unit_handle;
    if (!token) {
        token = (uintptr_t)(ctx->sequence + 0x1000u);
    }
    ctx->active_lease_token = token;
    ctx->active_unit_handle = ctx->last_extent.unit_handle;

    /* Populate raw_live_frame structure */
    out->token = token;
    out->sequence = ++ctx->sequence;
    out->width = SONY_FRAME_WIDTH;
    out->height = SONY_FRAME_HEIGHT;
    out->flags = RAW_LIVE_READY_LINEAR_8BIT_BT601_LIMITED;

    if (ctx->last_size_info.data_placement == 1) {
        /* Interleaved YUY2 single plane */
        out->format = RAW_FRAME_PIXFMT_YUY2;
        out->plane[0].physical = ctx->last_extent.planes[0].phy_addr;
        out->plane[0].bytes = SONY_YUY2_FRAME_BYTES;
        out->plane[0].stride = SONY_YUY2_ROW_STRIDE;
        out->plane[1].physical = 0;
        out->plane[1].bytes = 0;
        out->plane[1].stride = 0;
    } else {
        /* Semi-planar NV16 two planes */
        out->format = RAW_FRAME_PIXFMT_NV16;
        out->plane[0].physical = ctx->last_extent.planes[0].phy_addr;
        out->plane[0].bytes = SONY_NV16_LUMA_BYTES;
        out->plane[0].stride = SONY_FRAME_WIDTH;
        out->plane[1].physical = ctx->last_extent.planes[1].phy_addr;
        out->plane[1].bytes = SONY_NV16_CHROMA_BYTES;
        out->plane[1].stride = SONY_FRAME_WIDTH;
    }

    ctx->total_acquired++;
    return RAW_FRAME_OK;
}

int raw_live_sony_release(void *opaque, uintptr_t token) {
    if (!opaque || !token) {
        return RAW_FRAME_ERR_INVALID_PARAM;
    }
    raw_live_sony_context_t *ctx = (raw_live_sony_context_t *)opaque;

    /* Token must match the active acquired lease */
    if (token != ctx->active_lease_token) {
        ctx->total_errors++;
        return RAW_FRAME_ERR_INVALID_PARAM;
    }

    /* Release frame lease via IPC MemoryHandle Close (opcode 0x400, subcmd 4) */
    if (ctx->ipc_msg) {
        int err = ctx->ipc_msg(ctx->transport_ctx, ctx->target_queue_id,
                                SONY_IPC_OPCODE_MEMORY_HANDLE,
                                SONY_IPC_SUBCMD_MEM_CLOSE,
                                ctx->active_unit_handle,
                                NULL, 0, 10);
        if (err) {
            /* An error retains the token: retry is allowed; do not clear lease */
            ctx->total_errors++;
            return err;
        }
    }

    /* Release succeeded: clear active lease */
    ctx->active_lease_token = 0;
    ctx->active_unit_handle = 0;
    ctx->total_released++;
    return RAW_FRAME_OK;
}

int raw_live_sony_map_readonly(void *opaque, const raw_live_plane *plane,
                               size_t needed_bytes, raw_live_mapping *out) {
    if (!opaque || !plane || !out || !needed_bytes) {
        return RAW_FRAME_ERR_INVALID_PARAM;
    }
    raw_live_sony_context_t *ctx = (raw_live_sony_context_t *)opaque;

    if (!plane->physical || plane->bytes < needed_bytes) {
        return RAW_FRAME_ERR_INVALID_PARAM;
    }

    /* If custom mapping hook is supplied, delegate to it */
    if (ctx->stream_mmap) {
        return ctx->stream_mmap(ctx->transport_ctx, plane->physical, needed_bytes,
                                &out->base, &out->data, &out->length);
    }

#ifdef RAW_LIVE_TARGET_ARM
    /* Genuine target implementation via /dev/stream */
    size_t delta = plane->physical & 4095u;
    if (needed_bytes > SIZE_MAX - delta - 4095u) {
        return RAW_FRAME_ERR_INVALID_PARAM;
    }
    size_t length = (needed_bytes + delta + 4095u) & ~(size_t)4095u;
    if (length > UINT32_MAX - (plane->physical & ~4095u)) {
        return RAW_FRAME_ERR_INVALID_PARAM;
    }

    int fd = open("/dev/stream", 0); /* O_RDONLY */
    if (fd < 0) {
        return RAW_FRAME_ERR_IO;
    }
    void *base = mmap(0, length, 1 /* PROT_READ */, 1 /* MAP_SHARED */, fd,
                      (long)(plane->physical & ~4095u));
    close(fd);
    if (base == (void *)-1) {
        return RAW_FRAME_ERR_MMAP_FAILED;
    }

    out->base = base;
    out->data = (const uint8_t *)base + delta;
    out->length = length;
    return RAW_FRAME_OK;
#else
    return RAW_FRAME_ERR_MMAP_FAILED;
#endif
}

int raw_live_sony_unmap(void *opaque, raw_live_mapping *mapping) {
    if (!opaque || !mapping) {
        return RAW_FRAME_ERR_INVALID_PARAM;
    }
    raw_live_sony_context_t *ctx = (raw_live_sony_context_t *)opaque;

    if (!mapping->base || !mapping->length) {
        return RAW_FRAME_ERR_INVALID_PARAM;
    }

    if (ctx->stream_munmap) {
        return ctx->stream_munmap(ctx->transport_ctx, mapping->base, mapping->length);
    }

#ifdef RAW_LIVE_TARGET_ARM
    return munmap(mapping->base, mapping->length) ? RAW_FRAME_ERR_IO : RAW_FRAME_OK;
#else
    return RAW_FRAME_OK;
#endif
}

/* Global raw_live_ops descriptor */
const raw_live_ops raw_live_sony_ops = {
    .abi = RAW_LIVE_ABI,
    .size = sizeof(raw_live_ops),
    .acquire = raw_live_sony_acquire,
    .release = raw_live_sony_release,
    .map_readonly = raw_live_sony_map_readonly,
    .unmap = raw_live_sony_unmap
};

/* =========================================================================
 * 4. Binding Helpers for Revision 2.5 Transport
 * ========================================================================= */

static int (*s_transport_bind_fn)(const raw_live_ops *ops, void *opaque) = NULL;
static int (*s_transport_unbind_fn)(void) = NULL;

void raw_live_sony_set_transport_bind_fn(int (*bind_fn)(const raw_live_ops *, void *),
                                         int (*unbind_fn)(void)) {
    s_transport_bind_fn = bind_fn;
    s_transport_unbind_fn = unbind_fn;
}

int raw_live_sony_bind(raw_live_sony_context_t *ctx) {
    if (!ctx) {
        return RAW_FRAME_ERR_INVALID_PARAM;
    }
    if (s_transport_bind_fn) {
        return s_transport_bind_fn(&raw_live_sony_ops, ctx);
    }
#ifdef RAW_LIVE_TARGET_ARM
    return yuy2_live_bind(&raw_live_sony_ops, ctx);
#else
    return RAW_FRAME_ERR_NOT_INIT;
#endif
}

int raw_live_sony_unbind(void) {
    if (s_transport_unbind_fn) {
        return s_transport_unbind_fn();
    }
#ifdef RAW_LIVE_TARGET_ARM
    return yuy2_live_unbind();
#else
    return RAW_FRAME_ERR_NOT_INIT;
#endif
}
