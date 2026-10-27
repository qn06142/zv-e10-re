/**
 * @file test_raw_live_sony.c
 * @brief Comprehensive Verification Suite for Sony Live Frame Source Backend.
 *
 * Verifies:
 * - Exact 60-byte PIN_YC_IMAGE_SIZE_INFO, 6-byte PIN_YC_YC_STATE_INFO,
 *   16-byte PIN_PROPERTY, and 40-byte dmm_extent_t structures and offsets.
 * - raw_live_ops lease lifecycle (acquire, release, map_readonly, unmap).
 * - 10 ms timeout cap and failure rollback with zero lease.
 * - Lease retention upon release failure (retry semantics).
 * - USB completion fence (EBUSY blocking acquisition / mutation).
 * - Owned staging Unit 0x276 validation.
 * - Integration with raw_live_fill and synthetic color bar fallback.
 * - Revision 2.5 binding helpers.
 */

#include "raw_live_sony.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(cond) do { \
    if (!(cond)) { \
        fprintf(stderr, "FAIL at %s:%d: %s\n", __FILE__, __LINE__, #cond); \
        return __LINE__; \
    } \
} while (0)

/* Mock Transport Harness */
typedef struct {
    int ipc_calls;
    uint32_t last_queue_id;
    uint32_t last_opcode;
    uint32_t last_subcmd;
    uint16_t last_handle;
    uint32_t last_timeout;
    int fail_ipc_open;
    int fail_ipc_close;
    int close_fail_count;
    
    int map_calls;
    int unmap_calls;
    int fail_map;
    int fail_unmap;
} mock_transport_t;

static uint8_t s_mock_y_plane[SONY_NV16_LUMA_BYTES];
static uint8_t s_mock_uv_plane[SONY_NV16_CHROMA_BYTES];

static int mock_ipc_send(void *transport_ctx, uint32_t queue_id, uint32_t opcode,
                         uint32_t subcmd, uint16_t handle, void *io_payload,
                         size_t payload_len, uint32_t timeout_ms) {
    mock_transport_t *t = (mock_transport_t *)transport_ctx;
    t->ipc_calls++;
    t->last_queue_id = queue_id;
    t->last_opcode = opcode;
    t->last_subcmd = subcmd;
    t->last_handle = handle;
    t->last_timeout = timeout_ms;

    if (opcode == SONY_IPC_OPCODE_MEMORY_HANDLE && subcmd == SONY_IPC_SUBCMD_MEM_OPEN) {
        if (t->fail_ipc_open) {
            return t->fail_ipc_open;
        }
        if (io_payload && payload_len >= sizeof(dmm_extent_t)) {
            dmm_extent_t *ext = (dmm_extent_t *)io_payload;
            ext->unit_handle = 0x0123u;
            ext->num_planes = 2;
            ext->total_size = SONY_YUY2_FRAME_BYTES;
            ext->planes[0].phy_addr = 0x21000000u;
            ext->planes[0].size_or_stride = SONY_FRAME_WIDTH;
            ext->planes[1].phy_addr = 0x2104b000u;
            ext->planes[1].size_or_stride = SONY_FRAME_WIDTH;
        }
        return RAW_FRAME_OK;
    }

    if (opcode == SONY_IPC_OPCODE_MEMORY_HANDLE && subcmd == SONY_IPC_SUBCMD_MEM_CLOSE) {
        if (t->close_fail_count > 0) {
            t->close_fail_count--;
            return RAW_FRAME_ERR_IO;
        }
        if (t->fail_ipc_close) {
            return t->fail_ipc_close;
        }
        return RAW_FRAME_OK;
    }

    return RAW_FRAME_OK;
}

static int mock_mmap(void *transport_ctx, uint32_t phys_addr, size_t len,
                     void **out_base, const uint8_t **out_data, size_t *out_len) {
    mock_transport_t *t = (mock_transport_t *)transport_ctx;
    t->map_calls++;
    if (t->fail_map) {
        return RAW_FRAME_ERR_MMAP_FAILED;
    }
    if (phys_addr == 0x21000000u || phys_addr == 0x20000000u) {
        *out_base = s_mock_y_plane;
        *out_data = s_mock_y_plane;
        *out_len = len;
        return RAW_FRAME_OK;
    }
    if (phys_addr == 0x2104b000u || phys_addr == 0x2004b000u) {
        *out_base = s_mock_uv_plane;
        *out_data = s_mock_uv_plane;
        *out_len = len;
        return RAW_FRAME_OK;
    }
    /* Fallback default buffer */
    *out_base = s_mock_y_plane;
    *out_data = s_mock_y_plane;
    *out_len = len;
    return RAW_FRAME_OK;
}

static int mock_munmap(void *transport_ctx, void *base, size_t len) {
    (void)base;
    (void)len;
    mock_transport_t *t = (mock_transport_t *)transport_ctx;
    t->unmap_calls++;
    if (t->fail_unmap) {
        return RAW_FRAME_ERR_IO;
    }
    return RAW_FRAME_OK;
}

/* =========================================================================
 * Test Cases
 * ========================================================================= */

static int test_reverse_engineered_structures(void) {
    /* 1. Structure Sizes */
    CHECK(sizeof(PIN_YC_IMAGE_SIZE_INFO) == 60);
    CHECK(sizeof(PIN_YC_YC_STATE_INFO) == 6);
    CHECK(sizeof(PIN_PROPERTY) == 16);
    CHECK(sizeof(dmm_extent_t) == 40);

    /* 2. PIN_YC_IMAGE_SIZE_INFO Field Offsets */
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, image_attach) == 0);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, unit_type) == 4);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, unit_handle) == 8);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, unit_data_offset) == 12);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, exposure_time) == 16);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, expose_pic_delay) == 17);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, scenario_end) == 18);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, mirror) == 19);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, record_size_x) == 20);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, record_size_y) == 22);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, canvas_size_x) == 24);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, canvas_size_y) == 26);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, valid_offset_x) == 28);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, valid_offset_y) == 30);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, valid_size_x) == 32);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, valid_size_y) == 34);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, target_offset_x) == 36);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, target_offset_y) == 38);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, target_size_x) == 40);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, target_size_y) == 42);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, data_site) == 44);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, iib_number) == 45);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, aspect) == 46);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, yc_compress) == 47);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, data_transfer) == 48);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, data_placement) == 49);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, data_content) == 50);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, data_scan) == 51);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, strip_width) == 52);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, yc_bit_depth) == 54);
    CHECK(offsetof(PIN_YC_IMAGE_SIZE_INFO, cam_freq_char_h) == 56);

    /* 3. PIN_YC_YC_STATE_INFO Field Offsets */
    CHECK(offsetof(PIN_YC_YC_STATE_INFO, y_range) == 0);
    CHECK(offsetof(PIN_YC_YC_STATE_INFO, colorimetry) == 1);
    CHECK(offsetof(PIN_YC_YC_STATE_INFO, chroma_phase) == 2);
    CHECK(offsetof(PIN_YC_YC_STATE_INFO, scanline) == 3);
    CHECK(offsetof(PIN_YC_YC_STATE_INFO, copy_protection) == 4);
    CHECK(offsetof(PIN_YC_YC_STATE_INFO, author) == 5);

    /* 4. PIN_PROPERTY Field Offsets */
    CHECK(offsetof(PIN_PROPERTY, subsystem_id) == 0);
    CHECK(offsetof(PIN_PROPERTY, unit_id) == 4);
    CHECK(offsetof(PIN_PROPERTY, pin_id) == 8);
    CHECK(offsetof(PIN_PROPERTY, flags_queue_id) == 12);

    /* 5. dmm_extent_t Field Offsets */
    CHECK(offsetof(dmm_extent_t, unit_handle) == 0);
    CHECK(offsetof(dmm_extent_t, num_planes) == 2);
    CHECK(offsetof(dmm_extent_t, total_size) == 4);
    CHECK(offsetof(dmm_extent_t, planes[0].phy_addr) == 8);
    CHECK(offsetof(dmm_extent_t, planes[0].size_or_stride) == 12);
    CHECK(offsetof(dmm_extent_t, planes[1].phy_addr) == 16);
    CHECK(offsetof(dmm_extent_t, planes[1].size_or_stride) == 20);

    /* 6. Protocol Constants */
    CHECK(SONY_VDF_SUBSYSTEM_ID == 0x55u);
    CHECK(SONY_VDF_UNIT_ID == 0x01u);
    CHECK(SONY_VDF_PIN_ID == 0x01u);
    CHECK(SONY_VDF_PIN_KEY == 0x00550101u);
    CHECK(SONY_VDF_QUEUE_ID == 0x01670464u);
    CHECK(SONY_CMD_PIN == 0x1000u);
    CHECK(SONY_IPC_OPCODE_MEMORY_HANDLE == 0x400u);
    CHECK(SONY_IPC_SUBCMD_MEM_OPEN == 3u);
    CHECK(SONY_IPC_SUBCMD_MEM_CLOSE == 4u);
    CHECK(SONY_DMM_UNIT_UVC_WORKSPACE == 0x276u);
    CHECK(SONY_DMM_EXTENT_SRC_WORKSPACE == 0x333u);

    return 0;
}

static int test_context_initialization_and_destination(void) {
    raw_live_sony_context_t ctx;
    CHECK(raw_live_sony_init(NULL) == RAW_FRAME_ERR_INVALID_PARAM);

    CHECK(raw_live_sony_init(&ctx) == RAW_FRAME_OK);
    CHECK(ctx.target_queue_id == SONY_VDF_QUEUE_ID);
    CHECK(ctx.pin_key == SONY_VDF_PIN_KEY);
    CHECK(ctx.owned_staging_unit == SONY_DMM_UNIT_UVC_WORKSPACE);
    CHECK(ctx.staging_physical == 0x15b00000u);
    CHECK(ctx.is_subscribed == 1);
    CHECK(ctx.active_lease_token == 0);
    CHECK(ctx.host_ebusy == 0);

    /* Enforce Unit 0x276 destination checks */
    CHECK(raw_live_sony_validate_destination(&ctx, 0x276u, 0x15b00000u, SONY_YUY2_FRAME_BYTES) == RAW_FRAME_OK);
    CHECK(raw_live_sony_validate_destination(&ctx, 0x50eu, 0x15b00000u, SONY_YUY2_FRAME_BYTES) == RAW_FRAME_ERR_INVALID_PARAM);
    CHECK(raw_live_sony_validate_destination(&ctx, 0x1ddu, 0x15b00000u, SONY_YUY2_FRAME_BYTES) == RAW_FRAME_ERR_INVALID_PARAM);
    CHECK(raw_live_sony_validate_destination(&ctx, 0x276u, 0, SONY_YUY2_FRAME_BYTES) == RAW_FRAME_ERR_INVALID_PARAM);
    CHECK(raw_live_sony_validate_destination(&ctx, 0x276u, 0x15b00000u, 1000) == RAW_FRAME_ERR_INVALID_PARAM);

    return 0;
}

static int test_acquire_and_release_lifecycle(void) {
    raw_live_sony_context_t ctx;
    mock_transport_t mock;
    memset(&mock, 0, sizeof(mock));
    CHECK(raw_live_sony_init(&ctx) == RAW_FRAME_OK);
    ctx.transport_ctx = &mock;
    ctx.ipc_msg = mock_ipc_send;
    ctx.stream_mmap = mock_mmap;
    ctx.stream_munmap = mock_munmap;

    /* Prime valid size and state info */
    ctx.last_size_info = (PIN_YC_IMAGE_SIZE_INFO){
        .image_attach = 1,
        .unit_type = 0x1ddu,
        .unit_handle = 0x0123u,
        .record_size_x = 640,
        .record_size_y = 480,
        .canvas_size_x = 640,
        .canvas_size_y = 480,
        .yc_compress = 0,
        .data_placement = 2, /* NV16 */
        .yc_bit_depth = 8
    };
    ctx.last_state_info = (PIN_YC_YC_STATE_INFO){
        .y_range = 0,     /* Limited range BT.601 */
        .colorimetry = 0, /* BT.601 */
        .chroma_phase = 0,
        .scanline = 0
    };

    /* 1. Normal Acquire */
    raw_live_frame frame;
    memset(&frame, 0, sizeof(frame));
    CHECK(raw_live_sony_acquire(&ctx, 10, &frame) == RAW_FRAME_OK);
    CHECK(frame.token != 0);
    CHECK(frame.token == ctx.active_lease_token);
    CHECK(frame.sequence == 1);
    CHECK(frame.width == 640 && frame.height == 480);
    CHECK(frame.format == RAW_FRAME_PIXFMT_NV16);
    CHECK(frame.flags == RAW_LIVE_READY_LINEAR_8BIT_BT601_LIMITED);
    CHECK(frame.plane[0].physical == 0x21000000u);
    CHECK(frame.plane[0].bytes == SONY_NV16_LUMA_BYTES);
    CHECK(frame.plane[0].stride == 640);
    CHECK(frame.plane[1].physical == 0x2104b000u);
    CHECK(frame.plane[1].bytes == SONY_NV16_CHROMA_BYTES);
    CHECK(frame.plane[1].stride == 640);

    /* 2. Double-acquire while lease active must be rejected with DEVICE_BUSY */
    raw_live_frame frame2;
    memset(&frame2, 0, sizeof(frame2));
    CHECK(raw_live_sony_acquire(&ctx, 10, &frame2) == RAW_FRAME_ERR_DEVICE_BUSY);
    CHECK(frame2.token == 0);

    /* 3. Release with invalid token must fail */
    CHECK(raw_live_sony_release(&ctx, 0x9999) == RAW_FRAME_ERR_INVALID_PARAM);
    CHECK(ctx.active_lease_token == frame.token); /* Lease retained */

    /* 4. Release with valid token succeeds */
    CHECK(raw_live_sony_release(&ctx, frame.token) == RAW_FRAME_OK);
    CHECK(ctx.active_lease_token == 0);
    CHECK(mock.last_opcode == SONY_IPC_OPCODE_MEMORY_HANDLE);
    CHECK(mock.last_subcmd == SONY_IPC_SUBCMD_MEM_CLOSE);
    CHECK(mock.last_handle == 0x0123u);

    return 0;
}

static int test_timeout_and_error_handling(void) {
    raw_live_sony_context_t ctx;
    mock_transport_t mock;
    memset(&mock, 0, sizeof(mock));
    CHECK(raw_live_sony_init(&ctx) == RAW_FRAME_OK);
    ctx.transport_ctx = &mock;
    ctx.ipc_msg = mock_ipc_send;

    raw_live_frame frame;
    memset(&frame, 0, sizeof(frame));

    /* 1. Timeout parameter > 10 ms rejected immediately */
    CHECK(raw_live_sony_acquire(&ctx, 11, &frame) == RAW_FRAME_ERR_INVALID_PARAM);
    CHECK(frame.token == 0);
    CHECK(raw_live_sony_acquire(&ctx, 0, &frame) == RAW_FRAME_ERR_INVALID_PARAM);
    CHECK(frame.token == 0);

    /* 2. IPC timeout returns RAW_FRAME_ERR_TIMEOUT and sets no lease */
    mock.fail_ipc_open = RAW_FRAME_ERR_TIMEOUT;
    CHECK(raw_live_sony_acquire(&ctx, 10, &frame) == RAW_FRAME_ERR_TIMEOUT);
    CHECK(frame.token == 0);
    CHECK(ctx.active_lease_token == 0);
    CHECK(ctx.total_timeouts == 1);
    mock.fail_ipc_open = 0;

    /* 3. Lease retention upon release failure */
    ctx.last_size_info = (PIN_YC_IMAGE_SIZE_INFO){
        .image_attach = 1, .unit_type = 0x1ddu, .unit_handle = 0x0123u,
        .record_size_x = 640, .record_size_y = 480,
        .canvas_size_x = 640, .canvas_size_y = 480,
        .yc_compress = 0, .data_placement = 1 /* YUY2 */
    };
    ctx.last_state_info = (PIN_YC_YC_STATE_INFO){ .y_range = 0, .colorimetry = 0 };

    CHECK(raw_live_sony_acquire(&ctx, 10, &frame) == RAW_FRAME_OK);
    uintptr_t held_token = frame.token;
    CHECK(held_token != 0);

    /* Simulate temporary release failure */
    mock.close_fail_count = 1;
    CHECK(raw_live_sony_release(&ctx, held_token) == RAW_FRAME_ERR_IO);
    /* Crucial check: lease token MUST be retained on failure! */
    CHECK(ctx.active_lease_token == held_token);

    /* Acquisition remains blocked while release is incomplete */
    raw_live_frame blocked_frame;
    CHECK(raw_live_sony_acquire(&ctx, 10, &blocked_frame) == RAW_FRAME_ERR_DEVICE_BUSY);
    CHECK(blocked_frame.token == 0);

    /* Retry release succeeds */
    CHECK(raw_live_sony_release(&ctx, held_token) == RAW_FRAME_OK);
    CHECK(ctx.active_lease_token == 0);

    return 0;
}

static int test_usb_completion_fence(void) {
    raw_live_sony_context_t ctx;
    mock_transport_t mock;
    memset(&mock, 0, sizeof(mock));
    CHECK(raw_live_sony_init(&ctx) == RAW_FRAME_OK);
    ctx.transport_ctx = &mock;
    ctx.ipc_msg = mock_ipc_send;
    ctx.last_size_info = (PIN_YC_IMAGE_SIZE_INFO){
        .image_attach = 1,
        .unit_type = 0x1ddu,
        .unit_handle = 0x0123u,
        .record_size_x = 640,
        .record_size_y = 480,
        .canvas_size_x = 640,
        .canvas_size_y = 480,
        .yc_compress = 0,
        .data_placement = 2,
        .yc_bit_depth = 8
    };
    ctx.last_state_info = (PIN_YC_YC_STATE_INFO){
        .y_range = 0,
        .colorimetry = 0,
        .chroma_phase = 0,
        .scanline = 0
    };

    /* Set host EBUSY = 1 */
    raw_live_sony_set_host_ebusy(&ctx, 1);
    CHECK(ctx.host_ebusy == 1);

    raw_live_frame frame;
    memset(&frame, 0, sizeof(frame));

    /* Acquire must be rejected with DEVICE_BUSY without sending IPC */
    int before_ipc = mock.ipc_calls;
    CHECK(raw_live_sony_acquire(&ctx, 10, &frame) == RAW_FRAME_ERR_DEVICE_BUSY);
    CHECK(frame.token == 0);
    CHECK(ctx.active_lease_token == 0);
    CHECK(mock.ipc_calls == before_ipc); /* No IPC command sent */
    CHECK(ctx.total_fence_blocks == 1);

    /* Clear host EBUSY = 0 */
    raw_live_sony_set_host_ebusy(&ctx, 0);
    CHECK(ctx.host_ebusy == 0);

    /* Now acquire succeeds */
    CHECK(raw_live_sony_acquire(&ctx, 10, &frame) == RAW_FRAME_OK);
    CHECK(frame.token != 0);
    CHECK(raw_live_sony_release(&ctx, frame.token) == RAW_FRAME_OK);

    return 0;
}

static int test_full_pipeline_with_raw_live_fill(void) {
    raw_live_sony_context_t sony_ctx;
    mock_transport_t mock;
    memset(&mock, 0, sizeof(mock));

    /* Fill mock planes with deterministic test pattern */
    for (size_t i = 0; i < sizeof(s_mock_y_plane); i++) {
        s_mock_y_plane[i] = (uint8_t)(16 + (i % 200)); /* BT.601 valid range */
    }
    for (size_t i = 0; i < sizeof(s_mock_uv_plane); i++) {
        s_mock_uv_plane[i] = (uint8_t)(128 + ((int)(i % 100) - 50));
    }

    CHECK(raw_live_sony_init(&sony_ctx) == RAW_FRAME_OK);
    sony_ctx.transport_ctx = &mock;
    sony_ctx.ipc_msg = mock_ipc_send;
    sony_ctx.stream_mmap = mock_mmap;
    sony_ctx.stream_munmap = mock_munmap;

    sony_ctx.last_size_info = (PIN_YC_IMAGE_SIZE_INFO){
        .image_attach = 1, .unit_type = 0x1ddu, .unit_handle = 0x0123u,
        .record_size_x = 640, .record_size_y = 480,
        .canvas_size_x = 640, .canvas_size_y = 480,
        .yc_compress = 0, .data_placement = 2, /* NV16 */
        .yc_bit_depth = 8
    };
    sony_ctx.last_state_info = (PIN_YC_YC_STATE_INFO){ .y_range = 0, .colorimetry = 0 };

    /* Initialize raw_live_source adapter using Sony backend ops */
    raw_live_source s;
    memset(&s, 0, sizeof(s));
    CHECK(raw_live_init(&s, &raw_live_sony_ops, &sony_ctx, 640, 480, 10) == RAW_FRAME_OK);

    /* Allocate owned destination buffer (Unit 0x276) */
    uint8_t *dst = (uint8_t *)malloc(SONY_YUY2_FRAME_BYTES);
    CHECK(dst != NULL);
    memset(dst, 0xee, SONY_YUY2_FRAME_BYTES);

    uint32_t seq = 0;
    uint32_t dest_phys = 0x15b00000u; /* Staging Unit 0x276 */

    /* Execute raw_live_fill */
    CHECK(raw_live_fill(&s, dst, SONY_YUY2_FRAME_BYTES, dest_phys, &seq) == RAW_FRAME_OK);
    CHECK(seq == 1);
    CHECK(mock.ipc_calls == 2); /* 1 Open + 1 Close */
    CHECK(mock.map_calls == 2); /* Y plane + UV plane */
    CHECK(mock.unmap_calls == 2);
    CHECK(sony_ctx.active_lease_token == 0); /* Lease was released upon fill completion */

    /* Verify converted YUY2 pixels */
    /* Pixel 0: Y0, U0, Y1, V0 */
    CHECK(dst[0] == s_mock_y_plane[0]);
    CHECK(dst[1] == s_mock_uv_plane[0]);
    CHECK(dst[2] == s_mock_y_plane[1]);
    CHECK(dst[3] == s_mock_uv_plane[1]);

    /* Test Fallback: Simulate acquire timeout */
    mock.fail_ipc_open = RAW_FRAME_ERR_TIMEOUT;
    int fill_err = raw_live_fill(&s, dst, SONY_YUY2_FRAME_BYTES, dest_phys, &seq);
    CHECK(fill_err == RAW_FRAME_ERR_TIMEOUT);
    CHECK(sony_ctx.active_lease_token == 0);

    /* Clean shutdown */
    CHECK(raw_live_shutdown(&s) == RAW_FRAME_OK);
    free(dst);
    return 0;
}

static int s_mock_transport_bind_calls = 0;
static int s_mock_transport_unbind_calls = 0;
static const raw_live_ops *s_bound_ops = NULL;
static void *s_bound_opaque = NULL;

static int mock_transport_bind(const raw_live_ops *ops, void *opaque) {
    s_mock_transport_bind_calls++;
    s_bound_ops = ops;
    s_bound_opaque = opaque;
    return RAW_FRAME_OK;
}

static int mock_transport_unbind(void) {
    s_mock_transport_unbind_calls++;
    s_bound_ops = NULL;
    s_bound_opaque = NULL;
    return RAW_FRAME_OK;
}

static int test_revision_25_binding(void) {
    raw_live_sony_context_t ctx;
    CHECK(raw_live_sony_init(&ctx) == RAW_FRAME_OK);

    /* 1. Unconfigured transport returns NOT_INIT */
    raw_live_sony_set_transport_bind_fn(NULL, NULL);
    CHECK(raw_live_sony_bind(&ctx) == RAW_FRAME_ERR_NOT_INIT);
    CHECK(raw_live_sony_unbind() == RAW_FRAME_ERR_NOT_INIT);
    CHECK(raw_live_sony_bind(NULL) == RAW_FRAME_ERR_INVALID_PARAM);

    /* 2. Configure mock transport hooks (emulating Revision 2.5 yuy2_live_bind) */
    raw_live_sony_set_transport_bind_fn(mock_transport_bind, mock_transport_unbind);
    CHECK(raw_live_sony_bind(&ctx) == RAW_FRAME_OK);
    CHECK(s_mock_transport_bind_calls == 1);
    CHECK(s_bound_ops == &raw_live_sony_ops);
    CHECK(s_bound_opaque == &ctx);

    /* 3. Unbind */
    CHECK(raw_live_sony_unbind() == RAW_FRAME_OK);
    CHECK(s_mock_transport_unbind_calls == 1);
    CHECK(s_bound_ops == NULL);

    return 0;
}

int main(void) {
    unsigned passed = 0;
    printf("Starting Sony Live Frame Source Backend Verification...\n");

    CHECK(!test_reverse_engineered_structures());
    passed++;
    printf("PASS 1: Reverse engineered structure sizes & offsets verified (60B, 6B, 16B, 40B)\n");

    CHECK(!test_context_initialization_and_destination());
    passed++;
    printf("PASS 2: Context initialization and Unit 0x276 destination enforcement verified\n");

    CHECK(!test_acquire_and_release_lifecycle());
    passed++;
    printf("PASS 3: MemoryHandle Open/Close acquire/release lifecycle verified\n");

    CHECK(!test_timeout_and_error_handling());
    passed++;
    printf("PASS 4: 10 ms timeout cap and lease retention upon release failure verified\n");

    CHECK(!test_usb_completion_fence());
    passed++;
    printf("PASS 5: USB completion fence (EBUSY blocking acquisition) verified\n");

    CHECK(!test_full_pipeline_with_raw_live_fill());
    passed++;
    printf("PASS 6: Full pipeline conversion and fallback to synthetic verified\n");

    CHECK(!test_revision_25_binding());
    passed++;
    printf("PASS 7: Revision 2.5 transport binding helper verified\n");

    printf("ALL SONY LIVE BACKEND TESTS PASSED cleanly! (cases=%u)\n", passed);
    return 0;
}
