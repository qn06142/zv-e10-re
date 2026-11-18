#ifndef LIVE_BAYER_TAP_V01_H
#define LIVE_BAYER_TAP_V01_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Sony ZV-E10 LiveView Bayer RAW Tap Architecture (v0.1)
 *
 * Target SoC: CXD90045 (BIONZ X)
 * Sensor: Sony IMX503 / 24.2 MP APS-C CMOS
 * Transport: USB 3.0 SuperSpeed Bulk Endpoint 0x81 via DMA330
 */

#define USBG_VIDEO_IOCTL_REG_BUF       0x4008f000  /* _IOW(0xf0, 0, struct usbg_video_buf_info) */
#define USBG_VIDEO_IOCTL_UPDATE_BUF    0x4008f003  /* _IOW(0xf0, 3, struct usbg_video_data_info) */
#define USBG_VIDEO_IOCTL_WAIT_CMP      0xf002      /* _IO(0xf0, 2) */

#define USB3_SUPER_SPEED_PACKET_SIZE   1024
#define DMA330_BURST_ALIGNMENT         128

/* Frame geometry profiles */
typedef enum {
    BAYER_GEOMETRY_1080P_RAW10 = 0,  /* 1920x1080 10-bit packed: 2,592,000 bytes */
    BAYER_GEOMETRY_1080P_RAW12 = 1,  /* 1920x1080 12-bit packed: 3,110,400 bytes */
    BAYER_GEOMETRY_1280P_RAW10 = 2,  /* 1920x1280 10-bit open gate: 3,072,000 bytes */
} bayer_geometry_t;

/* Ring buffer descriptor for DFE sensor liveview frames */
typedef struct {
    uint32_t ring_slots;           /* Total ring slots (typically 4 or 8) */
    uint32_t current_slot;         /* Last produced slot index */
    uint32_t consumed_slot;        /* Last consumed slot index */
    uint32_t slot_phys_addrs[8];   /* Physical DMA addresses of slots */
    uint32_t slot_size_bytes;      /* Size of each slot */
    uint32_t frame_seq;            /* Monotonic frame sequence counter */
    uint32_t dropped_frames;       /* Overrun / drop counter */
} liveview_ring_ctx_t;

/* Gadget video registration parameter matching usbg_video.ko ABI */
typedef struct {
    uint32_t phys_addr;
    uint32_t size_bytes;
} usbg_video_buf_info_t;

/* Gadget video frame submission parameter matching usbg_video.ko ABI */
typedef struct {
    uint32_t slot_id;
    uint32_t length_bytes;
} usbg_video_data_info_t;

/* Tap status and performance metrics */
typedef struct {
    uint32_t total_frames_sent;
    uint64_t total_bytes_sent;
    uint32_t min_interval_us;
    uint32_t max_interval_us;
    uint32_t avg_interval_us;
    int is_active;
} bayer_tap_stats_t;

/* API functions */
int bayer_tap_init(liveview_ring_ctx_t *ring, bayer_geometry_t geom, uint32_t base_phys_addr);
int bayer_tap_on_frame_ready(liveview_ring_ctx_t *ring, uint32_t produced_slot, usbg_video_data_info_t *out_submission);
int bayer_tap_validate_alignment(uint32_t phys_addr, uint32_t size);
uint32_t bayer_tap_get_frame_size(bayer_geometry_t geom);

#ifdef __cplusplus
}
#endif

#endif /* LIVE_BAYER_TAP_V01_H */
