#include "sony_yc_sds.h"

static uint32_t r32(const unsigned char *p) {
 return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}

static int within(size_t n, uint32_t off, uint32_t count) { return off <= n && count <= n - off; }

static int sds_find_entry(const void *raw, size_t n, uint32_t target_cate, const unsigned char **out_data, uint32_t *out_bytes) {
 if (!raw || !out_data || !out_bytes || n < 32) return -1;
 const unsigned char *p = (const unsigned char *)raw;
 if (r32(p) != 0x43595353u || r32(p + 8) != 1) return -1; /* SSYC, native version 1 */
 uint32_t count = r32(p + 12), off = r32(p + 16);
 if (count > 64) return -1;
 if (!count) return -2;
 for (uint32_t i = 0; i < count; i++) {
  if (off < 32 || !within(n, off, 32)) return -1;
  const unsigned char *e = p + off;
  if (r32(e) != 0x59525445u) return -1; /* ETRY */
  uint32_t cate = r32(e + 4);
  uint32_t data = r32(e + 12), bytes = r32(e + 16), next = r32(e + 20);
  if (data < 32 || !within(n, data, bytes)) return -1;
  if (cate == target_cate) {
   *out_data = p + data;
   *out_bytes = bytes;
   return 0;
  }
  if (i + 1 < count && (!next || next == off)) return -1;
  off = next;
 }
 return -2;
}

int sony_yc_sds_decode_image(const void *raw, size_t n, sony_yc_metadata *out) {
 if (!out) return -1;
 const unsigned char *data = 0;
 uint32_t bytes = 0;
 int ret = sds_find_entry(raw, n, 0, &data, &bytes);
 if (ret != 0) return ret;
 if (bytes < SONY_YC_IMAGE_SIZE_BYTES) return -1;
 return sony_yc_metadata_decode(data, bytes, out);
}

int sony_yc_sds_decode_state(const void *raw, size_t n, sony_yc_state_info *out) {
 if (!out) return -1;
 const unsigned char *data = 0;
 uint32_t bytes = 0;
 int ret = sds_find_entry(raw, n, 1, &data, &bytes);
 if (ret != 0) return ret;
 if (bytes < SONY_YC_STATE_INFO_BYTES) return -1;
 return sony_yc_state_decode(data, bytes, out);
}

int sony_yc_sds_decode_multi_segment(const void *raw, size_t n, sony_yc_multiple_segment_info *out) {
 if (!out) return -1;
 const unsigned char *data = 0;
 uint32_t bytes = 0;
 int ret = sds_find_entry(raw, n, 0x11, &data, &bytes);
 if (ret != 0) return ret;
 if (bytes < SONY_YC_MULTI_SEGMENT_BYTES) return -1;
 return sony_yc_multiple_segment_decode(data, bytes, out);
}
