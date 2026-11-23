#ifndef VGA_RESIZE_H
#define VGA_RESIZE_H
#include <stdint.h>
#define VGA_BYTES 614400u
/* One native capture per cold boot, then immutable replay to the same caller
 * buffer. A zero result is not a new frame. No second thread/capture restart.
 * Native VGA packing remains unverified; this is a frozen-image diagnostic. */
int vga_resize_copy(void *, unsigned, uint32_t *, uint32_t, uint32_t, uint32_t);
void vga_resize_stop(void);
int vga_resize_reusable(void);
#endif
