#include "native_dmm_wire.h"
uint16_t native_dmm_read16(const unsigned char *p){return (uint16_t)((uint16_t)p[0]|(uint16_t)p[1]<<8);}
uint32_t native_dmm_read32(const unsigned char *p){return (uint32_t)native_dmm_read16(p)|(uint32_t)native_dmm_read16(p+2)<<16;}
static void w16(unsigned char*p,uint32_t x){p[0]=(unsigned char)x;p[1]=(unsigned char)(x>>8);}
static void w32(unsigned char*p,uint32_t x){w16(p,x);w16(p+2,x>>16);}
void native_dmm_request(unsigned char*p,uint16_t cmd,uint32_t type,uint16_t handle,uint32_t reply_queue){
 for(unsigned i=0;i<NATIVE_DMM_BYTES;i++)p[i]=0;
 w16(p,cmd);w16(p+2,handle);
 if(cmd==2)w32(p+4,type);
 /* Open +0xc=0: kernel non-waiting request; mode0 at+0x16 for all operations. */
 w32(p+0x10,reply_queue);w16(p+0x14,reply_queue);
}
int native_dmm_reply(const unsigned char*p,uint16_t cmd,uint16_t handle,uint32_t queue){
 if(native_dmm_read16(p)!=(uint16_t)(cmd|0x8000u) || native_dmm_read16(p+4)!=handle || native_dmm_read16(p+6)!=(uint16_t)queue)return -1;
 return (int16_t)native_dmm_read16(p+2)<0?-2:0;
}
