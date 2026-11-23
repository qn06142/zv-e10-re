#include "capture.h"
static raw_original original;
static raw_ops ops;
static unsigned state,selected;
/* 0 unbound,1 ready,2 armed,3 copying,4 complete,5 failed. No implicit rearm. */
int raw_bind(raw_original f,const raw_ops *o){
 if(!f||!o||!o->save||state)return -1;
 original=f;ops=*o;__atomic_store_n(&state,1,__ATOMIC_RELEASE);return 0;
}
int raw_arm(unsigned tag){
 if(tag!=1 || __atomic_load_n(&state,__ATOMIC_ACQUIRE)!=1)return -1;
 selected=tag;__atomic_store_n(&state,2,__ATOMIC_RELEASE);return 0;
}
unsigned raw_status(void){return __atomic_load_n(&state,__ATOMIC_ACQUIRE);}
int raw_dispatch(void *self,const raw_packet *wire){
 if(!wire||!original)return 0;
 raw_packet p=*wire;
 if(p.op!=1 || p.mode!=0 || (p.tag&255)!=selected || raw_status()!=2)
  return original(self,wire);
 unsigned expected=2;
 if(!__atomic_compare_exchange_n(&state,&expected,3,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return 0;
 /* Bounds on the native physical span; no format/depth inference. */
 if(!p.address || !p.bytes || p.bytes>64u*1024u*1024u ||
    p.address>=0x40000000u || p.bytes>0x40000000u-p.address){
  __atomic_store_n(&state,5,__ATOMIC_RELEASE);return 0;
 }
 int ok=ops.save(&p)==0;
 __atomic_store_n(&state,ok?4:5,__ATOMIC_RELEASE);return ok;
}
