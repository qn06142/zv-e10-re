#include "raw_live_sony.h"
#include <string.h>
#include <stdio.h>
#define CHECK(v) do{if(!(v)){printf("FAIL %d\n",__LINE__);return 1;}}while(0)
static unsigned calls;
static int fake_ipc(void *ctx,uint32_t q,uint32_t op,uint32_t sub,uint16_t h,void *p,size_t n,uint32_t ms){
 (void)ctx;(void)q;(void)op;(void)sub;(void)h;(void)p;(void)n;(void)ms;calls++;return 0;
}
static int fake_bind(const raw_live_ops *ops,void *ctx){(void)ops;(void)ctx;calls++;return 0;}
int main(void){
 raw_live_sony_context_t c;raw_live_frame f;
 CHECK(!raw_live_sony_init(&c));CHECK(!c.is_subscribed && !c.staging_physical && !c.active_lease_token);
 memset(&f,0xaa,sizeof(f));CHECK(raw_live_sony_acquire(&c,10,&f)==RAW_FRAME_ERR_NOT_INIT);
 CHECK(!f.token && !f.plane[0].physical && !f.plane[1].physical);
 c.is_subscribed=1;c.ipc_msg=fake_ipc;c.simulated_frame_ready=1;
 CHECK(raw_live_sony_ops.acquire(&c,10,&f)==RAW_FRAME_ERR_NOT_INIT && calls==0);
 c.active_lease_token=7;c.active_unit_handle=7;
 CHECK(raw_live_sony_release(&c,7)==RAW_FRAME_ERR_NOT_INIT && c.active_lease_token==7);
 raw_live_sony_set_transport_bind_fn(fake_bind,0);
 CHECK(raw_live_sony_bind(&c)==RAW_FRAME_ERR_NOT_INIT && calls==0);
 CHECK(raw_live_sony_map_readonly(&c,&f.plane[0],1,0)==RAW_FRAME_ERR_NOT_INIT);
 CHECK(raw_live_sony_unbind()==RAW_FRAME_ERR_NOT_INIT);
 puts("Sony target/default backend fails closed: 7 checks passed");return 0;
}
