#include "sony_yc_metadata.h"

void *memcpy(void *dest, const void *src, size_t n) {
 unsigned char *d = (unsigned char *)dest;
 const unsigned char *s = (const unsigned char *)src;
 while (n--) *d++ = *s++;
 return dest;
}

static uint32_t b16(const unsigned char *p) {return (uint32_t)p[0]|(uint32_t)p[1]<<8;}
static uint32_t b32(const unsigned char *p) {return b16(p)|b16(p+2)<<16;}

int sony_yc_metadata_decode(const void *raw, size_t length, sony_yc_metadata *out) {
 if (!raw || !out || length < SONY_YC_IMAGE_SIZE_BYTES) return -1;
 const unsigned char *p = (const unsigned char *)raw;
 sony_yc_metadata value;
 value.image_attach = p[0x00];
 value.unit_type = b32(p + 0x04);
 value.unit_handle = b16(p + 0x08);
 value.unit_data_offset = b32(p + 0x0c);
 value.exposure_time = p[0x10];
 value.expose_pic_delay = p[0x11];
 value.scenario_end = p[0x12];
 value.mirror = p[0x13];
 value.record_size_x = b16(p + 0x14);
 value.record_size_y = b16(p + 0x16);
 value.canvas_size_x = b16(p + 0x18);
 value.canvas_size_y = b16(p + 0x1a);
 value.valid_offset_x = b16(p + 0x1c);
 value.valid_offset_y = b16(p + 0x1e);
 value.valid_size_x = b16(p + 0x20);
 value.valid_size_y = b16(p + 0x22);
 value.target_offset_x = b16(p + 0x24);
 value.target_offset_y = b16(p + 0x26);
 value.target_size_x = b16(p + 0x28);
 value.target_size_y = b16(p + 0x2a);
 value.data_site = p[0x2c];
 value.iib_number = p[0x2d];
 value.aspect = p[0x2e];
 value.yc_compress = p[0x2f];
 value.data_transfer = p[0x30];
 value.data_placement = p[0x31];
 value.data_content = p[0x32];
 value.data_scan = p[0x33];
 value.strip_width = b16(p + 0x34);
 value.yc_bit_depth = p[0x36];
 value.cam_freq_char_h = b16(p + 0x38);
 *out = value;
 return 0;
}

int sony_yc_resolve_data_span(const sony_yc_metadata *m, uint32_t physical, uint32_t bytes, sony_yc_span *out) {
 if (!m || !out || !physical || !bytes || m->unit_data_offset >= bytes || (uint64_t)physical + bytes > 0x100000000ull) return -1;
 sony_yc_span value = { physical + m->unit_data_offset, bytes - m->unit_data_offset };
 *out = value;
 return 0;
}

int sony_yc_state_decode(const void *raw, size_t length, sony_yc_state_info *out) {
 if (!raw || !out || length < SONY_YC_STATE_INFO_BYTES) return -1;
 const unsigned char *p = (const unsigned char *)raw;
 sony_yc_state_info value;
 value.y_range = p[0x00];
 value.colorimetry = p[0x01];
 value.chroma_phase = p[0x02];
 value.scanline = p[0x03];
 value.copy_protection = p[0x04];
 value.author = p[0x05];
 *out = value;
 return 0;
}

int sony_yc_multiple_segment_decode(const void *raw, size_t length, sony_yc_multiple_segment_info *out) {
 if (!raw || !out || length < SONY_YC_MULTI_SEGMENT_BYTES) return -1;
 const unsigned char *p = (const unsigned char *)raw;
 sony_yc_multiple_segment_info value;
 value.image_attach = p[0x00];
 value.exposure_time = p[0x01];
 value.expose_pic_delay = p[0x02];
 value.scenario_end = p[0x03];
 value.mirror = p[0x04];
 value.record_size_x = b16(p + 0x06);
 value.record_size_y = b16(p + 0x08);
 value.aspect = p[0x0a];
 value.yc_compress = p[0x0b];
 value.data_transfer = p[0x0c];
 value.data_placement = p[0x0d];
 value.data_content = p[0x0e];
 value.data_scan = p[0x0f];
 value.strip_width = b16(p + 0x10);
 value.total_segment_num = p[0x1f];
 for (uint32_t i = 0; i < SONY_YC_MAX_SEGMENTS; i++) {
  const unsigned char *s = p + 0x20 + (i * 0x40);
  sony_yc_image_segment *seg = &value.segments[i];
  seg->unit_type = b32(s + 0x04);
  seg->unit_handle = b16(s + 0x08);
  seg->unit_data_offset = b32(s + 0x0c);
  seg->canvas_size_x = b16(s + 0x10);
  seg->canvas_size_y = b16(s + 0x12);
  seg->valid_offset_x = b16(s + 0x14);
  seg->valid_offset_y = b16(s + 0x16);
  seg->valid_size_x = b16(s + 0x18);
  seg->valid_size_y = b16(s + 0x1a);
  seg->target_offset_x = b16(s + 0x1c);
  seg->target_offset_y = b16(s + 0x1e);
  seg->target_size_x = b16(s + 0x20);
  seg->target_size_y = b16(s + 0x22);
  seg->data_site = s[0x24];
  seg->iib_number = s[0x25];
 }
 *out = value;
 return 0;
}

int sony_yc_segment_extract_image_size(const sony_yc_multiple_segment_info *multi, uint32_t slot, sony_yc_metadata *out) {
 if (!multi || !out || slot >= SONY_YC_MAX_SEGMENTS) return -1;
 const sony_yc_image_segment *seg = &multi->segments[slot];
 sony_yc_metadata value;
 value.image_attach = multi->image_attach;
 value.unit_type = seg->unit_type;
 value.unit_handle = seg->unit_handle;
 value.unit_data_offset = seg->unit_data_offset;
 value.exposure_time = multi->exposure_time;
 value.expose_pic_delay = multi->expose_pic_delay;
 value.scenario_end = multi->scenario_end;
 value.mirror = multi->mirror;
 value.record_size_x = multi->record_size_x;
 value.record_size_y = multi->record_size_y;
 value.canvas_size_x = seg->canvas_size_x;
 value.canvas_size_y = seg->canvas_size_y;
 value.valid_offset_x = seg->valid_offset_x;
 value.valid_offset_y = seg->valid_offset_y;
 value.valid_size_x = seg->valid_size_x;
 value.valid_size_y = seg->valid_size_y;
 value.target_offset_x = seg->target_offset_x;
 value.target_offset_y = seg->target_offset_y;
 value.target_size_x = seg->target_size_x;
 value.target_size_y = seg->target_size_y;
 value.data_site = seg->data_site;
 value.iib_number = seg->iib_number;
 value.aspect = multi->aspect;
 value.yc_compress = multi->yc_compress;
 value.data_transfer = multi->data_transfer;
 value.data_placement = multi->data_placement;
 value.data_content = multi->data_content;
 value.data_scan = multi->data_scan;
 value.strip_width = multi->strip_width;
 value.yc_bit_depth = 0;
 value.cam_freq_char_h = 0;
 *out = value;
 return 0;
}

int sony_yc_segment_merge_image_size(const sony_yc_multiple_segment_info *multi, sony_yc_metadata *out) {
 if (!multi || !out) return -1;
 const sony_yc_image_segment *seg0 = &multi->segments[0];
 const sony_yc_image_segment *seg1 = &multi->segments[1];
 sony_yc_metadata value;
 value.image_attach = multi->image_attach;
 value.unit_type = seg0->unit_type;
 value.unit_handle = seg0->unit_handle;
 value.unit_data_offset = seg0->unit_data_offset;
 value.exposure_time = multi->exposure_time;
 value.expose_pic_delay = multi->expose_pic_delay;
 value.scenario_end = multi->scenario_end;
 value.mirror = multi->mirror;
 value.record_size_x = multi->record_size_x;
 value.record_size_y = multi->record_size_y;
 value.canvas_size_x = seg0->canvas_size_x + seg1->canvas_size_x;
 value.canvas_size_y = seg0->canvas_size_y;
 value.valid_offset_x = seg0->valid_offset_x;
 value.valid_offset_y = seg0->valid_offset_y;
 value.valid_size_x = seg0->valid_size_x + seg1->valid_size_x;
 value.valid_size_y = seg0->valid_size_y;
 value.target_offset_x = seg0->target_offset_x;
 value.target_offset_y = seg0->target_offset_y;
 value.target_size_x = seg0->target_size_x + seg1->target_size_x;
 value.target_size_y = seg0->target_size_y;
 value.data_site = seg0->data_site;
 value.iib_number = seg0->iib_number;
 value.aspect = multi->aspect;
 value.yc_compress = multi->yc_compress;
 value.data_transfer = multi->data_transfer;
 value.data_placement = multi->data_placement;
 value.data_content = multi->data_content;
 value.data_scan = multi->data_scan;
 value.strip_width = multi->strip_width;
 value.yc_bit_depth = 0;
 value.cam_freq_char_h = 0;
 *out = value;
 return 0;
}
