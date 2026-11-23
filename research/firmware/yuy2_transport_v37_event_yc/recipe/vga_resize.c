/* Experimental Sony SDF VGA backend. Every Sony call runs on a private worker:
 * SDK synchronous receives can block indefinitely. Stop never kills that worker
 * or frees its resources; a stuck SDK request requires reboot, not reuse. */
#include "vga_resize.h"
#include "vga_contract.h"
#include "vga_guards.h"
#include "yc_port.h"
#include "yc_unpack.h"
#include <stddef.h>
#include <stdint.h>
extern void *dlopen(const char *,int),*dlsym(void *,const char *);
extern void *malloc(unsigned),*memcpy(void *,const void *,unsigned),*memset(void *,int,unsigned);
extern int memcmp(const void *,const void *,unsigned),open(const char *,int,...),close(int);
extern int read(int,void *,unsigned),write(int,const void *,unsigned),snprintf(char *,unsigned,const char *,...);
extern int sscanf(const char *,const char *,...),usleep(unsigned),munmap(void *,unsigned);
extern void *mmap(void *,unsigned,int,int,int,long);
extern int pthread_create(unsigned long *,const void *,void *(*)(void *),void *),pthread_detach(unsigned long);
static void *sdk[VG_SDK_COUNT],*obj[VG_OBJ_COUNT];
static unsigned shared_running,shared_stopping,lock,shared_available,shared_generation;
#define running __atomic_load_n(&shared_running,__ATOMIC_ACQUIRE)
#define stopping __atomic_load_n(&shared_stopping,__ATOMIC_ACQUIRE)
#define available __atomic_load_n(&shared_available,__ATOMIC_ACQUIRE)
#define generation __atomic_load_n(&shared_generation,__ATOMIC_ACQUIRE)
#define fault __atomic_load_n(&shared_fault,__ATOMIC_ACQUIRE)
static unsigned char published[VGA_BYTES],first_native[VGA_BYTES],listing[131072];
static unsigned char dmm[256] __attribute__((aligned(8)));
static unsigned char allocator[256] __attribute__((aligned(8)));
static unsigned char sdf[256] __attribute__((aligned(8)));
static unsigned char accessor[512] __attribute__((aligned(8)));
typedef struct {uint16_t handle,pad;uint32_t type,physical,bytes;} memory_set;
typedef struct {void *base;unsigned length;unsigned char *bytes;} mapping;
typedef struct {memory_set ref;unsigned shared,opened;mapping map;unsigned granted;} lease;
static memory_set destination_sds,destination_image;
static memory_set input_sds;
static mapping input_mapping;
static unsigned initialized,destination_ready,shared_fault;
/* Bounded multi-producer telemetry. No filesystem I/O in trace(): metadata
 * and pixel acquisition must not be separated by synchronous flash writes.
 * The private worker is the only flusher. UI stop never waits on this lock. */
static unsigned usb_physical,usb_capacity,staging_physical,staging_capacity,usb_handle,usb_reserved;
static unsigned char source_snapshot[65536],first_input[65536],first_dest[65536];
static unsigned first_input_bytes,first_dest_bytes;
static unsigned trace_bytes,trace_guard,trace_flushed,trace_dropped;
static char trace_buffer[65536],trace_scratch[4096];
static void trace(const char *tag,unsigned a,unsigned b,unsigned c){
 char row[160];int n=snprintf(row,sizeof(row),"VGA %s %08x %08x %08x\n",tag,a,b,c);
 if(n<=0 || (unsigned)n>=sizeof(row))return;
 if(__sync_lock_test_and_set(&trace_guard,1)){__atomic_add_fetch(&trace_dropped,1,__ATOMIC_RELAXED);return;}
 if((unsigned)n<=sizeof(trace_buffer)-trace_bytes){memcpy(trace_buffer+trace_bytes,row,(unsigned)n);trace_bytes+=(unsigned)n;}
 else __atomic_add_fetch(&trace_dropped,1,__ATOMIC_RELAXED);
 __sync_lock_release(&trace_guard);
}
static void trace_flush(void){
 /* At most the snapshot present on entry is written; concurrent UI records
  * wait for the next private-worker boundary. Failed/partial writes retain
  * the unwritten suffix. No lock is held across filesystem operations. */
 unsigned end;
 if(__sync_lock_test_and_set(&trace_guard,1))return;
 end=trace_bytes;__sync_lock_release(&trace_guard);
 if(trace_flushed>=end)return;
 int fd=open("/log/yuy2_640_v37vga/vga.log",0x441,0644);if(fd<0)return;
 while(trace_flushed<end){
  unsigned n=end-trace_flushed;if(n>sizeof(trace_scratch))n=sizeof(trace_scratch);
  memcpy(trace_scratch,trace_buffer+trace_flushed,n);
  int wrote=write(fd,trace_scratch,n);
  if(wrote<=0 || (unsigned)wrote>n)break;
  trace_flushed+=(unsigned)wrote;
 }
 close(fd);
}
static void barrier(void){__sync_synchronize();}
static void evidence(const char *path,const void *p,unsigned n){
 if(!n || n>VGA_BYTES)return;
 int fd=open(path,0x241,0644);if(fd<0)return;
 unsigned done=0;while(done<n){int r=write(fd,(const unsigned char *)p+done,n-done);if(r<=0)break;done+=(unsigned)r;}
 close(fd);
}
static int dram(unsigned phys,unsigned bytes){
 return phys && bytes && bytes<=32u*1024u*1024u && phys<0x40000000u && bytes<=0x40000000u-phys;
}
static int collision(unsigned p,unsigned n,unsigned q,unsigned m){
 return q && m && p<q+m && q<p+n;
}
static int map_memory(uint32_t phys,uint32_t bytes,mapping *out,int writable){
 if(!dram(phys,bytes))return -1;
 if(collision(phys,bytes,usb_physical,usb_capacity))return -2;
 if(collision(phys,bytes,staging_physical,staging_capacity))return -3;
 unsigned delta=phys&4095u;if(bytes>0xffffffffu-delta-4095u)return -4;
 unsigned n=(bytes+delta+4095u)&~4095u;
 int fd=open("/dev/stream",2);if(fd<0)return -5;
 void *p=mmap(0,n,writable?3:1,1,fd,(long)(phys&~4095u));close(fd);
 if(p==(void *)-1)return -6;
 *out=(mapping){p,n,(unsigned char *)p+delta};return 0;
}
static int unmap_memory(mapping *m){
 if(m->base && munmap(m->base,m->length))return -1;
 *m=(mapping){0};return 0;
}
static int load_calls(void){
 void *b=dlopen("libBizFw.so",6),*o=dlopen("libObj.so",6);
 if(!b || !o){trace("LIBRARY_LOAD_FAILED",!!b,!!o,0);return -1;}
 for(unsigned i=0;i<VG_SDK_COUNT;i++){
  sdk[i]=dlsym(b,vg_sdk_names[i]);
  if(!sdk[i]){trace("SDK_SYMBOL_MISSING",i,0,0);return -1;}
  if(memcmp((void *)((uintptr_t)sdk[i]&~(uintptr_t)1),vg_sdk_guards[i],16)){trace("SDK_GUARD_MISMATCH",i,0,0);return -1;}
 }
 int fd=open("/proc/self/maps",0);if(fd<0){trace("MAPS_OPEN_FAILED",0,0,0);return -1;}
 /* procfs seq_file reads may return a page-sized prefix before EOF. A short
  * read is not EOF: libObj is beyond byte 14000 in the failed target maps.
  * Reserve the terminator, read through EOF, and reject truncated input. */
 unsigned n=0;int r=0;
 while(n<sizeof(listing)-1){
  r=read(fd,listing+n,sizeof(listing)-1-n);
  if(r<=0)break;
  if((unsigned)r>sizeof(listing)-1-n){close(fd);trace("MAPS_READ_INVALID",n,(unsigned)r,0);return -1;}
  n+=(unsigned)r;
 }
 if(r<0){close(fd);trace("MAPS_READ_FAILED",n,0,0);return -1;}
 if(n==sizeof(listing)-1){
  unsigned char extra; r=read(fd,&extra,1);
  if(r!=0){close(fd);trace("MAPS_TOO_LARGE",n,0,0);return -1;}
 }
 close(fd);
 if(!n){trace("MAPS_EMPTY",0,0,0);return -1;}
 trace("MAPS_READ",n,0,0);
 listing[n]=0;unsigned base=0;char *p=(char *)listing;
 struct region {unsigned lo,hi;} readable[128];unsigned regions=0;
 while(*p){char *end=p;while(*end && *end!='\n')end++;char saved=*end;*end=0;
  unsigned lo,hi,offset;char perms[8],path[256]={0};
  if(sscanf(p,"%x-%x %7s %x %*s %*s %255s",&lo,&hi,perms,&offset,path)==5){
   unsigned j=0;while(path[j])j++;const char suffix[]="/libObj.so";
   if(j>=sizeof(suffix)-1 && !memcmp(path+j-(sizeof(suffix)-1),suffix,sizeof(suffix)-1)){
    if(!offset)base=lo;
    if(perms[0]=='r' && regions<128)readable[regions++]=(struct region){lo,hi};
   }
  }
  *end=saved;if(!saved)break;p=end+1;
 }
 if(!base){trace("OBJ_MAPPING_MISSING",n,regions,0);return -1;}
 for(unsigned i=0;i<VG_OBJ_COUNT;i++){
  if(base>0xffffffffu-16 || vg_obj_offsets[i]>0xffffffffu-base-16){trace("OBJ_ADDRESS_OVERFLOW",i,base,0);return -1;}
  unsigned address=base+vg_obj_offsets[i],valid=0;
  for(unsigned j=0;j<regions;j++)if(address>=readable[j].lo && address+16<=readable[j].hi)valid=1;
  if(!valid){trace("OBJ_RANGE_MISMATCH",i,address,regions);return -1;}
  obj[i]=(void *)(uintptr_t)(address+1);
  if(memcmp((void *)(uintptr_t)address,vg_obj_guards[i],16)){trace("OBJ_GUARD_MISMATCH",i,address,0);return -1;}
 }
 /* Lazy initialization, after all guards passed, on the private worker only. */
 ((void (*)(void *,unsigned short))sdk[VG_DMM_CTOR])(dmm,0x35);
 ((void (*)(void *,unsigned short))sdk[VG_SDF_CTOR])(sdf,0x35);
 ((void (*)(void *))obj[VG_ALLOC_CTOR])(allocator);
 unsigned dq,sq,aq;memcpy(&dq,dmm+4,4);memcpy(&sq,sdf+4,4);memcpy(&aq,allocator+8,4);
 if(!dq || !sq || !aq){trace("QUEUE_INIT_FAILED",dq,sq,aq);return -1;}
 trace("QUEUES",dq,sq,aq);
 return 0;
}
static int dmm_status(int rc,const unsigned char *reply){return rc || (int16_t)(reply[2]|reply[3]<<8)<0;}
/* Failure-only wire evidence: all six words are diagnostic data, never handles
 * to replay. Keep ownership/quarantine behavior unchanged until replies prove
 * whether acquisition completed. Logging must not invoke Sony IPC. */
static unsigned reply_word(const unsigned char *r,unsigned off){
 return (unsigned)r[off]|(unsigned)r[off+1]<<8|(unsigned)r[off+2]<<16|(unsigned)r[off+3]<<24;
}
static void reply_evidence(const char *tag,unsigned handle,int rc,const unsigned char *reply){
 trace(tag,handle,(unsigned)rc,reply_word(reply,0));
 trace("DMM_REPLY_04",reply_word(reply,4),reply_word(reply,8),reply_word(reply,12));
 trace("DMM_REPLY_10",reply_word(reply,16),reply_word(reply,20),0);
}
/* Exact negative mode-0 Share completion verified against dmm.ko:
 * native -1 returns BEFORE the allocation reference increment. This only
 * skips optional source candidates; all unknown outcomes still quarantine. */
/* Original dmm.ko Share has no reference increment on these correlated
 * mode-0 failures. Required destination acquisitions remain strict. A wire
 * status alone is insufficient: native status and every echoed field match. */
static int optional_share_declined(int rc,const unsigned char *r,unsigned handle,unsigned type){
 unsigned q;memcpy(&q,dmm+4,4);
 if(rc || (reply_word(r,0)&65535u)!=0x8002u ||
    (reply_word(r,4)&65535u)!=handle || (reply_word(r,4)>>16)!=(q&65535u) ||
    (reply_word(r,8)&65535u) || reply_word(r,12)!=type || reply_word(r,16) || reply_word(r,20))return 0;
 unsigned status=reply_word(r,0)>>16,native=reply_word(r,8)>>16;
 return (status==0xffffu && native==0xffffu) ||
        (status==0xfffbu && (native==0xfdfbu || native==0xfefbu)) ||
        (status==0xfffdu && native==0xfffdu);
}
static int reply_identity(const unsigned char *r,unsigned command,unsigned handle){
 unsigned q;memcpy(&q,dmm+4,4);
 return (reply_word(r,0)&65535u)==(command|0x8000u) &&
        (reply_word(r,4)&65535u)==handle && (reply_word(r,4)>>16)==(q&65535u);
}
static int take_impl(lease *l,unsigned handle,unsigned type,unsigned optional_source){
 unsigned char reply[24]={0};
 if(stopping)return 2; /* cancelled before requesting any ownership */
 l->ref.handle=handle;l->ref.type=type;
 trace("SHARE",handle,type,0);
 l->shared=1;
 int rc=((int (*)(void *,void *,unsigned,unsigned short,unsigned short))sdk[VG_SHARE])(dmm,reply,type,handle,0);
 if(dmm_status(rc,reply)){
  if(optional_source && !l->opened && !l->map.base && optional_share_declined(rc,reply,handle,type)){
   reply_evidence(optional_source==2?"PIXEL_SHARE_DECLINED":"SOURCE_SHARE_DECLINED",handle,rc,reply);
   *l=(lease){0};return 1;
  }
  reply_evidence("SHARE_FAILED",handle,rc,reply);__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;
 }
 if(!reply_identity(reply,2,handle) || reply_word(reply,0)!=0x8002u || reply_word(reply,8) ||
    reply_word(reply,12)!=type || reply_word(reply,16) || reply_word(reply,20)){
  reply_evidence("SHARE_REPLY_UNEXPECTED",handle,rc,reply);__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;
 }
 trace("SHARE_OK",handle,reply_word(reply,0),reply_word(reply,4));
 if(stopping)return 2;
 memset(reply,0,24);l->opened=1;
 trace("OPEN",handle,0,0);
 rc=((int (*)(void *,void *,unsigned short,unsigned short,unsigned))sdk[VG_OPEN])(dmm,reply,handle,0,0);
 if(dmm_status(rc,reply)){
  reply_evidence("OPEN_FAILED",handle,rc,reply);__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;
 }
 if(!reply_identity(reply,5,handle) || reply_word(reply,0)!=0x8005u){
  reply_evidence("OPEN_REPLY_UNEXPECTED",handle,rc,reply);__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;
 }
 if((reply[8]|reply[9]<<8)!=1){
  reply_evidence("OPEN_SITE_REJECTED",handle,rc,reply);__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;
 }
 memcpy(&l->ref.physical,reply+16,4);memcpy(&l->ref.bytes,reply+20,4);
 trace("OPEN_OK",handle,l->ref.physical,l->ref.bytes);
 rc=map_memory(l->ref.physical,l->ref.bytes,&l->map,0);
 if(rc){trace("LEASE_MAP_FAILED",handle,(unsigned)rc,l->ref.physical);trace("LEASE_MAP_BYTES",l->ref.bytes,usb_physical,staging_physical);__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
 trace("LEASE_READY",handle,l->ref.physical,l->ref.bytes);
 return 0;
}
static int take(lease *l,unsigned handle,unsigned type){return take_impl(l,handle,type,0);}
/* Independent source-allocation credit survives native manager teardown. */
static int reserve_usb_source(void){
 if(usb_reserved)return 0;
 unsigned char reply[24]={0};
 int rc=((int (*)(void *,void *,unsigned,unsigned short,unsigned short))sdk[VG_SHARE])(dmm,reply,0x276,(unsigned short)usb_handle,0);
 if(rc || !reply_identity(reply,2,usb_handle) || reply_word(reply,0)!=0x8002u || reply_word(reply,8) || reply_word(reply,12)!=0x276 || reply_word(reply,16) || reply_word(reply,20)){
  reply_evidence("USB_SOURCE_SHARE_UNCERTAIN",usb_handle,rc,reply);return -1;
 }
 usb_reserved=1;trace("USB_SOURCE_RESERVED",usb_handle,usb_physical,usb_capacity);return 0;
}
static int drop(lease *l){
 unsigned char reply[24]={0};int rc;
 if(fault)return -1;
 if(unmap_memory(&l->map)){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
 if(l->opened){
  rc=((int (*)(void *,void *,unsigned short))sdk[VG_CLOSE])(dmm,reply,l->ref.handle);
  if(dmm_status(rc,reply) || !reply_identity(reply,6,l->ref.handle)){trace("CLOSE_UNCERTAIN",l->ref.handle,(unsigned)rc,reply_word(reply,0));__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}l->opened=0;
 }
 if(l->shared){memset(reply,0,24);
  rc=((int (*)(void *,void *,unsigned short,unsigned short))sdk[VG_FREE])(dmm,reply,l->ref.handle,l->granted?2:0);
  if(dmm_status(rc,reply) || !reply_identity(reply,4,l->ref.handle)){trace("FREE_UNCERTAIN",l->ref.handle,(unsigned)rc,reply_word(reply,0));__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}l->shared=0;
 }
 return 0;
}
/* Only a matching native SEND delivers these references. VDF allocates a new
 * SDS and pre-shares its pixel attachment before sending. We consume that
 * transferred credit, never add a speculative Share to a pool-scanned handle. */
static unsigned port_ready,event_active;
static int open_transferred(lease *l){
 unsigned char reply[24]={0};l->opened=1;
 int rc=((int (*)(void *,void *,unsigned short,unsigned short,unsigned))sdk[VG_OPEN])(dmm,reply,l->ref.handle,0,0);
 if(dmm_status(rc,reply) || !reply_identity(reply,5,l->ref.handle) || reply_word(reply,0)!=0x8005u || (reply[8]|reply[9]<<8)!=1){
  reply_evidence("EVENT_OPEN_UNCERTAIN",l->ref.handle,rc,reply);__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;
 }
 memcpy(&l->ref.physical,reply+16,4);memcpy(&l->ref.bytes,reply+20,4);
 if(map_memory(l->ref.physical,l->ref.bytes,&l->map,0)){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
 return 0;
}
static int find_source(lease *meta,lease *pixels){
 yc_port_frame ev={0};int r=yc_port_next(&ev,20);
 if(r>0)return 1;
 if(r<0 || event_active){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
 event_active=1;*meta=(lease){0};*pixels=(lease){0};
 meta->ref.handle=ev.sds;meta->ref.type=ev.type;meta->shared=meta->granted=1;
 /* Even on stop, decode the granted SDS to identify the pixel credit that we
  * must return. A stop flag is not permission to forget a received transfer. */
 if(open_transferred(meta))return -1;
 sony_yc_metadata m;sony_yc_state_info state;sony_yc_multiple_segment_info multi;
 if(meta->ref.bytes>sizeof(source_snapshot)){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
 memcpy(source_snapshot,meta->map.bytes,meta->ref.bytes);barrier();
 if(memcmp(source_snapshot,meta->map.bytes,meta->ref.bytes) ||
    sony_yc_sds_decode_image(source_snapshot,meta->ref.bytes,&m) ||
    sony_yc_sds_decode_state(source_snapshot,meta->ref.bytes,&state) ||
    sony_yc_sds_decode_multi_segment(source_snapshot,meta->ref.bytes,&multi)!=-2 ||
    m.unit_type!=0x295 || !m.unit_handle || m.unit_handle==meta->ref.handle){
  trace("EVENT_DESCRIPTOR_REJECTED",ev.sds,0,0);__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;
 }
 pixels->ref.handle=m.unit_handle;pixels->ref.type=m.unit_type;pixels->shared=pixels->granted=1;
 if(open_transferred(pixels) || vga_source_contract(&m,pixels->ref.bytes,pixels->ref.handle)){
  __atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;
 }
 trace("SOURCE_EVENT",ev.sds,m.unit_handle,(m.canvas_size_x<<16)|m.canvas_size_y);
 if(!generation)trace("SOURCE_FLAGS",m.yc_compress,(m.data_placement<<24)|(m.data_content<<16)|(m.data_scan<<8)|m.yc_bit_depth,m.strip_width);
 return 0;
}
static int return_event(lease *meta,lease *pixels){
 if(drop(pixels) || drop(meta))return -1;
 if(event_active){
  if(yc_port_complete()){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
  event_active=0;
 }
 return 0;
}
static void close_source_port(lease *meta,lease *pixels){
 if(!port_ready || fault)return;
 if(yc_port_close()){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return;}
 for(unsigned n=0;n<200 && !yc_port_is_closed() && !fault;n++){
  int r=find_source(meta,pixels);
  if(r<0)break;
  if(!r && return_event(meta,pixels))break;
 }
 if(!yc_port_is_closed()){trace("EVENT_DISCONNECT_UNCERTAIN",0,0,0);__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);}
}

static int destination(void){
 if(stopping)return 1;
 if(destination_ready)return 0;
 trace("ALLOCATE",0x220,640,480);
 /* Original allocNewSdsAndYc and original YC metadata constructor/store. */
 int rc=((int (*)(void *,void *,unsigned,void *))obj[VG_ALLOC_PAIR])(allocator,&destination_sds,0x220,0);
 if(rc){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;} /* Partial success/rollback details not inferred. */
 if(!destination_sds.handle || destination_sds.type!=0xe0b00 ||
    !dram(destination_sds.physical,destination_sds.bytes) || destination_sds.bytes>65536){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
 if(stopping)return 1;
 if(!destination_image.handle){
  /* The pair helper returns SDS only; retrieve its actual image attachment
   * through the original accessor. Do not assume a second returned handle. */
  ((void (*)(void *,const void *,unsigned,unsigned))obj[VG_YC_CTOR])(accessor,&destination_sds,0,0);
  unsigned char *wire=accessor+0x124;
  destination_image.type=0x220;destination_image.handle=(uint16_t)(wire[8]|wire[9]<<8);
  if(!destination_image.handle || wire[0]!=1){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
  uint16_t geometry[10]={640,480,0,0,640,480,0,0,640,480};
  ((void (*)(void *,const void *))obj[VG_GEOMETRY])(accessor,geometry);
  rc=((int (*)(void *))obj[VG_STORE])(accessor);
  sony_yc_metadata m;lease checked={0};
  if(!rc && !sony_yc_metadata_decode(wire,60,&m)){
   if(take(&checked,destination_image.handle,0x220) ||
      vga_destination_contract(&m,checked.ref.bytes,destination_image.handle))rc=-1;
   if(!rc){destination_image.physical=checked.ref.physical;destination_image.bytes=checked.ref.bytes;}
   if(!fault && drop(&checked))rc=-1;
  }else rc=-1;
  ((void (*)(void *))obj[VG_YC_DTOR])(accessor);
  if(rc){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
 }
 destination_ready=1;return 0;
}
static int freeze_input(const lease *source,const lease *pixels){
 /* A DMM share pins allocation lifetime, not the producer's mutable SSYC
  * fields. Send an OWNED metadata copy pointing to the pinned pixel handle. */
 if(!input_sds.handle){
  unsigned char reply[24]={0};trace("ALLOCATE_INPUT_SSYC",0xe0b00,source->ref.bytes,0);
  int rc=((int (*)(void *,void *,unsigned,unsigned short,unsigned))sdk[VG_ALLOC_NEW])(dmm,reply,0xe0b00,1,0xffffffffu);
  if(dmm_status(rc,reply)){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
  input_sds.handle=(uint16_t)(reply[4]|reply[5]<<8);input_sds.type=0xe0b00;
  memcpy(&input_sds.physical,reply+16,4);memcpy(&input_sds.bytes,reply+20,4);
  if(!input_sds.handle || (reply[8]|reply[9]<<8)!=1 || input_sds.bytes>65536 ||
     map_memory(input_sds.physical,input_sds.bytes,&input_mapping,1)){
   __atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;
  }
 }
 if(source->ref.bytes>input_sds.bytes ||
    collision(input_sds.physical,input_sds.bytes,source->ref.physical,source->ref.bytes) ||
    collision(input_sds.physical,input_sds.bytes,pixels->ref.physical,pixels->ref.bytes) ||
    collision(input_sds.physical,input_sds.bytes,destination_sds.physical,destination_sds.bytes) ||
    collision(input_sds.physical,input_sds.bytes,destination_image.physical,destination_image.bytes)){
  trace("INPUT_SSYC_RANGE_REJECTED",source->ref.bytes,input_sds.bytes,0);__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;
 }
 memcpy(input_mapping.bytes,source_snapshot,source->ref.bytes);
 if(source->ref.bytes<input_sds.bytes)memset(input_mapping.bytes+source->ref.bytes,0,input_sds.bytes-source->ref.bytes);
 barrier();return 0;
}
static int resize_frame(lease *source,const lease *pixels){
 if(stopping)return 1;
 unsigned char command[68]={0},cmp[24]={0},ack[16]={0};
 if(collision(destination_image.physical,destination_image.bytes,pixels->ref.physical,pixels->ref.bytes) ||
    collision(destination_image.physical,destination_image.bytes,source->ref.physical,source->ref.bytes)){
  __atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;
 }
 if(freeze_input(source,pixels))return -1;
 if(stopping)return 1;
 if(!generation){memcpy(first_input,input_mapping.bytes,input_sds.bytes);first_input_bytes=input_sds.bytes;}
 memcpy(command+0x18,&input_sds.type,4);memcpy(command+0x1c,&input_sds.handle,2);
 command[0x25]=1;memcpy(command+0x38,&destination_sds.type,4);memcpy(command+0x3c,&destination_sds.handle,2);
 trace("RESIZE_READY",input_sds.handle,destination_sds.handle,generation);
 if(stopping)return 1;
 trace("RESIZE_ENTER",input_sds.handle,destination_sds.handle,generation);
 int rc=((int (*)(void *,void *,void *,void *))sdk[VG_RESIZE])(sdf,cmp,ack,command);

 unsigned ack_status,cmp_status;memcpy(&ack_status,ack+8,4);memcpy(&cmp_status,cmp+8,4);
 trace("RESIZE_RETURN",(unsigned)rc,ack_status,cmp_status);
 if(rc || ack_status || cmp_status){trace("REJECTED",rc,ack_status,cmp_status);__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
 return 0;
}
static void *worker(void *unused){
 (void)unused;lease meta={0},pixels={0},outmeta={0},outpixels={0};
 if(stopping)goto done;
 if(!initialized){if(load_calls()){trace("GUARD_FAILED",0,0,0);__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);goto done;}initialized=1;}
 trace_flush();
 if(stopping)goto done;
 if(reserve_usb_source()){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);goto done;}
 if(destination())goto done;
 if(yc_port_init(sdk[VG_DMM_CTOR],sdk[VG_WIRE_SEND],trace)){trace("SOURCE_CONNECT_FAILED",0,0,0);__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);goto done;}port_ready=1;
 trace_flush();
 while(!stopping && !fault){
  /* One pending frame is enough. Do not keep invoking SDF while the host is
   * absent or the USB worker has not consumed the previous completed copy. */
  if(available){int skipped=find_source(&meta,&pixels);if(skipped<0)break;if(!skipped && return_event(&meta,&pixels))break;continue;}
  int found=find_source(&meta,&pixels);
  if(found<0){trace("SOURCE_SEARCH_FAILED",0,0,0);break;}
  if(found){trace_flush();continue;}
  if(stopping){return_event(&meta,&pixels);break;}
  if(resize_frame(&meta,&pixels))break;
  /* SDK success means ACK and CMP returned. Re-open and read destination
   * metadata after completion, and validate the actual attachment/capacity. */
  if(take(&outmeta,destination_sds.handle,destination_sds.type))break;
  sony_yc_metadata m;
  if(sony_yc_sds_decode_image(outmeta.map.bytes,outmeta.ref.bytes,&m) ||
     m.unit_handle!=destination_image.handle || m.unit_type!=0x220){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);break;}
  if(take(&outpixels,m.unit_handle,m.unit_type))break;
  if(vga_destination_contract(&m,outpixels.ref.bytes,outpixels.ref.handle)){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);trace("DEST_FORMAT_REJECTED",m.yc_compress,m.canvas_size_x,m.canvas_size_y);break;}
  if(!generation){
   trace("DEST_FLAGS",m.yc_compress,(m.data_placement<<24)|(m.data_content<<16)|(m.data_scan<<8)|m.yc_bit_depth,m.strip_width);
   if(outmeta.ref.bytes>sizeof(first_dest)){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);break;}
   memcpy(first_dest,outmeta.map.bytes,outmeta.ref.bytes);first_dest_bytes=outmeta.ref.bytes;
  }
  if(!__sync_lock_test_and_set(&lock,1)){
   if(!generation)memcpy(first_native,outpixels.map.bytes+m.unit_data_offset,VGA_BYTES);
   yc_uyvy_to_yuy2(published,outpixels.map.bytes+m.unit_data_offset,VGA_BYTES);
   __atomic_add_fetch(&shared_generation,1,__ATOMIC_RELEASE);if(!generation)__atomic_add_fetch(&shared_generation,1,__ATOMIC_RELEASE);barrier();__atomic_store_n(&shared_available,1,__ATOMIC_RELEASE);__sync_lock_release(&lock);
   trace("COMPLETE",generation,VGA_BYTES,m.data_placement);
  }
  if(drop(&outpixels) || drop(&outmeta) || return_event(&meta,&pixels))break;
  trace_flush();
 }
done:
 /* Only the private worker performs known-reference cleanup. Global fault
  * still quarantines uncertain replies or hardware outcomes. */
 if(!fault){
  if(drop(&outpixels) || drop(&outmeta) || return_event(&meta,&pixels)){}
  close_source_port(&meta,&pixels);
  if(!fault && generation){
   /* Dump only after producer disconnect and queue drain. Flash I/O never
    * holds a source credit or blocks the live producer for a 614400-byte dump. */
   evidence("/log/yuy2_640_v37vga/native-vga-first.bin",first_native,VGA_BYTES);
   evidence("/log/yuy2_640_v37vga/input-ssyc.bin",first_input,first_input_bytes);
   evidence("/log/yuy2_640_v37vga/destination-ssyc.bin",first_dest,first_dest_bytes);
  }
 }
 __atomic_store_n(&shared_available,0,__ATOMIC_RELEASE);
 __atomic_store_n(&shared_stopping,1,__ATOMIC_RELEASE);
 /* Unknown SDK outcome: retain refs and mappings. Never free buffers that
  * might still be read/written by hardware; no new worker until cold boot. */
 if(fault)trace("QUARANTINED",meta.ref.handle,pixels.ref.handle,destination_sds.handle);
 else trace("STOPPED",generation,0,0);
 trace("TRACE_DROPPED",__atomic_load_n(&trace_dropped,__ATOMIC_RELAXED),0,0);
 trace_flush();
 /* running denotes actual thread liveness; fault/stopping prohibit restart. */
 __atomic_store_n(&shared_running,0,__ATOMIC_RELEASE);return 0;
}
int vga_resize_copy(void *out,unsigned capacity,uint32_t *sequence,uint32_t physical,uint32_t stage,uint32_t stage_bytes,uint32_t handle){
 if(!out || capacity<VGA_BYTES || !sequence || !handle || handle>65535 || fault || stopping)return -1;
 if(!running){
  if(!dram(physical,capacity) || !dram(stage,stage_bytes) || collision(physical,capacity,stage,stage_bytes))return -1;
  if(__sync_val_compare_and_swap(&shared_running,0,1)!=0)return 1;
  usb_physical=physical;usb_capacity=capacity;staging_physical=stage;staging_capacity=stage_bytes;usb_handle=handle;
  if(stopping){__atomic_store_n(&shared_running,0,__ATOMIC_RELEASE);return -1;}
  unsigned long thread;int e=pthread_create(&thread,0,worker,0);
  if(e){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);__atomic_store_n(&shared_running,0,__ATOMIC_RELEASE);trace("THREAD_FAILED",e,0,0);return -1;}pthread_detach(thread);return 1;
 }
 if(physical!=usb_physical || capacity!=usb_capacity || stage!=staging_physical || stage_bytes!=staging_capacity || handle!=usb_handle)return -1;
 if(!available || __sync_lock_test_and_set(&lock,1))return 1;
 if(!available){__sync_lock_release(&lock);return 1;}
 memcpy(out,published,VGA_BYTES);*sequence=generation;__atomic_store_n(&shared_available,0,__ATOMIC_RELEASE);__sync_lock_release(&lock);return 0;
}
void vga_resize_stop(void){__atomic_store_n(&shared_stopping,1,__ATOMIC_RELEASE);barrier();trace("STOP_REQUESTED",running,generation,fault);}
int vga_resize_reusable(void){return !stopping && !fault;}
