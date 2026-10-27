#include "native_dmm.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
static unsigned commands[64],ns,available,bad,status,count=1,phys=0x18000000,span=2073600,fail_send;
static int select_unit(void *v,native_dmm_candidate *c){(void)v;c->handle=0x408a;c->type=0x6193f;return 0;}
static int send_cmd(void *v,const unsigned char *p){(void)v;commands[ns++]=native_dmm_read16(p);return fail_send;}
static int recv_cmd(void *v,unsigned char *r){(void)v;if(!available)return 1;available=0;memset(r,0,24);
 unsigned short h[6]={(unsigned short)(commands[ns-1]|0x8000),(unsigned short)status,0x408a,0x5678,(unsigned short)count,0};
 memcpy(r,h,12);memcpy(r+16,&phys,4);memcpy(r+20,&span,4);if(bad)r[6]^=1;return 0;}
static native_dmm fresh(void){native_dmm s={0};s.io=(native_dmm_io){select_unit,send_cmd,recv_cmd,0,0x12345678};ns=0;available=bad=status=fail_send=0;count=1;phys=0x18000000;return s;}
static int acquire(native_dmm *s){raw_live_frame f;return native_dmm_acquire(s,10,&f);}
static int ack_acquire(native_dmm *s){available=1;return acquire(s);}
static void held(native_dmm *s){assert(acquire(s)==-4);assert(ack_acquire(s)==-4);assert(ack_acquire(s)==0);assert(s->state==ND_HELD && s->shared && s->opened);}
static unsigned char src[614400],dst[614400];static int acqs,rels,release_pending;
static int snap_acq(void *x,uint32_t timeout,raw_live_frame *f){(void)x;(void)timeout;acqs++;*f=(raw_live_frame){0};f->token=7;f->sequence=123;f->plane[0]=(raw_live_plane){0x18000000,sizeof(src),0};return 0;}
static int snap_rel(void*x,uintptr_t token){(void)x;assert(token==7);rels++;return release_pending?-4:0;}
static int snap_map(void*x,const raw_live_plane*p,size_t n,raw_live_mapping*m){(void)x;(void)p;assert(n==sizeof(src));*m=(raw_live_mapping){src,src,n};return 0;}
static int snap_unmap(void*x,raw_live_mapping*m){(void)x;(void)m;return 0;}
int main(void){native_dmm s;raw_live_frame f;unsigned tests=0;
 s=fresh();held(&s);assert(ns==2 && commands[0]==2 && commands[1]==5);assert(native_dmm_release(&s,s.token)==-4 && commands[2]==6);available=1;assert(native_dmm_release(&s,s.token)==-4 && commands[3]==4);available=1;assert(native_dmm_release(&s,s.token)==0 && !s.shared && !s.opened);tests++;
 s=fresh();assert(acquire(&s)==-4);for(int i=0;i<100;i++)assert(acquire(&s)==-4);assert(ns==1);tests++;
 s=fresh();acquire(&s);available=1;bad=1;assert(acquire(&s)==-7 && s.state==ND_FAULT);assert(ns==1);tests++;
 s=fresh();acquire(&s);status=0xffff;assert(ack_acquire(&s)==-7 && !s.shared && s.state==ND_IDLE);assert(ns==1);tests++;
 s=fresh();acquire(&s);ack_acquire(&s);status=0xffff;assert(ack_acquire(&s)==-4 && commands[2]==4 && !s.opened);status=0;available=1;assert(acquire(&s)==-4 && s.state==ND_IDLE);tests++;
 s=fresh();acquire(&s);ack_acquire(&s);count=2;assert(ack_acquire(&s)==-4 && commands[2]==6);tests++;
 s=fresh();acquire(&s);ack_acquire(&s);phys=0xfe000000;assert(ack_acquire(&s)==-4 && commands[2]==6);tests++;
 s=fresh();fail_send=1;assert(acquire(&s)==-7 && s.state==ND_FAULT);fail_send=0;assert(acquire(&s)==-7 && ns==1);tests++;
 s=fresh();acquire(&s);assert(native_dmm_quiesce(&s)==-4);available=1;assert(native_dmm_quiesce(&s)==-4 && commands[1]==4);assert(ns==2);tests++;
 s=fresh();held(&s);assert(native_dmm_release(&s,999)==-1 && ns==2);assert(native_dmm_acquire(&s,10,&f)==-6 && !f.token);tests++;
 s=fresh();held(&s);native_dmm_release(&s,s.token);available=1;status=0xffff;assert(native_dmm_release(&s,s.token)==-7 && s.opened && s.shared && ns==3);tests++;
 raw_live_source live={0};raw_live_ops ops={1,sizeof(ops),snap_acq,snap_rel,snap_map,snap_unmap};uint32_t seq=0;
 memset(src,0x5a,sizeof(src));assert(!raw_live_init(&live,&ops,0,640,480,10));release_pending=1;
 assert(raw_live_fill_opaque(&live,dst,sizeof(dst),0x28000000,0,&seq)==-4 && live.opaque_pending && acqs==1);
 memset(src,0xa5,sizeof(src));assert(raw_live_fill_opaque(&live,dst,sizeof(dst),0x28000000,0,&seq)==-4 && acqs==1);
 release_pending=0;assert(!raw_live_fill_opaque(&live,dst,sizeof(dst),0x28000000,0,&seq));assert(seq==123 && acqs==1 && dst[0]==0x5a && dst[614399]==0x5a);tests++;
 printf("{\"passed\":%u,\"hardware_services_mocked\":true}\n",tests);return 0;}
