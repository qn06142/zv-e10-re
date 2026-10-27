/**
 * @file raw_frame_source.h
 * @brief Live Camera Raw Frame Source Interface for Sony ZV-E10 (CXD90045).
 *
 * Reconstructed contract structures, DMM unit definitions, physical memory
 * mapping parameters, and conversion kernels for uncompressed 640x480 YUY2 UVC streaming.
 */

#ifndef RAW_FRAME_SOURCE_H
#define RAW_FRAME_SOURCE_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* =========================================================================
 * 1. DMM Unit IDs and Extent IDs (Reverse Engineered from DmmConfig.bin)
 * ========================================================================= */

/**
 * DMM Unit IDs assigned across the ZV-E10 ISP and video subsystem.
 * Verified against DmmConfig.bin (unit table starting at file offset 0x11000).
 */
#define DMM_UNIT_PREVIEW_1DD        0x01ddu /* Extent 0x227: 614,400 bytes (ISP Preview Ring 1) */
#define DMM_UNIT_PREVIEW_2C5        0x02c5u /* Extent 0x3da: 614,400 bytes (ISP Preview Ring 2) */
#define DMM_UNIT_PREVIEW_2CD        0x02cdu /* Extent 0x3e2: 614,400 bytes (ISP Preview Ring 3) */
#define DMM_UNIT_UVC_YUY2_SRC       0x0276u /* Extent 0x333: 3,276,800 bytes (Patched UVC source workspace) */
#define DMM_UNIT_UVC_STAGING_STOCK  0x050eu /* Extent 0x589: 1,843,200 bytes (Stock UVC JPEG staging buffer) */
#define DMM_UNIT_UAC_AUDIO_STOCK    0x050fu /* Extent 0x58a: 6,144 bytes (Stock UAC audio PCM FIFO) */

/**
 * DMM Extent IDs and exact byte allocations.
 * Verified against DmmConfig.bin (extent records at 0x0180c, 0x01c1c, 0x085f8, 0x02e14, 0x01d98).
 */
#define DMM_EXTENT_640_480_YUV_227  0x0227u /* 614,400 bytes (0x96000) - 640x480 YUV 4:2:2 */
#define DMM_EXTENT_640_480_YUV_3DA  0x03dau /* 614,400 bytes (0x96000) - 640x480 YUV 4:2:2 */
#define DMM_EXTENT_640_480_YUV_3E2  0x03e2u /* 614,400 bytes (0x96000) - 640x480 YUV 4:2:2 */
#define DMM_EXTENT_SRC_WORKSPACE_333 0x0333u /* 3,276,800 bytes (0x320000) - UVC frame staging */
#define DMM_EXTENT_STAGING_589      0x0589u /* 1,843,200 bytes (0x1c2000) - Two 921,600 halves */
#define DMM_EXTENT_AUDIO_58A        0x058au /* 6,144 bytes (0x1800) - Audio FIFO */

/* Buffer Geometry Constants for 640x480 UVC Transport */
#define RAW_FRAME_WIDTH             640u
#define RAW_FRAME_HEIGHT            480u
#define RAW_FRAME_YUY2_BYTES_PER_PX 2u
#define RAW_FRAME_YUY2_STRIDE       (RAW_FRAME_WIDTH * RAW_FRAME_YUY2_BYTES_PER_PX) /* 1,280 bytes */
#define RAW_FRAME_YUY2_SIZE         (RAW_FRAME_YUY2_STRIDE * RAW_FRAME_HEIGHT)      /* 614,400 bytes */

#define RAW_FRAME_NV16_LUMA_SIZE    (RAW_FRAME_WIDTH * RAW_FRAME_HEIGHT)            /* 307,200 bytes */
#define RAW_FRAME_NV16_CHROMA_SIZE  (RAW_FRAME_WIDTH * RAW_FRAME_HEIGHT)            /* 307,200 bytes */
#define RAW_FRAME_NV16_SIZE         (RAW_FRAME_NV16_LUMA_SIZE + RAW_FRAME_NV16_CHROMA_SIZE) /* 614,400 bytes */

#define RAW_FRAME_NV12_LUMA_SIZE    (RAW_FRAME_WIDTH * RAW_FRAME_HEIGHT)            /* 307,200 bytes */
#define RAW_FRAME_NV12_CHROMA_SIZE  (RAW_FRAME_WIDTH * (RAW_FRAME_HEIGHT / 2u))     /* 153,600 bytes */
#define RAW_FRAME_NV12_SIZE         (RAW_FRAME_NV12_LUMA_SIZE + RAW_FRAME_NV12_CHROMA_SIZE) /* 460,800 bytes */

/* PFN (Page Frame Number) conversion formula from stream.ko (stream_mmap PFN formula: phys >> 12) */
#define RAW_FRAME_PAGE_SHIFT        12u
#define RAW_FRAME_PAGE_SIZE         (1u << RAW_FRAME_PAGE_SHIFT) /* 4096 bytes */
#define RAW_FRAME_PAGE_MASK         (RAW_FRAME_PAGE_SIZE - 1u)
#define RAW_FRAME_PHYS_TO_PFN(p)    ((uint32_t)((p) >> RAW_FRAME_PAGE_SHIFT))
#define RAW_FRAME_PFN_TO_PHYS(pfn)  (((uint32_t)(pfn)) << RAW_FRAME_PAGE_SHIFT)

/* =========================================================================
 * 2. Hardware Metadata Structures
 * ========================================================================= */

#pragma pack(push, 1)

/**
 * struct PIN_YC_IMAGE_SIZE_INFO
 * Reconstructed 60-byte (0x3c) metadata structure matching:
 * - dataflowInfraFramework.so VA 0x24678 (C_DataflowInfra_Entry_ImageSizeInfo constructor and accessors)
 * - libObj.so VA 0xed4a30 ([ObjRenderer]PIN_YC_IMAGE_SIZE_INFO print formatter)
 */
struct PIN_YC_IMAGE_SIZE_INFO {
    uint8_t  image_attach;        /* +0x00 (0): Image attachment flag */
    uint8_t  reserved0[3];        /* +0x01 (1): Alignment padding */
    uint32_t unit_type;           /* +0x04 (4): DMM Unit Type (e.g. 0x1dd, 0x2c5, 0x2cd, 0x276, 0x50e) */
    uint16_t unit_handle;         /* +0x08 (8): DMM Unit Handle returned by dmm_ctrl */
    uint16_t reserved1;           /* +0x0a (10): Alignment padding */
    uint32_t unit_data_offset;    /* +0x0c (12): Byte offset within DMM extent to first active pixel */
    uint8_t  exposure_time;       /* +0x10 (16): Exposure time tag */
    uint8_t  expose_pic_delay;    /* +0x11 (17): Exposure picture delay count */
    uint8_t  scenario_end;        /* +0x12 (18): End of sequence / scenario flag */
    uint8_t  mirror;              /* +0x13 (19): Sensor horizontal/vertical flip state */
    uint16_t record_size_x;       /* +0x14 (20): Recording buffer stride pitch in pixels/bytes */
    uint16_t record_size_y;       /* +0x16 (22): Recording buffer height / row count */
    uint16_t canvas_size_x;       /* +0x18 (24): Total allocated canvas width (stride in pixels) */
    uint16_t canvas_size_y;       /* +0x1a (26): Total allocated canvas height (row capacity) */
    uint16_t valid_offset_x;      /* +0x1c (28): Horizontal offset to start of valid image */
    uint16_t valid_offset_y;      /* +0x1e (30): Vertical offset to start of valid image */
    uint16_t valid_size_x;        /* +0x20 (32): Active valid picture width (optical pixels) */
    uint16_t valid_size_y;        /* +0x22 (34): Active valid picture height (optical pixels) */
    uint16_t target_offset_x;     /* +0x24 (36): Cropped / display target offset X */
    uint16_t target_offset_y;     /* +0x26 (38): Cropped / display target offset Y */
    uint16_t target_size_x;       /* +0x28 (40): Target output width (scaled/cropped pixels) */
    uint16_t target_size_y;       /* +0x2a (42): Target output height (scaled/cropped pixels) */
    uint8_t  data_site;           /* +0x2c (44): Chroma subsampling siting (cosited vs interstitial) */
    uint8_t  iib_number;          /* +0x2d (45): Image Information Buffer ring index */
    uint8_t  aspect;              /* +0x2e (46): Aspect ratio enum (0=4:3, 1=16:9, 2=3:2, 3=1:1) */
    uint8_t  yc_compress;         /* +0x2f (47): Compression mode (0 = uncompressed YUV raster) */
    uint8_t  data_transfer;       /* +0x30 (48): Transfer mode / DMA packing format */
    uint8_t  data_placement;      /* +0x31 (49): Plane layout (1=interleaved YUY2, 2=semi-planar NV12/NV16) */
    uint8_t  data_content;        /* +0x32 (50): Content type (video, still, preview, thumbnail) */
    uint8_t  data_scan;           /* +0x33 (51): Scan format (0 = progressive, 1 = interlaced) */
    uint16_t strip_width;         /* +0x34 (52): Strip width / hardware slice pitch (alignment block) */
    uint8_t  yc_bit_depth;        /* +0x36 (54): Bit depth per component (8 = 8-bit YUV) */
    uint8_t  reserved2;           /* +0x37 (55): Alignment padding */
    uint16_t cam_freq_char_h;     /* +0x38 (56): High-frequency spatial characteristic tag */
    uint16_t reserved3;           /* +0x3a (58): Trailing padding to 60 bytes */
};

/**
 * struct PIN_YC_YC_STATE_INFO
 * Reconstructed 6-byte companion structure matching:
 * - dataflowInfraFramework.so VA 0x256cc (C_DataflowInfra_Entry_YcStateInfo)
 * - libObj.so VA 0xed4feb ([ObjRenderer]PIN_YC_YC_STATE_INFO)
 */
struct PIN_YC_YC_STATE_INFO {
    uint8_t y_range;              /* +0x00 (0): Luma range (0 = limited 16-235, 1 = full 0-255) */
    uint8_t colorimetry;          /* +0x01 (1): Colorimetry standard (1 = BT.601, 2 = BT.709) */
    uint8_t chroma_phase;         /* +0x02 (2): Chroma sampling phase */
    uint8_t scanline;             /* +0x03 (3): Progressive vs interlaced scanlines */
    uint8_t copy_protection;      /* +0x04 (4): CGMS-A / copy protection tag */
    uint8_t author;               /* +0x05 (5): Creation source / author tag */
};

/**
 * struct PIN_PROPERTY
 * Reconstructed 16-byte pin identity key matching:
 * - dataflowInfraFramework.so / libBizFw.so pin registration (Command 0x1000)
 * - Routing key: (subsystem_id << 16) | (unit_id << 8) | pin_id
 */
typedef struct {
    uint32_t subsystem_id;        /* +0x00 (0): Subsystem ID (e.g. 0x00000055 for VDF) */
    uint32_t unit_id;             /* +0x04 (4): Unit ID (e.g. 0x00000001 for VDF Preview Source) */
    uint32_t pin_id;              /* +0x08 (8): Pin Index (e.g. 0x00000001) */
    uint32_t flags_queue_id;      /* +0x0c (12): Connection flags or target queue ID */
} PIN_PROPERTY;

/**
 * struct dmm_extent
 * Reconstructed 40-byte multi-plane memory extent matching:
 * - DMM extent open ABI and dumpSdsYccFromHandle (libBizFw.so VA 0x34998)
 */
typedef struct {
    uint16_t unit_handle;         /* +0x00 (0): DMM memory unit handle */
    uint16_t num_planes;          /* +0x02 (2): Plane count (2 for YC: Y and UV) */
    uint32_t total_size;          /* +0x04 (4): Aggregate buffer size in bytes */
    struct {
        uint32_t phy_addr;        /* +0x08, +0x10: Physical start address */
        uint32_t size_or_stride;  /* +0x0c, +0x14: Plane size / row stride */
    } planes[4];
} dmm_extent_t;

#pragma pack(pop)

/* Compile-time verification of structure sizes */
#if defined(__STDC_VERSION__) && (__STDC_VERSION__ >= 201112L)
_Static_assert(sizeof(struct PIN_YC_IMAGE_SIZE_INFO) == 60, "PIN_YC_IMAGE_SIZE_INFO size must be exactly 60 bytes");
_Static_assert(sizeof(struct PIN_YC_YC_STATE_INFO) == 6, "PIN_YC_YC_STATE_INFO size must be exactly 6 bytes");
_Static_assert(sizeof(PIN_PROPERTY) == 16, "PIN_PROPERTY size must be exactly 16 bytes");
_Static_assert(sizeof(dmm_extent_t) == 40, "dmm_extent_t size must be exactly 40 bytes");
#endif

/* =========================================================================
 * 3. Enums & Error Codes
 * ========================================================================= */

typedef enum {
    RAW_FRAME_PIXFMT_UNKNOWN       = 0,
    RAW_FRAME_PIXFMT_YUY2          = 1, /* Interleaved YUYV / YUY2 (data_placement = 1) */
    RAW_FRAME_PIXFMT_NV16          = 2, /* Semi-planar YUV 4:2:2 (data_placement = 2, 4:2:2) */
    RAW_FRAME_PIXFMT_NV12          = 3, /* Semi-planar YUV 4:2:0 (data_placement = 2, 4:2:0) */
    RAW_FRAME_PIXFMT_SYNTHETIC     = 4  /* Fallback synthetic SMPTE color bars */
} raw_frame_pixfmt_t;

typedef enum {
    RAW_FRAME_OK                   = 0,
    RAW_FRAME_ERR_INVALID_PARAM    = -1,
    RAW_FRAME_ERR_NOT_INIT         = -2,
    RAW_FRAME_ERR_MMAP_FAILED      = -3,
    RAW_FRAME_ERR_TIMEOUT          = -4,
    RAW_FRAME_ERR_UNSUPPORTED_FMT  = -5,
    RAW_FRAME_ERR_DEVICE_BUSY      = -6,
    RAW_FRAME_ERR_IO               = -7,
    RAW_FRAME_ERR_NO_MEMORY        = -8
} raw_frame_err_t;

/* =========================================================================
 * 4. Context & Descriptors
 * ========================================================================= */

typedef struct {
    uint32_t width;                    /* Target frame width (default: 640) */
    uint32_t height;                   /* Target frame height (default: 480) */
    uint32_t dmm_unit_type;            /* Target DMM unit type (e.g. 0x276) */
    uint32_t timeout_ms;               /* Acquisition timeout in ms */
    bool     allow_synthetic_fallback; /* If true, generate SMPTE bars on timeout */
    const char *stream_dev_path;       /* Path to stream driver (e.g. "/dev/stream") */
} raw_frame_config_t;

typedef struct {
    raw_frame_pixfmt_t format;         /* Pixel format of acquired frame */
    uint32_t width;                    /* Width in pixels */
    uint32_t height;                   /* Height in pixels */
    uint32_t y_stride;                 /* Luma stride in bytes */
    uint32_t uv_stride;                /* Chroma stride in bytes */
    uint32_t phys_addr;                /* Physical memory base address */
    void     *vaddr_y;                 /* Virtual address for luma (or packed YUY2) */
    void     *vaddr_uv;                /* Virtual address for chroma (NV16/NV12) */
    void     *mapping_base;            /* Base mmap pointer (for munmap) */
    size_t   mapping_len;              /* Mapped size in bytes */
    size_t   data_size;                /* Total valid data size in bytes */
    uint16_t unit_handle;              /* DMM unit handle for release */
    uint32_t frame_index;              /* Monotonic frame sequence counter */
    bool     is_synthetic;             /* True if synthetic fallback pattern */
    struct PIN_YC_IMAGE_SIZE_INFO size_info; /* Native ISP metadata */
} raw_frame_desc_t;

typedef struct {
    raw_frame_config_t config;
    int      stream_fd;                /* File descriptor for /dev/stream */
    uint32_t frame_counter;            /* Monotonic counter */
    uint32_t fallback_count;           /* Count of synthetic frames generated */
    bool     initialized;
    void     *staging_mapping;         /* Mapped address for DMM Unit 0x276 */
    size_t   staging_map_len;          /* Length of mapped region */
    uint32_t staging_phys_addr;        /* Physical address of Unit 0x276 */
} raw_frame_source_ctx_t;

/* =========================================================================
 * 5. Memory Barrier Helper
 * ========================================================================= */

/**
 * Issue ARM Data Synchronization Barrier (DSB) and Data Memory Barrier (DMB).
 * Ensures all write-combining buffers and cache operations have drained to DRAM
 * before signaling the hardware DMA-330 controller.
 */
static inline void raw_frame_memory_barrier(void) {
#if defined(__arm__) || defined(__aarch64__)
    __asm__ volatile("dsb\n\tdmb" ::: "memory");
#elif defined(__GNUC__) || defined(__clang__)
    __asm__ volatile("" ::: "memory");
#else
    /* Non-GCC memory barrier */
#endif
}

/* =========================================================================
 * 6. Function Prototypes
 * ========================================================================= */

/**
 * Initialize the raw frame source subsystem.
 */
int raw_frame_source_init(raw_frame_source_ctx_t *ctx, const raw_frame_config_t *config);

/**
 * Acquire a raw frame from the camera ISP / Dataflow pipeline.
 * On acquisition timeout or device unavailability, returns a synthetic frame if configured.
 */
int raw_frame_source_acquire(raw_frame_source_ctx_t *ctx, raw_frame_desc_t *frame_desc, uint32_t timeout_ms);

/**
 * Convert acquired frame to standard packed YUY2 (640x480, 614,400 bytes).
 * Supports NV16, NV12, direct YUY2, and synthetic fallback.
 * Automatically issues hardware memory barrier prior to return.
 */
int raw_frame_source_convert_to_yuy2(raw_frame_source_ctx_t *ctx,
                                     const raw_frame_desc_t *src_frame,
                                     void *dst_yuy2_buf,
                                     size_t dst_buf_len);

/**
 * Release an acquired frame back to the ISP / DMM ring buffer.
 */
int raw_frame_source_release(raw_frame_source_ctx_t *ctx, raw_frame_desc_t *frame_desc);

/**
 * Teardown and close all allocated resources.
 */
void raw_frame_source_teardown(raw_frame_source_ctx_t *ctx);

/* Standalone Conversion Kernels & Utilities */
int raw_frame_convert_nv16_to_yuy2(const uint8_t *y_plane, size_t y_stride,
                                  const uint8_t *uv_plane, size_t uv_stride,
                                  uint8_t *dst_yuy2, size_t dst_stride,
                                  uint32_t width, uint32_t height);

int raw_frame_convert_nv12_to_yuy2(const uint8_t *y_plane, size_t y_stride,
                                  const uint8_t *uv_plane, size_t uv_stride,
                                  uint8_t *dst_yuy2, size_t dst_stride,
                                  uint32_t width, uint32_t height);

int raw_frame_copy_yuy2(const uint8_t *src_yuy2, size_t src_stride,
                        uint8_t *dst_yuy2, size_t dst_stride,
                        uint32_t width, uint32_t height);

int raw_frame_generate_synthetic_fallback(uint8_t *dst_yuy2,
                                         uint32_t width, uint32_t height,
                                         uint32_t frame_counter);

int raw_frame_stream_mmap(int fd_stream, uint32_t phys_addr, size_t len,
                          void **out_mapping, size_t *out_map_len, void **out_vaddr);

int raw_frame_stream_munmap(void *mapping, size_t map_len);

#ifdef __cplusplus
}
#endif

#endif /* RAW_FRAME_SOURCE_H */
