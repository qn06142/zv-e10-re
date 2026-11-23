#ifndef RAW_SOURCE_FILE_H
#define RAW_SOURCE_FILE_H
#include <stdint.h>

#define RAW_UVC_WIDTH       6144u
#define RAW_UVC_HEIGHT      4100u
#define RAW_UVC_FRAME_BYTES (RAW_UVC_WIDTH * RAW_UVC_HEIGHT * 2u) /* 50,380,800 = 82 * 614,400 */
#define RAW_UVC_CHUNK_BYTES 614400u
#define RAW_UVC_HDR_BYTES   64u
#define RAW_UVC_MAX_PAYLOAD (RAW_UVC_FRAME_BYTES - RAW_UVC_HDR_BYTES)

typedef struct {
    uint16_t op, tag;
    uint32_t address, bytes;
    uint8_t sequence, mode, a, b;
    uint32_t c, d;
} raw_capture_packet;

int raw_source_prepare(unsigned frame_seq, unsigned char hdr[RAW_UVC_HDR_BYTES], uint32_t *out_raw_bytes);
int raw_source_read_chunk(const unsigned char hdr[RAW_UVC_HDR_BYTES], uint32_t raw_bytes,
                          unsigned frame_offset, unsigned char *dst, unsigned chunk_len);
void raw_source_close(void);
uint32_t raw_crc32_ieee(uint32_t init, const unsigned char *buf, unsigned len);

#endif
