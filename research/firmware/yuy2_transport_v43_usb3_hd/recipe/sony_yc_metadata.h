/* Verified metadata field offsets only; enum meanings and frame ownership unresolved. */
#ifndef SONY_YC_METADATA_H
#define SONY_YC_METADATA_H
#include <stdint.h>
#include <stddef.h>

#define SONY_YC_IMAGE_SIZE_BYTES 60u
#define SONY_YC_STATE_INFO_BYTES 6u
#define SONY_YC_MULTI_SEGMENT_BYTES 288u
#define SONY_YC_MAX_SEGMENTS 4u

/* Category 0: C_DataflowInfra_Entry_ImageSizeInfo (60 wire bytes, 31 verified fields) */
typedef struct {
 uint32_t image_attach;     /* wire +0x00, 1 byte(s) */
 uint32_t unit_type;        /* wire +0x04, 4 byte(s) */
 uint32_t unit_handle;      /* wire +0x08, 2 byte(s) */
 uint32_t unit_data_offset; /* wire +0x0c, 4 byte(s) */
 uint32_t exposure_time;    /* wire +0x10, 1 byte(s) */
 uint32_t expose_pic_delay; /* wire +0x11, 1 byte(s) */
 uint32_t scenario_end;     /* wire +0x12, 1 byte(s) */
 uint32_t mirror;           /* wire +0x13, 1 byte(s) */
 uint32_t record_size_x;    /* wire +0x14, 2 byte(s) */
 uint32_t record_size_y;    /* wire +0x16, 2 byte(s) */
 uint32_t canvas_size_x;    /* wire +0x18, 2 byte(s) */
 uint32_t canvas_size_y;    /* wire +0x1a, 2 byte(s) */
 uint32_t valid_offset_x;   /* wire +0x1c, 2 byte(s) */
 uint32_t valid_offset_y;   /* wire +0x1e, 2 byte(s) */
 uint32_t valid_size_x;     /* wire +0x20, 2 byte(s) */
 uint32_t valid_size_y;     /* wire +0x22, 2 byte(s) */
 uint32_t target_offset_x;  /* wire +0x24, 2 byte(s) */
 uint32_t target_offset_y;  /* wire +0x26, 2 byte(s) */
 uint32_t target_size_x;    /* wire +0x28, 2 byte(s) */
 uint32_t target_size_y;    /* wire +0x2a, 2 byte(s) */
 uint32_t data_site;        /* wire +0x2c, 1 byte(s) */
 uint32_t iib_number;       /* wire +0x2d, 1 byte(s) */
 uint32_t aspect;           /* wire +0x2e, 1 byte(s) */
 uint32_t yc_compress;      /* wire +0x2f, 1 byte(s) */
 uint32_t data_transfer;    /* wire +0x30, 1 byte(s) */
 uint32_t data_placement;   /* wire +0x31, 1 byte(s) */
 uint32_t data_content;     /* wire +0x32, 1 byte(s) */
 uint32_t data_scan;        /* wire +0x33, 1 byte(s) */
 uint32_t strip_width;      /* wire +0x34, 2 byte(s) */
 uint32_t yc_bit_depth;     /* wire +0x36, 1 byte(s) */
 uint32_t cam_freq_char_h;  /* wire +0x38, 2 byte(s) */
} sony_yc_metadata;

typedef struct { uint32_t physical, bytes; } sony_yc_span;

/* Category 1: C_DataflowInfra_Entry_YcStateInfo (6 wire bytes) */
typedef struct {
 uint32_t y_range;         /* wire +0x00, 1 byte(s) */
 uint32_t colorimetry;     /* wire +0x01, 1 byte(s) */
 uint32_t chroma_phase;    /* wire +0x02, 1 byte(s) */
 uint32_t scanline;        /* wire +0x03, 1 byte(s) */
 uint32_t copy_protection; /* wire +0x04, 1 byte(s) */
 uint32_t author;          /* wire +0x05, 1 byte(s) */
} sony_yc_state_info;

/* Category 0x11: Segment slice descriptor (64 bytes within MultiSegment wire) */
typedef struct {
 uint32_t unit_type;        /* segment +0x04, 4 byte(s) */
 uint32_t unit_handle;      /* segment +0x08, 2 byte(s) */
 uint32_t unit_data_offset; /* segment +0x0c, 4 byte(s) */
 uint32_t canvas_size_x;    /* segment +0x10, 2 byte(s) */
 uint32_t canvas_size_y;    /* segment +0x12, 2 byte(s) */
 uint32_t valid_offset_x;   /* segment +0x14, 2 byte(s) */
 uint32_t valid_offset_y;   /* segment +0x16, 2 byte(s) */
 uint32_t valid_size_x;     /* segment +0x18, 2 byte(s) */
 uint32_t valid_size_y;     /* segment +0x1a, 2 byte(s) */
 uint32_t target_offset_x;  /* segment +0x1c, 2 byte(s) */
 uint32_t target_offset_y;  /* segment +0x1e, 2 byte(s) */
 uint32_t target_size_x;    /* segment +0x20, 2 byte(s) */
 uint32_t target_size_y;    /* segment +0x22, 2 byte(s) */
 uint32_t data_site;        /* segment +0x24, 1 byte(s) */
 uint32_t iib_number;       /* segment +0x25, 1 byte(s) */
} sony_yc_image_segment;

/* Category 0x11: C_DataflowInfra_Entry_MultipleSegmentImageInfo (288 wire bytes) */
typedef struct {
 uint32_t image_attach;     /* wire +0x00, 1 byte(s) */
 uint32_t exposure_time;    /* wire +0x01, 1 byte(s) */
 uint32_t expose_pic_delay; /* wire +0x02, 1 byte(s) */
 uint32_t scenario_end;     /* wire +0x03, 1 byte(s) */
 uint32_t mirror;           /* wire +0x04, 1 byte(s) */
 uint32_t record_size_x;    /* wire +0x06, 2 byte(s) */
 uint32_t record_size_y;    /* wire +0x08, 2 byte(s) */
 uint32_t aspect;           /* wire +0x0a, 1 byte(s) */
 uint32_t yc_compress;      /* wire +0x0b, 1 byte(s) */
 uint32_t data_transfer;    /* wire +0x0c, 1 byte(s) */
 uint32_t data_placement;   /* wire +0x0d, 1 byte(s) */
 uint32_t data_content;     /* wire +0x0e, 1 byte(s) */
 uint32_t data_scan;        /* wire +0x0f, 1 byte(s) */
 uint32_t strip_width;      /* wire +0x10, 2 byte(s) */
 uint32_t total_segment_num;/* wire +0x1f, 1 byte(s) */
 sony_yc_image_segment segments[SONY_YC_MAX_SEGMENTS];
} sony_yc_multiple_segment_info;

/* Outputs unchanged on failure. No pixel-format classification or lease acquisition. */
int sony_yc_metadata_decode(const void *raw, size_t length, sony_yc_metadata *out);
/* Apply unitDataOffset to one already-owned DMM address/capacity pair. */
int sony_yc_resolve_data_span(const sony_yc_metadata *m, uint32_t physical, uint32_t bytes, sony_yc_span *out);

/* Decode Category 1 YcStateInfo */
int sony_yc_state_decode(const void *raw, size_t length, sony_yc_state_info *out);

/* Decode Category 0x11 MultipleSegmentImageInfo */
int sony_yc_multiple_segment_decode(const void *raw, size_t length, sony_yc_multiple_segment_info *out);

/* Extracts segment `slot` into an ImageSizeInfo structure (matches Sony RTOS 0x63cebf24). */
int sony_yc_segment_extract_image_size(const sony_yc_multiple_segment_info *multi, uint32_t slot, sony_yc_metadata *out);

/* Recombines dual segments back into full-width ImageSizeInfo (matches Sony RTOS 0x63cec0d8). */
int sony_yc_segment_merge_image_size(const sony_yc_multiple_segment_info *multi, sony_yc_metadata *out);

#endif
