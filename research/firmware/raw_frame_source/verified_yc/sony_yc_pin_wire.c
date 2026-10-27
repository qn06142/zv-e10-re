#include "sony_yc_pin_wire.h"
static uint32_t r16(const unsigned char*p){return (uint32_t)p[0]|(uint32_t)p[1]<<8;}
static uint32_t r32(const unsigned char*p){return r16(p)|r16(p+2)<<16;}
static void w16(unsigned char*p,uint32_t n){p[0]=n;p[1]=n>>8;}
static void w32(unsigned char*p,uint32_t n){w16(p,n);w16(p+2,n>>16);}
static sony_pin_property property(const unsigned char*p){sony_pin_property q={r32(p),r32(p+4),r32(p+8),r32(p+12)};return q;}
static void put_property(unsigned char*p,const sony_pin_property*q){w32(p,q->data_type);w32(p+4,q->direction);w32(p+8,q->index);w32(p+12,q->queue);}
int sony_pin_decode_send(const void *raw,size_t n,sony_pin_frame_send*out){
 if(!raw || !out || n<SONY_PIN_SEND_BYTES)return -1;
 const unsigned char*p=raw;
 if(r16(p)!=0x1000 || r16(p+2)!=0x102 || r16(p+4)!=SONY_PIN_SEND_BYTES || r16(p+6)!=1)return -1;
 sony_pin_frame_send value={property(p+8),property(p+24),r32(p+40),r32(p+48),(uint16_t)r16(p+44)};
 *out=value;return 0;
}
int sony_pin_make_complete(const sony_pin_frame_send*f,int32_t status,void*raw,size_t n){
 if(!f || !raw || n<SONY_PIN_COMPLETE_BYTES)return -1;
 /* Snapshot fields before writing so input/output aliasing cannot corrupt properties. */
 sony_pin_frame_send v=*f;unsigned char*p=raw;
 w16(p,0x1000);w16(p+2,0x8102);w16(p+4,SONY_PIN_COMPLETE_BYTES);w16(p+6,1);
 put_property(p+8,&v.output);put_property(p+24,&v.input);w32(p+40,(uint32_t)status);return 0;
}
