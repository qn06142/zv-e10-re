#include "raw_snapshot.h"
#include <stdlib.h>
#include <string.h>
static __attribute__((noinline)) uint32_t crc(const unsigned char *p,size_t n){
 uint32_t c=~0u;
 while(n--){c^=*p++;for(unsigned k=0;k<8;k++)c=(c>>1)^(0xedb88320u & (0u-(c&1u)));}
 return ~c;
}
static void put(unsigned char *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(unsigned char)(v>>(i*8));}
int raw_snapshot_step(raw_snapshot *b,raw_live_source *s,uint32_t dst,size_t dstbytes){
 if(!b || !s || !s->initialized)return RAW_FRAME_ERR_NOT_INIT;
 if(b->ready)return 0;
 int e=raw_live_drain(s);if(e)return e;
 if(b->copied){b->copied=0;b->ready=1;b->offset=0;if(!++b->id)++b->id;return 0;}
 e=s->ops.acquire(s->opaque,s->timeout_ms,&s->leased);
 if(e){int c=raw_live_drain(s);return c?c:e;}
 raw_live_plane *p=&s->leased.plane[0];
 if(!s->leased.token || !p->physical || !p->bytes || p->bytes>SNAP_MAX ||
    p->physical>=0x40000000u || p->bytes>0x40000000u-p->physical)e=RAW_FRAME_ERR_INVALID_PARAM;
 if(!e && (!dst || !dstbytes || dstbytes>UINT32_MAX-dst ||
    (p->physical<dst+dstbytes && dst<p->physical+p->bytes)))e=RAW_FRAME_ERR_INVALID_PARAM;
 if(!e && !b->data){b->data=malloc(SNAP_MAX);if(!b->data)e=RAW_FRAME_ERR_NO_MEMORY;}
 if(!e){
  e=s->ops.map_readonly(s->opaque,p,p->bytes,&s->mapped[0]);
  if(!e && (!s->mapped[0].base || !s->mapped[0].data || s->mapped[0].length<p->bytes))e=RAW_FRAME_ERR_MMAP_FAILED;
 }
 if(!e){
  memcpy(b->data,s->mapped[0].data,p->bytes);
  b->bytes=(uint32_t)p->bytes;b->physical=p->physical;b->sequence=s->leased.sequence;b->copied=1;
 }
 int c=raw_live_drain(s);if(c)return c;
 if(e)return e;
 b->copied=0;b->ready=1;b->offset=0;if(!++b->id)++b->id;return 0;
}
int raw_snapshot_packet(raw_snapshot *b,void *dst){
 if(!b || !b->ready || !dst || b->offset>=b->bytes)return RAW_FRAME_ERR_INVALID_PARAM;
 unsigned char *p=dst;uint32_t n=b->bytes-b->offset;if(n>SNAP_PAYLOAD)n=SNAP_PAYLOAD;
 memset(p,0,SNAP_PACKET);memcpy(p,"ZVYC0029",8);
 put(p+8,1);put(p+12,SNAP_HEADER);put(p+16,b->id);put(p+20,b->sequence);
 put(p+24,b->bytes);put(p+28,b->offset);put(p+32,n);
 memcpy(p+SNAP_HEADER,b->data+b->offset,n);put(p+36,crc(p+SNAP_HEADER,n));
 put(p+40,b->physical);put(p+44,1); /* allocation snapshot; completed frame NOT guaranteed */
 put(p+48,crc(p,48));
 return 0;
}
void raw_snapshot_commit(raw_snapshot *b){
 if(!b || !b->ready)return;
 uint32_t n=b->bytes-b->offset;if(n>SNAP_PAYLOAD)n=SNAP_PAYLOAD;
 b->offset+=n;if(b->offset==b->bytes){b->ready=0;b->offset=0;}
}
void raw_snapshot_reset(raw_snapshot *b){
 /* Called after worker exclusion; native cleanup is separately mandatory.
  * Retain bounded heap storage and monotonic ID across camera mode cycles. */
 if(b){b->ready=b->copied=0;b->offset=b->bytes=0;}
}
