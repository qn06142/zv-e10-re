/* STATUS: default/ARM implementation is fail-closed. The historical identifiers,
 * command structures and pixel-plane claims below are HOST TEST FIXTURES, not a
 * recovered Sony acquisition ABI. Do not enable them for camera work.
 * Genuine wire/metadata helpers are in verified_yc/; source packing and frame
 * acquisition remain unresolved. See docs/uvc_yc_live_source_20261026.md.
 */
/**
 * @file raw_live_sony.h
 * @brief Concrete Sony Completed-YC Frame Source Backend for Sony ZV-E10 (CXD90045).
 *
 * Implements the concrete Sony live-source backend conforming to raw_live_ops,
 * binding to Revision 2.5 transport while preserving proven USB completion fences,
 * synthetic color bar fallback, and target CPU constraints (Cortex-A5, no NEON).
 *
 * Reverse-engineered structures:
 * - PIN_YC_IMAGE_SIZE_INFO (60 bytes)
 * - PIN_YC_YC_STATE_INFO (6 bytes)
 * - PIN_PROPERTY (16 bytes, pin key 0x00550101, queue 0x01670464)
 * - dmm_extent_t (40 bytes, plane 0 Y, plane 1 interleaved UV)
 */

#ifndef RAW_LIVE_SONY_H
#define RAW_LIVE_SONY_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include "raw_live_source.h"

#ifdef __cplusplus
extern "C" {
#endif

/* =========================================================================
 * 1. Sony Subsystem, Pin, and Command Identifiers
 * ========================================================================= */

#define SONY_VDF_SUBSYSTEM_ID           0x00000055u /* VDF Video Dataflow Subsystem */
#define SONY_VDF_UNIT_ID                0x00000001u /* Unit 0x01: Frame Source */
#define SONY_VDF_PIN_ID                 0x00000001u /* Pin 0x01: Completed Preview Stream */
#define SONY_VDF_QUEUE_ID               0x01670464u /* RTOS Routing Queue from table at 0x63e96f90 */

/* 24-bit composite PinKey = (subsystem << 16) | (unit << 8) | pin */
#define SONY_PIN_KEY(sub, unit, pin)    (((uint32_t)(sub) << 16) | ((uint32_t)(unit) << 8) | (uint32_t)(pin))
#define SONY_VDF_PIN_KEY                SONY_PIN_KEY(SONY_VDF_SUBSYSTEM_ID, SONY_VDF_UNIT_ID, SONY_VDF_PIN_ID) /* 0x00550101u */

/* Master Pin Management Commands (DataflowInfra command 0x1000) */
#define SONY_CMD_PIN                    0x00001000u
#define SONY_SUBCMD_PIN_CONNECT         0x00000001u /* INFRA_CONNECT_PIN */
#define SONY_SUBCMD_PIN_GET             0x00000002u /* INFRA_GET_PIN */
#define SONY_SUBCMD_PIN_DISCONNECT      0x00000003u /* INFRA_DISCONNECT_PIN */

/* MemoryHandle IPC Protocol (FC::MemoryHandle in fc_lib_image / fc_api_monitoring) */
#define SONY_IPC_OPCODE_MEMORY_HANDLE   0x00000400u
#define SONY_IPC_SUBCMD_MEM_OPEN        0x00000003u /* Open / Acquire Lease (locks prc_mem_handle) */
#define SONY_IPC_SUBCMD_MEM_CLOSE       0x00000004u /* Close / Release Lease (unlocks prc_mem_handle) */

/* DMM Ownership Constraints */
#define SONY_DMM_UNIT_UVC_WORKSPACE     0x00000276u /* Exclusive Patched UVC Destination Unit */
#define SONY_DMM_EXTENT_SRC_WORKSPACE   0x00000333u /* Extent 0x333 (3,276,800 bytes) */

/* Geometry Constants */
#define SONY_FRAME_WIDTH                640u
#define SONY_FRAME_HEIGHT               480u
#define SONY_YUY2_ROW_STRIDE            (SONY_FRAME_WIDTH * 2u) /* 1,280 bytes */
#define SONY_YUY2_FRAME_BYTES           (SONY_YUY2_ROW_STRIDE * SONY_FRAME_HEIGHT) /* 614,400 bytes */
#define SONY_NV16_LUMA_BYTES            (SONY_FRAME_WIDTH * SONY_FRAME_HEIGHT)      /* 307,200 bytes */
#define SONY_NV16_CHROMA_BYTES          (SONY_FRAME_WIDTH * SONY_FRAME_HEIGHT)      /* 307,200 bytes */

/* =========================================================================
 * 2. Reverse-Engineered Hardware Structure Aliases & Assertions
 * ========================================================================= */

/* Typedef aliases matching exact definitions in raw_frame_source.h */
typedef struct PIN_YC_IMAGE_SIZE_INFO PIN_YC_IMAGE_SIZE_INFO;
typedef struct PIN_YC_YC_STATE_INFO PIN_YC_YC_STATE_INFO;

/* Compile-time structure size assertions */
#if defined(__STDC_VERSION__) && (__STDC_VERSION__ >= 201112L)
_Static_assert(sizeof(PIN_YC_IMAGE_SIZE_INFO) == 60, "PIN_YC_IMAGE_SIZE_INFO must be 60 bytes");
_Static_assert(sizeof(PIN_YC_YC_STATE_INFO) == 6, "PIN_YC_YC_STATE_INFO must be 6 bytes");
_Static_assert(sizeof(PIN_PROPERTY) == 16, "PIN_PROPERTY must be 16 bytes");
_Static_assert(sizeof(dmm_extent_t) == 40, "dmm_extent_t must be 40 bytes");
#endif

/* =========================================================================
 * 3. Transport Hooks and Context
 * ========================================================================= */

/**
 * Low-level IPC message callback hook (for MemoryHandle Open/Close).
 * Allows plugging genuine Linux/RTOS message queues or offline test harnesses.
 */
typedef int (*sony_ipc_msg_fn)(void *transport_ctx, uint32_t queue_id, uint32_t opcode,
                               uint32_t subcmd, uint16_t handle, void *io_payload,
                               size_t payload_len, uint32_t timeout_ms);

/**
 * Memory mapping hook for physical plane translation.
 * Maps physical address via /dev/stream (or mock buffer in offline tests).
 */
typedef int (*sony_mmap_fn)(void *transport_ctx, uint32_t phys_addr, size_t len,
                            void **out_base, const uint8_t **out_data, size_t *out_len);
typedef int (*sony_munmap_fn)(void *transport_ctx, void *base, size_t len);

/**
 * Backend context for Sony completed-YC frame source.
 */
typedef struct {
    /* Subscription & Routing */
    uint32_t target_queue_id;        /* Default: SONY_VDF_QUEUE_ID (0x01670464) */
    uint32_t pin_key;                /* Default: SONY_VDF_PIN_KEY (0x00550101) */
    uint32_t owned_staging_unit;     /* Default: SONY_DMM_UNIT_UVC_WORKSPACE (0x0276) */
    uint32_t staging_physical;       /* Physical base address of owned Unit 0x276 */
    
    /* Hardware / Simulated Transport Hooks */
    void *transport_ctx;
    sony_ipc_msg_fn ipc_msg;         /* IPC message send hook */
    sony_mmap_fn stream_mmap;        /* /dev/stream mmap hook */
    sony_munmap_fn stream_munmap;    /* /dev/stream munmap hook */

    /* Active State & Lease Tracking */
    int is_subscribed;               /* 1 if subscribed to VDF pin */
    uint32_t sequence;               /* Monotonic frame sequence counter */
    uintptr_t active_lease_token;    /* Non-zero while an acquired frame lease is held */
    uint16_t active_unit_handle;     /* Active DMM unit handle */

    /* Reverse-Engineered Metadata Cache */
    PIN_YC_IMAGE_SIZE_INFO last_size_info;
    PIN_YC_YC_STATE_INFO last_state_info;
    dmm_extent_t last_extent;

    /* USB Completion Fence Guard */
    int host_ebusy;                  /* 1 if USB host transfer is in-flight (EBUSY) */

    /* Telemetry / Statistics */
    uint32_t total_acquired;
    uint32_t total_released;
    uint32_t total_timeouts;
    uint32_t total_errors;
    uint32_t total_fence_blocks;

    /* Fallback and Test Hooks */
    int simulated_frame_ready;       /* 1 if simulated frame is primed in test mode */
} raw_live_sony_context_t;

/* =========================================================================
 * 4. Exported Functions & raw_live_ops Interface
 * ========================================================================= */

/**
 * Initialize a Sony live frame source backend context.
 */
int raw_live_sony_init(raw_live_sony_context_t *ctx);

/**
 * Update USB completion fence state.
 * When ebusy != 0, acquisition is blocked to prevent mutating frames during in-flight DMA.
 */
void raw_live_sony_set_host_ebusy(raw_live_sony_context_t *ctx, int ebusy);

/**
 * Validate that destination buffer belongs to exclusively owned Unit 0x276.
 */
int raw_live_sony_validate_destination(raw_live_sony_context_t *ctx, uint32_t dest_unit_type,
                                       uint32_t dest_phys, size_t dest_len);

/**
 * Acquire a frame lease from the Sony VDF pipeline.
 * Honors timeout <= 10 ms; returns RAW_FRAME_ERR_* on timeout or error with token = 0.
 */
int raw_live_sony_acquire(void *opaque, uint32_t timeout_ms, raw_live_frame *out);

/**
 * Release an active frame lease via MemoryHandle Close protocol.
 * On release failure, retains active_lease_token so release can be retried.
 */
int raw_live_sony_release(void *opaque, uintptr_t token);

/**
 * Read-only memory map for physical plane DRAM address.
 * Page-aligns address for /dev/stream non-cached mapping.
 */
int raw_live_sony_map_readonly(void *opaque, const raw_live_plane *plane, size_t needed_bytes, raw_live_mapping *out);

/**
 * Unmap virtual memory mapping.
 */
int raw_live_sony_unmap(void *opaque, raw_live_mapping *mapping);

/**
 * Global raw_live_ops instance for Sony completed-YC source.
 */
extern const raw_live_ops raw_live_sony_ops;

#ifdef RAW_LIVE_TARGET_ARM
extern int yuy2_live_bind(const raw_live_ops *ops, void *opaque);
extern int yuy2_live_unbind(void);
#endif

/**
 * Configure dynamic or mock binding callbacks for Revision 2.5 transport.
 */
void raw_live_sony_set_transport_bind_fn(int (*bind_fn)(const raw_live_ops *, void *),
                                         int (*unbind_fn)(void));

/**
 * Helper to bind this Sony backend to Revision 2.5 transport via yuy2_live_bind.
 */
int raw_live_sony_bind(raw_live_sony_context_t *ctx);

/**
 * Helper to unbind this Sony backend via yuy2_live_unbind.
 */
int raw_live_sony_unbind(void);

#ifdef __cplusplus
}
#endif

#endif /* RAW_LIVE_SONY_H */
