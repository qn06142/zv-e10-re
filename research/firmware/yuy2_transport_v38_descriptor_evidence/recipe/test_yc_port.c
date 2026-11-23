#include <assert.h>
#include <stdio.h>
#include "yc_port.c"
void *dlopen(const char *p,int f){(void)p;(void)f;return 0;}
void *dlsym(void *p,const char *s){(void)p;(void)s;return 0;}
static unsigned char inbound[64],sent[64];static unsigned in_size,sent_size,connects,disconnects,acks,dtors;static int receive_rc;
static void ctor(void *p){(void)p;}
static void dtor(void *p){(void)p;dtors++;}
static int recv(void *r,unsigned q,void *m,unsigned t){(void)r;(void)m;assert(q==queue);assert(t==20);return receive_rc;}
static unsigned short size(void *m){(void)m;return in_size;}
static int copy(void *m,void *p,unsigned short n){(void)m;assert(n>=in_size);memcpy(p,inbound,in_size);return 0;}
static int connect_pin(void *p,const void *r){(void)p;assert(!memcmp((const char *)r+8,peer,16));connects++;return 0;}
static int disconnect_pin(void *p,const void *r){(void)p;(void)r;disconnects++;return 0;}
static int comp(void *p,int n){(void)p;assert(!n);acks++;return 0;}
static int wire(void *p,void *r,unsigned short n,unsigned q,unsigned dest){assert(p==channel+12 && q==queue && dest==0x59000e);sent_size=n;memcpy(sent,r,n);return 0;}
static void logger(const char *s,unsigned a,unsigned b,unsigned c){(void)s;(void)a;(void)b;(void)c;}
static void reset(void){
 initialized=1;bound=connected=closing=closed=disconnect_sent=frames=0;queue=0x356122;own[0]=0;own[1]=1;own[2]=0x7fffff37;own[3]=queue;
 logit=logger;send_wire=wire;receive_rc=0;f[YP_MSG_CTOR]=ctor;f[YP_MSG_DTOR]=dtor;f[YP_RECEIVE]=recv;f[YP_MSG_SIZE]=size;f[YP_MSG_COPY]=copy;f[YP_CONNECT]=connect_pin;f[YP_DISCONNECT]=disconnect_pin;f[YP_SEND_COMP]=comp;
}
static void msg(unsigned op,unsigned n){memset(inbound,0,64);in_size=n;w16(inbound,0x1000);w16(inbound+2,op);w16(inbound+4,n);w16(inbound+6,1);memcpy(inbound+8,peer,16);if(n>=40)memcpy(inbound+24,own,16);}
int main(void){
 yc_port_frame ev={0};reset();assert(!request(1));assert(sent_size==40 && u16(sent+2)==1 && !memcmp(sent+24,own,16));
 msg(0x100,40);assert(yc_port_next(&ev,20)==1 && connected && bound && connects==1);
 for(unsigned n=1;n<=100;n++){
  msg(0x102,52);memcpy(inbound+40,(unsigned[]){0xe0b00},4);w16(inbound+44,n);
  assert(!yc_port_next(&ev,20) && ev.sds==n && ev.type==0xe0b00);assert(!yc_port_complete());
 }
 assert(acks==100 && frames==100);assert(!yc_port_close() && sent_size==24 && u16(sent+2)==2);
 msg(0x101,40);assert(yc_port_next(&ev,20)==1 && !connected && disconnects==1);
 msg(0x8002,28);assert(yc_port_next(&ev,20)==2 && closed);
 reset();msg(0x8001,28);memcpy(inbound+24,(int[]){-25},4);assert(yc_port_next(&ev,20)==-1 && closed);sent_size=0;assert(!yc_port_close() && !sent_size);
 reset();closing=1;msg(0x100,40);assert(yc_port_next(&ev,20)==1 && disconnect_sent && sent_size==24);
 for(unsigned mode=0;mode<7;mode++){
  reset();bound=1;msg(0x102,52);memcpy(inbound+40,(unsigned[]){0xe0b00},4);w16(inbound+44,1);
  if(mode==0)inbound[8]=1; /* OSD/control type must never become an image. */
  if(mode==1)inbound[24]=1;if(mode==2)inbound[44]=0;
  if(mode==3)inbound[48]=1;if(mode==4)inbound[46]=1;
  if(mode==5)inbound[4]=51;if(mode==6)bound=0;
  assert(yc_port_next(&ev,20)==-1);
 }
 reset();receive_rc=1;unsigned before=dtors;assert(yc_port_next(&ev,20)==1 && dtors==before+1);
 puts("PASS: 100 frame events, handshake/disconnect, busy rejection, late connect, 7 malformed routes, timeout cleanup");return 0;
}
