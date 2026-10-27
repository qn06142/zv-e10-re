#ifndef VGA_CONTRACT_H
#define VGA_CONTRACT_H
#include "sony_yc_sds.h"
#include <stdint.h>
/* No compression/geometry inferred from USB descriptors or allocation size. */
int vga_source_contract(const sony_yc_metadata *, uint32_t, uint32_t);
int vga_destination_contract(const sony_yc_metadata *, uint32_t, uint32_t);
#endif
