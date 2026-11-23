#include "raw_source_file.h"
#include <stddef.h>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#include <string.h>
#define RAW_OPEN_RDONLY (_O_RDONLY | _O_BINARY)
#else
#define RAW_OPEN_RDONLY 0
extern int open(const char *, int, ...), close(int), read(int, void *, unsigned);
extern long lseek(int, long, int);
extern void *memset(void *, int, unsigned), *memcpy(void *, const void *, unsigned);
extern int memcmp(const void *, const void *, unsigned);
#endif

#ifndef RAW_CAPTURE_DIR
#define RAW_CAPTURE_DIR "/log/raw_capture_v01"
#endif
#define REQ_PATH  RAW_CAPTURE_DIR "/request.bin"
#define DONE_PATH RAW_CAPTURE_DIR "/complete.bin"
#define BIN_PATH  RAW_CAPTURE_DIR "/frame.bin"

static int g_bin_fd = -1;
static unsigned char g_last_pkt[24];
static unsigned char g_crc_buf[4096];
static uint32_t g_cached_crc = 0;
static uint32_t g_cached_size = 0;
static int g_have_cache = 0;

uint32_t raw_crc32_ieee(uint32_t crc, const unsigned char *buf, unsigned len) {
    crc = ~crc;
    for (unsigned i = 0; i < len; i++) {
        crc ^= buf[i];
        for (int b = 0; b < 8; b++)
            crc = (crc & 1u) ? ((crc >> 1) ^ 0xedb88320u) : (crc >> 1);
    }
    return ~crc;
}

static void put32(unsigned char *p, uint32_t v) {
    p[0] = (unsigned char)(v & 255u);
    p[1] = (unsigned char)((v >> 8) & 255u);
    p[2] = (unsigned char)((v >> 16) & 255u);
    p[3] = (unsigned char)((v >> 24) & 255u);
}

static int read_exact(const char *path, void *out, unsigned len) {
    int fd = open(path, RAW_OPEN_RDONLY);
    if (fd < 0) return -1;
    unsigned char *dst = out;
    unsigned got = 0;
    while (got < len) {
        int r = read(fd, dst + got, len - got);
        if (r <= 0) { close(fd); return -1; }
        got += (unsigned)r;
    }
    unsigned char extra;
    int tail = read(fd, &extra, 1);
    close(fd);
    return (tail == 0) ? 0 : -1;
}

void raw_source_close(void) {
    if (g_bin_fd >= 0) {
        close(g_bin_fd);
        g_bin_fd = -1;
    }
    g_have_cache = 0;
}

int raw_source_prepare(unsigned frame_seq, unsigned char hdr[RAW_UVC_HDR_BYTES], uint32_t *out_raw_bytes) {
    unsigned char req[24], done[24];
    if (read_exact(DONE_PATH, done, 24) < 0) return -1;
    if (read_exact(REQ_PATH, req, 24) < 0) return -2;
    if (memcmp(req, done, 24) != 0) return -3;

    raw_capture_packet pkt;
    memcpy(&pkt, done, 24);
    if (pkt.op != 1u || pkt.mode != 0u || (pkt.tag & 255u) != 1u) return -4;
    if (!pkt.bytes || pkt.bytes > RAW_UVC_MAX_PAYLOAD) return -5;

    if (!g_have_cache || g_bin_fd < 0 || memcmp(g_last_pkt, done, 24) != 0) {
        raw_source_close();
        int fd = open(BIN_PATH, RAW_OPEN_RDONLY);
        if (fd < 0) return -6;
        long sz = lseek(fd, 0, 2);
        if (sz < 0 || (uint32_t)sz != pkt.bytes || lseek(fd, 0, 0) != 0) {
            close(fd);
            return -7;
        }
        uint32_t rem = pkt.bytes, crc = 0;
        while (rem) {
            unsigned step = rem > sizeof(g_crc_buf) ? sizeof(g_crc_buf) : rem;
            int r = read(fd, g_crc_buf, step);
            if (r <= 0) { close(fd); return -8; }
            crc = raw_crc32_ieee(crc, g_crc_buf, (unsigned)r);
            rem -= (unsigned)r;
        }
        g_bin_fd = fd;
        memcpy(g_last_pkt, done, 24);
        g_cached_crc = crc;
        g_cached_size = pkt.bytes;
        g_have_cache = 1;
    }

    memset(hdr, 0, RAW_UVC_HDR_BYTES);
    memcpy(hdr, "ZVRAW001", 8);
    put32(hdr + 8, 1u);
    put32(hdr + 12, RAW_UVC_HDR_BYTES);
    put32(hdr + 16, frame_seq);
    put32(hdr + 20, g_cached_size);
    put32(hdr + 24, pkt.address);
    put32(hdr + 28, (uint32_t)pkt.op | ((uint32_t)pkt.tag << 16));
    put32(hdr + 32, (uint32_t)pkt.sequence | ((uint32_t)pkt.mode << 8) |
                    ((uint32_t)pkt.a << 16) | ((uint32_t)pkt.b << 24));
    put32(hdr + 36, pkt.c);
    put32(hdr + 40, pkt.d);
    put32(hdr + 44, g_cached_crc);
    put32(hdr + 48, raw_crc32_ieee(0, hdr, 48));
    *out_raw_bytes = g_cached_size;
    return 0;
}

int raw_source_read_chunk(const unsigned char hdr[RAW_UVC_HDR_BYTES], uint32_t raw_bytes,
                          unsigned frame_offset, unsigned char *dst, unsigned chunk_len) {
    if (g_bin_fd < 0 || !g_have_cache || raw_bytes != g_cached_size) return -1;
    if (frame_offset + chunk_len > RAW_UVC_FRAME_BYTES) return -2;

    unsigned pos = 0;
    if (frame_offset < RAW_UVC_HDR_BYTES) {
        unsigned take = RAW_UVC_HDR_BYTES - frame_offset;
        if (take > chunk_len) take = chunk_len;
        memcpy(dst + pos, hdr + frame_offset, take);
        pos += take;
    }

    unsigned data_end = RAW_UVC_HDR_BYTES + raw_bytes;
    unsigned cur = frame_offset + pos;
    if (pos < chunk_len && cur < data_end) {
        unsigned file_off = cur - RAW_UVC_HDR_BYTES;
        unsigned take = data_end - cur;
        if (take > chunk_len - pos) take = chunk_len - pos;
        if (lseek(g_bin_fd, (long)file_off, 0) != (long)file_off) return -3;
        unsigned got = 0;
        while (got < take) {
            int r = read(g_bin_fd, dst + pos + got, take - got);
            if (r <= 0) return -4;
            got += (unsigned)r;
        }
        pos += take;
    }

    if (pos < chunk_len) {
        memset(dst + pos, 0, chunk_len - pos);
    }
    return 0;
}
