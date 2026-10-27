#include "raw_snapshot.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned char source[2073600],packet[SNAP_PACKET];
static unsigned acquire_count,map_count,release_count,unmap_count;
static int release_wait,unmap_wait,oversize,map_fail;
static int acquire(void *ctx,uint32_t timeout,raw_live_frame *f){
 (void)ctx;(void)timeout;acquire_count++;
 *f=(raw_live_frame){0};f->token=1;f->sequence=17;
 f->plane[0]=(raw_live_plane){0x10000000,oversize?SNAP_MAX+1:sizeof(source),0};return 0;
}
static int release(void *ctx,uintptr_t token){(void)ctx;assert(token==1);release_count++;if(release_wait){release_wait--;return RAW_FRAME_ERR_TIMEOUT;}return 0;}
static int map(void *ctx,const raw_live_plane *p,size_t n,raw_live_mapping *m){
 (void)ctx;assert(n==sizeof(source) && p->physical==0x10000000);map_count++;
 if(map_fail)return RAW_FRAME_ERR_MMAP_FAILED;
 *m=(raw_live_mapping){source,source,sizeof(source)};return 0;
}
static int unmap(void *ctx,raw_live_mapping *m){(void)ctx;assert(m->base==source);unmap_count++;if(unmap_wait){unmap_wait--;return RAW_FRAME_ERR_IO;}return 0;}
static raw_live_source init(void){raw_live_source s={0};raw_live_ops ops={RAW_LIVE_ABI,sizeof(ops),acquire,release,map,unmap};assert(!raw_live_init(&s,&ops,0,640,480,10));return s;}
int main(int argc,char **argv){
 assert(argc==2);for(unsigned i=0;i<sizeof(source);i++)source[i]=(i*31u+(i>>9))&255;
 raw_live_source s=init();raw_snapshot b={0};
 release_wait=1;assert(raw_snapshot_step(&b,&s,0x30000000,0x320000)==RAW_FRAME_ERR_TIMEOUT);assert(!b.ready && b.copied && s.leased.token);
 /* A producer update after copy must not alter subsequent USB chunks. */
 memset(source,0xa7,sizeof(source));assert(!raw_snapshot_step(&b,&s,0x30000000,0x320000));assert(b.ready && !s.leased.token && acquire_count==1 && map_count==1);
 FILE *f=fopen(argv[1],"wb");assert(f);unsigned chunks=0;
 while(b.ready){assert(!raw_snapshot_packet(&b,packet));unsigned char *retry=malloc(SNAP_PACKET);assert(retry);memcpy(retry,packet,SNAP_PACKET);
  assert(!raw_snapshot_packet(&b,packet) && !memcmp(retry,packet,SNAP_PACKET));free(retry);
  assert(fwrite(packet,1,SNAP_PACKET,f)==SNAP_PACKET);raw_snapshot_commit(&b);chunks++;}
 fclose(f);assert(chunks==4 && acquire_count==1);
 unsigned maps_before=map_count;
 assert(raw_snapshot_step(&b,&s,0x10000010,614400)==RAW_FRAME_ERR_INVALID_PARAM);assert(map_count==maps_before && !s.leased.token);
 oversize=1;assert(raw_snapshot_step(&b,&s,0x30000000,0x320000)==RAW_FRAME_ERR_INVALID_PARAM);assert(!s.leased.token && !b.ready);oversize=0;
 map_fail=1;assert(raw_snapshot_step(&b,&s,0x30000000,0x320000)==RAW_FRAME_ERR_MMAP_FAILED);assert(!s.leased.token && !b.ready);map_fail=0;
 unmap_wait=1;assert(raw_snapshot_step(&b,&s,0x30000000,0x320000)==RAW_FRAME_ERR_IO);unsigned before=acquire_count;
 assert(!raw_snapshot_step(&b,&s,0x30000000,0x320000));assert(acquire_count==before && b.ready && !s.leased.token);
 unsigned id=b.id;raw_snapshot_reset(&b);assert(!b.ready && b.id==id);
 assert(!raw_snapshot_step(&b,&s,0x30000000,0x320000));assert(b.id==id+1);
 raw_snapshot_reset(&b);free(b.data);
 puts("snapshot ownership, full-copy, retry, range, mapping, reset: PASS");return 0;
}
