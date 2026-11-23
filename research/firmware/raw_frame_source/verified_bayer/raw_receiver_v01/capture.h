#ifndef RAW_CAPTURE_H
#define RAW_CAPTURE_H
#include <stdint.h>
typedef struct { uint16_t op,tag;uint32_t address,bytes;uint8_t sequence,mode,a,b;uint32_t c,d;} raw_packet;
_Static_assert(sizeof(raw_packet)==24,"native wire size");
typedef int (*raw_original)(void*,const raw_packet*);
typedef struct {int (*save)(const raw_packet*);} raw_ops;
int raw_bind(raw_original,const raw_ops*);
int raw_arm(unsigned);
int raw_dispatch(void*,const raw_packet*);
unsigned raw_status(void);
#endif
