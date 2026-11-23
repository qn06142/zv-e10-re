#ifndef VGA_RESIZE_H
#define VGA_RESIZE_H
#include <stdint.h>
#define VGA_BYTES 4147200u
/* Lazy worker, never called by a library constructor. Returns 0 only after a
 * complete hardware-resized buffer has been copied into caller-owned storage.
 * Output is native VGA bytes, NOT an assertion of packed YUY2 ordering. */
int vga_resize_copy(void *, unsigned, uint32_t *, uint32_t, uint32_t, uint32_t, uint32_t);
void vga_resize_stop(void);
int vga_resize_reusable(void);
int vga_resize_copy_chunk(void *,unsigned,uint32_t *,uint32_t,uint32_t,uint32_t,uint32_t,unsigned,unsigned);
int vga_resize_frame_done(uint32_t);
#endif
