#include "bayer_tap.h"

uint32_t bayer_tap_get_frame_size(bayer_geometry_t geom) {
    switch (geom) {
        case BAYER_GEOMETRY_1080P_RAW10:
            return 2592000; /* 1920 * 1080 * 10 / 8 */
        case BAYER_GEOMETRY_1080P_RAW12:
            return 3110400; /* 1920 * 1080 * 12 / 8 */
        case BAYER_GEOMETRY_1280P_RAW10:
            return 3072000; /* 1920 * 1280 * 10 / 8 */
        default:
            return 0;
    }
}

int bayer_tap_validate_alignment(uint32_t phys_addr, uint32_t size) {
    /* DMA-330 burst transfer requires address aligned to 128 bytes */
    if ((phys_addr & (DMA330_BURST_ALIGNMENT - 1)) != 0) {
        return -1;
    }
    /* Size must be positive and multiple of SuperSpeed packet size (1024) or aligned */
    if (size == 0 || (size & 0x3F) != 0) {
        return -2;
    }
    return 0;
}

int bayer_tap_init(liveview_ring_ctx_t *ring, bayer_geometry_t geom, uint32_t base_phys_addr) {
    uint32_t frame_size;
    uint32_t i;

    if (!ring) {
        return -1;
    }

    frame_size = bayer_tap_get_frame_size(geom);
    if (frame_size == 0) {
        return -2;
    }

    /* Check base alignment */
    if (bayer_tap_validate_alignment(base_phys_addr, frame_size) != 0) {
        return -3;
    }

    ring->ring_slots = 4; /* Standard 4-slot ping-pong ring buffer */
    ring->slot_size_bytes = frame_size;
    ring->current_slot = 0;
    ring->consumed_slot = 0;
    ring->frame_seq = 0;
    ring->dropped_frames = 0;

    /* Initialize slot physical addresses with 128-byte alignment padding */
    uint32_t aligned_stride = (frame_size + DMA330_BURST_ALIGNMENT - 1) & ~(DMA330_BURST_ALIGNMENT - 1);
    for (i = 0; i < ring->ring_slots; i++) {
        ring->slot_phys_addrs[i] = base_phys_addr + (i * aligned_stride);
    }

    return 0;
}

int bayer_tap_on_frame_ready(liveview_ring_ctx_t *ring, uint32_t produced_slot, usbg_video_data_info_t *out_submission) {
    if (!ring || !out_submission) {
        return -1;
    }

    if (produced_slot >= ring->ring_slots) {
        return -2;
    }

    /* Check if producer overran the consumer slot */
    if (produced_slot == ring->consumed_slot && ring->frame_seq > 0) {
        ring->dropped_frames++;
        /* Advance consumer to prevent stall */
        ring->consumed_slot = (ring->consumed_slot + 1) % ring->ring_slots;
    }

    ring->current_slot = produced_slot;
    ring->frame_seq++;

    out_submission->slot_id = produced_slot;
    out_submission->length_bytes = ring->slot_size_bytes;

    /* Advance consumed pointer */
    ring->consumed_slot = (produced_slot + 1) % ring->ring_slots;

    return 0;
}
