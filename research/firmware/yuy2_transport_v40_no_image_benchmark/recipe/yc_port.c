/* Direct type-0 YC connection on a PRIVATE queue. No native OSD/YC1 dispatcher,
 * guessed callback, forced reconnect, or memory-pool scan is used. */
#include "yc_port.h"
#include "yc_port_guards.h"
#include <stdint.h>
extern void *dlopen(const char *,int),*dlsym(void *,const char *);
extern void *memcpy(void *,const void *,unsigned),*memset(void *,int,unsigned);
extern int memcmp(const void *,const void *,unsigned);
static void *f[YP_COUNT],*send_wire;
static unsigned char channel[256] __attribute__((aligned(8)));
static unsigned char receiver[16] __attribute__((aligned(8))),sender[16] __attribute__((aligned(8)));
static unsigned char pin[64] __attribute__((aligned(8))),message[272] __attribute__((aligned(8)));
static uint32_t own[4],peer[4]={0,2,0,0x59000e};
static unsigned queue,initialized,bound,connected,closing,closed,disconnect_sent,frames;
static yc_port_log logit;
static unsigned short u16(const unsigned char *p){return (unsigned short)(p[0]|p[1]<<8);}
static unsigned u32(const unsigned char *p){return (unsigned)p[0]|(unsigned)p[1]<<8|(unsigned)p[2]<<16|(unsigned)p[3]<<24;}
static void w16(unsigned char *p,unsigned x){p[0]=x;p[1]=x>>8;}
static int request(unsigned opcode){
 unsigned char raw[40]={0};unsigned n=opcode==1?40:24;
 w16(raw,0x1000);w16(raw+2,opcode);w16(raw+4,n);w16(raw+6,1);
 memcpy(raw+8,peer,16);if(opcode==1)memcpy(raw+24,own,16);
 int rc=((int (*)(void *,void *,unsigned short,unsigned,unsigned))send_wire)(channel+12,raw,(unsigned short)n,queue,peer[3]);
 logit(opcode==1?"YC_CONNECT_REQUEST":"YC_DISCONNECT_REQUEST",queue,(unsigned)rc,own[2]);return rc;
}
int yc_port_init(void *ctor,void *wire_send,yc_port_log logger){
 if(initialized)return -1;
 initialized=1;logit=logger;send_wire=wire_send;
 void *h=dlopen("dataflowInfraFramework.so",6);if(!h)return -1;
 for(unsigned i=0;i<YP_COUNT;i++){
  f[i]=dlsym(h,yp_names[i]);
  if(!f[i] || memcmp((void *)((uintptr_t)f[i]&~(uintptr_t)1),yp_guards[i],16)){logit("YC_API_GUARD_FAILED",i,0,0);return -1;}
 }
 ((void (*)(void *,unsigned short))ctor)(channel,0x35);memcpy(&queue,channel+4,4);
 if(!queue)return -1;
 own[0]=0;own[1]=1;own[2]=0x7fffff37;own[3]=queue;
 ((void (*)(void *))f[YP_SENDER_CTOR])(sender);
 ((void (*)(void *,void *,void *))f[YP_PIN_CTOR])(pin,own,sender);
 ((void (*)(void *))f[YP_RECEIVER_CTOR])(receiver);
 return request(1)?-1:0;
}
int yc_port_next(yc_port_frame *out,unsigned timeout){
 if(!initialized)return -1;if(closed)return 2;
 unsigned char raw[64]={0};unsigned n;int rc;
 ((void (*)(void *))f[YP_MSG_CTOR])(message);
 rc=((int (*)(void *,unsigned,void *,unsigned))f[YP_RECEIVE])(receiver,queue,message,timeout);
 if(rc){((void (*)(void *))f[YP_MSG_DTOR])(message);return 1;}
 n=((unsigned short (*)(void *))f[YP_MSG_SIZE])(message);
 if(n<8 || n>sizeof(raw))rc=-1;
 else rc=((int (*)(void *,void *,unsigned short))f[YP_MSG_COPY])(message,raw,sizeof(raw));
 ((void (*)(void *))f[YP_MSG_DTOR])(message);
 if(rc || u16(raw)!=0x1000 || u16(raw+4)!=n){logit("YC_MESSAGE_REJECTED",n,(unsigned)rc,0);return -1;}
 unsigned op=u16(raw+2);
 if(op==0x100 || op==0x101){
  if(n!=40 || memcmp(raw+8,peer,16) || memcmp(raw+24,own,16))return -1;
  if(op==0x100){
   rc=((int (*)(void *,const void *))f[YP_CONNECT])(pin,raw);
   if(rc)return -1;bound=connected=1;logit("YC_CONNECTED",queue,own[2],0);
   if(closing && !disconnect_sent){if(request(2))return -1;disconnect_sent=1;}
  }else{
   rc=((int (*)(void *,const void *))f[YP_DISCONNECT])(pin,raw);
   if(rc)return -1;connected=0;logit("YC_DISCONNECTED",queue,0,0);
  }
  return 1;
 }
 if(op==0x8001 || op==0x8002){
  if(n!=28 || memcmp(raw+8,peer,16))return -1;
  int status=(int)u32(raw+24);logit(op==0x8001?"YC_CONNECT_STATUS":"YC_DISCONNECT_STATUS",(unsigned)status,queue,0);
  if(op==0x8001 && status){closed=1;return -1;}
  if(op==0x8002){if(status && status!=-26)return -1;closed=1;connected=0;return 2;}
  return 1;
 }
 if(op==0x102){
  if(!bound || n!=52 || memcmp(raw+8,peer,16) || memcmp(raw+24,own,16) ||
     u32(raw+40)!=0xe0b00 || !u16(raw+44) || u16(raw+46) || u32(raw+48))return -1;
  *out=(yc_port_frame){u32(raw+40),u32(raw+48),u16(raw+44),0};
  frames++;logit("YC_FRAME_EVENT",frames,out->sds,queue);return 0;
 }
 logit("YC_UNEXPECTED_OPCODE",op,n,0);return -1;
}
int yc_port_complete(void){
 int rc=((int (*)(void *,int))f[YP_SEND_COMP])(pin,0);
 if(rc)logit("YC_COMPLETE_UNCERTAIN",(unsigned)rc,queue,0);return rc;
}
int yc_port_close(void){
 closing=1;if(closed)return 0;
 if(connected && !disconnect_sent){if(request(2))return -1;disconnect_sent=1;}
 return 0;
}
int yc_port_is_closed(void){return closed;}
