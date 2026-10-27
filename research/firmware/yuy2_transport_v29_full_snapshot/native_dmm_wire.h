#ifndef NATIVE_DMM_WIRE_H
#define NATIVE_DMM_WIRE_H
#include <stdint.h>
#include <stddef.h>
#define NATIVE_DMM_BYTES 24u
#define NATIVE_DMM_QUEUE 0x0061003cu
void native_dmm_request(unsigned char *,uint16_t,uint32_t,uint16_t,uint32_t);
int native_dmm_reply(const unsigned char *,uint16_t,uint16_t,uint32_t);
uint16_t native_dmm_read16(const unsigned char *);
uint32_t native_dmm_read32(const unsigned char *);
#endif
