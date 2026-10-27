/* Native SSYC/ETRY metadata reader; no mapping, ownership or format inference. */
#ifndef SONY_YC_SDS_H
#define SONY_YC_SDS_H
#include "sony_yc_metadata.h"

/* Reads image-size entry category 0 from a complete mapped SDS byte extent.
 * Supports the version 1 container emitted by the real Sony YC constructor.
 * At most 64 entries, matching RTOS lookup's cap; all offsets are SDS-relative.
 * Output is unchanged on failure. Returns 0, -1 malformed/unsupported, -2 absent.
 * Caller must keep metadata mapping stable for the entire call. */
int sony_yc_sds_decode_image(const void *raw, size_t n, sony_yc_metadata *out);

/* Reads Category 1 (YcStateInfo, 6 wire bytes) from mapped SDS extent. */
int sony_yc_sds_decode_state(const void *raw, size_t n, sony_yc_state_info *out);

/* Reads Category 0x11 (MultipleSegmentImageInfo, 288 wire bytes) from mapped SDS extent. */
int sony_yc_sds_decode_multi_segment(const void *raw, size_t n, sony_yc_multiple_segment_info *out);

#endif
