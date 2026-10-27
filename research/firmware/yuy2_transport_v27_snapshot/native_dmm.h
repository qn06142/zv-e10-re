#ifndef NATIVE_DMM_H
#define NATIVE_DMM_H
#include "raw_live_source.h"
#include "native_dmm_wire.h"
typedef struct { unsigned short handle; unsigned type; } native_dmm_candidate;
typedef struct {
 int (*select)(void *,native_dmm_candidate *);
 int (*send)(void *,const unsigned char *);
 int (*receive)(void *,unsigned char *); /* 1 means no reply, 0 success */
 void *opaque; unsigned queue;
} native_dmm_io;
enum { ND_IDLE,ND_SHARE,ND_OPEN,ND_HELD,ND_CLOSE,ND_FREE,ND_FAULT };
typedef struct {
 native_dmm_io io; native_dmm_candidate candidate;
 unsigned state,shared,opened,serial,physical,bytes,cancel;
 uintptr_t token;
} native_dmm;
int native_dmm_acquire(void *,uint32_t,raw_live_frame *);
int native_dmm_release(void *,uintptr_t);
int native_dmm_quiesce(native_dmm *);
int native_dmm_target_bind(raw_live_source *,size_t);
int native_dmm_target_quiesce(void);
int native_dmm_target_offset(size_t);
int native_dmm_select_text(char *,size_t,native_dmm_candidate *);
#endif
