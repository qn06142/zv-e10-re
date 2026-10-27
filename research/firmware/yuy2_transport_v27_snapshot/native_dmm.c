#include "native_dmm.h"
#define AGAIN RAW_FRAME_ERR_TIMEOUT
#define BAD RAW_FRAME_ERR_IO
static int command(native_dmm *s,unsigned cmd,unsigned next) {
 unsigned char request[24];
 native_dmm_request(request,cmd,s->candidate.type,s->candidate.handle,s->io.queue);
 /* A failed send is ambiguous: never repeat a possibly accepted command. */
 s->state=next;
 if(s->io.send(s->io.opaque,request)){s->state=ND_FAULT;return BAD;}
 return AGAIN;
}
static int poll(native_dmm *s,unsigned cmd,unsigned char *r) {
 int e=s->io.receive(s->io.opaque,r);
 if(e==1)return AGAIN;
 if(e || native_dmm_reply(r,cmd,s->candidate.handle,s->io.queue)==-1){s->state=ND_FAULT;return BAD;}
 return native_dmm_reply(r,cmd,s->candidate.handle,s->io.queue)==-2?BAD:0;
}
/* One receive and at most one send per invocation. Native replies, not elapsed
 * time, advance ownership. Allocation lifetime is pinned; pixels may tear. */
static int step(native_dmm *s) {
 unsigned char r[24];int e;
 switch(s->state){
 case ND_SHARE:
  e=poll(s,2,r);if(e==AGAIN || s->state==ND_FAULT)return e;
  if(e){s->state=ND_IDLE;return e;}
  s->shared=1;
  return command(s,s->cancel?4:5,s->cancel?ND_FREE:ND_OPEN);
 case ND_OPEN:
  e=poll(s,5,r);if(e==AGAIN || s->state==ND_FAULT)return e;
  if(e)return command(s,4,ND_FREE);
  s->opened=1;
  s->physical=native_dmm_read32(r+16);s->bytes=native_dmm_read32(r+20);
  /* Physical DRAM aperture, one contiguous extent, no MMIO or wrap. */
  if(s->cancel || native_dmm_read16(r+8)!=1 || !s->physical ||
     s->physical>=0x40000000u || !s->bytes || s->bytes>0x40000000u-s->physical)
   return command(s,6,ND_CLOSE);
  s->serial++;if(!s->serial)s->serial++;
  s->token=s->serial;s->state=ND_HELD;return 0;
 case ND_CLOSE:
  e=poll(s,6,r);if(e==AGAIN || s->state==ND_FAULT)return e;
  if(e){s->state=ND_FAULT;return BAD;}
  s->opened=0;return command(s,4,ND_FREE);
 case ND_FREE:
  e=poll(s,4,r);if(e==AGAIN || s->state==ND_FAULT)return e;
  if(e){s->state=ND_FAULT;return BAD;}
  s->shared=0;s->token=0;s->state=ND_IDLE;s->cancel=0;return 0;
 case ND_FAULT:return BAD;
 default:return 0;
 }
}
int native_dmm_acquire(void *ctx,uint32_t timeout,raw_live_frame *out) {
 native_dmm *s=ctx;
 if(!s || !out || !timeout || timeout>10)return RAW_FRAME_ERR_INVALID_PARAM;
 *out=(raw_live_frame){0};
 if(s->state==ND_IDLE){
  if(!s->io.queue || !s->io.select || !s->io.send || !s->io.receive)return BAD;
  int e=s->io.select(s->io.opaque,&s->candidate);if(e)return e;
  if(!s->candidate.handle || (s->candidate.type!=0x240b2e && s->candidate.type!=0x6193f && s->candidate.type!=0x61940))return BAD;
  s->cancel=0;return command(s,2,ND_SHARE);
 }
 if(s->state==ND_HELD)return RAW_FRAME_ERR_DEVICE_BUSY;
 int e=step(s);if(e)return e;
 if(s->state!=ND_HELD)return AGAIN;
 out->token=s->token;out->sequence=s->serial;
 out->format=RAW_FRAME_PIXFMT_UNKNOWN;out->flags=0;
 out->plane[0]=(raw_live_plane){s->physical,s->bytes,0};
 return 0;
}
int native_dmm_release(void *ctx,uintptr_t token) {
 native_dmm *s=ctx;
 if(!s || !token || s->token!=token)return RAW_FRAME_ERR_INVALID_PARAM;
 if(s->state==ND_HELD)return command(s,6,ND_CLOSE);
 if(s->state!=ND_CLOSE && s->state!=ND_FREE)return BAD;
 int e=step(s);return e?e:(s->state==ND_IDLE?0:AGAIN);
}
int native_dmm_quiesce(native_dmm *s) {
 if(!s)return BAD;
 s->cancel=1;
 if(s->state==ND_HELD)return command(s,6,ND_CLOSE);
 if(s->state==ND_IDLE){s->cancel=0;return 0;}
 return step(s);
}
