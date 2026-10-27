/* Experimental Sony SDF VGA backend. Every Sony call runs on a private worker:
 * SDK synchronous receives can block indefinitely. Stop never kills that worker
 * or frees its resources; a stuck SDK request requires reboot, not reuse. */
#include "vga_resize.h"
#include "vga_contract.h"
#include "vga_guards.h"
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
static unsigned char published[VGA_BYTES],listing[131072];
static unsigned char dmm[256] __attribute__((aligned(8)));
static unsigned char allocator[256] __attribute__((aligned(8)));
static unsigned char sdf[256] __attribute__((aligned(8)));
static unsigned char accessor[512] __attribute__((aligned(8)));
typedef struct {uint16_t handle,pad;uint32_t type,physical,bytes;} memory_set;
typedef struct {void *base;unsigned length;unsigned char *bytes;} mapping;
typedef struct {memory_set ref;unsigned shared,opened;mapping map;} lease;
static memory_set destination_sds,destination_image;
static memory_set input_sds;
static mapping input_mapping;
static unsigned initialized,destination_ready,shared_fault;
static unsigned trace_bytes;
static unsigned usb_physical,usb_capacity,staging_physical,staging_capacity;
static unsigned char source_snapshot[65536];
static void trace(const char *tag,unsigned a,unsigned b,unsigned c){
 char row[160];int n=snprintf(row,sizeof(row),"VGA %s %08x %08x %08x\n",tag,a,b,c);
 if(n<=0 || (unsigned)n>=sizeof(row) || __sync_fetch_and_add(&trace_bytes,(unsigned)n)>65536u-(unsigned)n)return;
 int fd=open("/log/yuy2_640_v30vga/vga.log",0x441,0644);
 if(fd>=0){if(n>0 && (unsigned)n<sizeof(row))write(fd,row,(unsigned)n);close(fd);}
}
static void barrier(void){__sync_synchronize();}
static void evidence(const char *path,const void *p,unsigned n){
 if(!n || n>65536)return;
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
 if(!dram(phys,bytes) || collision(phys,bytes,usb_physical,usb_capacity) ||
    collision(phys,bytes,staging_physical,staging_capacity))return -1;
 unsigned delta=phys&4095u;if(bytes>0xffffffffu-delta-4095u)return -1;
 unsigned n=(bytes+delta+4095u)&~4095u;
 int fd=open("/dev/stream",2);if(fd<0)return -1;
 void *p=mmap(0,n,writable?3:1,1,fd,(long)(phys&~4095u));close(fd);
 if(p==(void *)-1)return -1;
 *out=(mapping){p,n,(unsigned char *)p+delta};return 0;
}
static int unmap_memory(mapping *m){
 if(m->base && munmap(m->base,m->length))return -1;
 *m=(mapping){0};return 0;
}
static int load_calls(void){
 void *b=dlopen("libBizFw.so",6),*o=dlopen("libObj.so",6);
 if(!b || !o)return -1;
 for(unsigned i=0;i<VG_SDK_COUNT;i++){
  sdk[i]=dlsym(b,vg_sdk_names[i]);
  if(!sdk[i] || memcmp((void *)((uintptr_t)sdk[i]&~(uintptr_t)1),vg_sdk_guards[i],16))return -1;
 }
 int fd=open("/proc/self/maps",0);if(fd<0)return -1;
 int n=read(fd,listing,sizeof(listing)-1);close(fd);if(n<=0 || (unsigned)n>=sizeof(listing)-1)return -1;
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
 if(!base)return -1;
 for(unsigned i=0;i<VG_OBJ_COUNT;i++){
  if(vg_obj_offsets[i]>0xffffffffu-base-16)return -1;
  unsigned address=base+vg_obj_offsets[i],valid=0;
  for(unsigned j=0;j<regions;j++)if(address>=readable[j].lo && address+16<=readable[j].hi)valid=1;
  if(!valid)return -1;
  obj[i]=(void *)(uintptr_t)(address+1);
  if(memcmp((void *)(uintptr_t)address,vg_obj_guards[i],16))return -1;
 }
 /* Lazy initialization, after all guards passed, on the private worker only. */
 ((void (*)(void *,unsigned short))sdk[VG_DMM_CTOR])(dmm,0x35);
 ((void (*)(void *,unsigned short))sdk[VG_SDF_CTOR])(sdf,0x35);
 ((void (*)(void *))obj[VG_ALLOC_CTOR])(allocator);
 unsigned dq,sq,aq;memcpy(&dq,dmm+4,4);memcpy(&sq,sdf+4,4);memcpy(&aq,allocator+8,4);
 if(!dq || !sq || !aq)return -1;
 trace("QUEUES",dq,sq,aq);
 return 0;
}
static int dmm_status(int rc,const unsigned char *reply){return rc || (int16_t)(reply[2]|reply[3]<<8)<0;}
static int take(lease *l,unsigned handle,unsigned type){
 unsigned char reply[24]={0};l->ref.handle=handle;l->ref.type=type;
 trace("SHARE",handle,type,0);
 /* Mark potential ownership BEFORE a possibly blocking call. On ambiguous
  * SDK failure quarantine the worker/context; never retry or free blindly. */
 l->shared=1;
 int rc=((int (*)(void *,void *,unsigned,unsigned short,unsigned short))sdk[VG_SHARE])(dmm,reply,type,handle,0);
 if(dmm_status(rc,reply)){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
 memset(reply,0,24);l->opened=1;
 rc=((int (*)(void *,void *,unsigned short,unsigned short,unsigned))sdk[VG_OPEN])(dmm,reply,handle,0,0);
 if(dmm_status(rc,reply)){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
 if((reply[8]|reply[9]<<8)!=1){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
 memcpy(&l->ref.physical,reply+16,4);memcpy(&l->ref.bytes,reply+20,4);
 if(map_memory(l->ref.physical,l->ref.bytes,&l->map,0)){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
 return 0;
}
static int drop(lease *l){
 unsigned char reply[24]={0};int rc;
 if(fault)return -1;
 if(unmap_memory(&l->map)){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
 if(l->opened){
  rc=((int (*)(void *,void *,unsigned short))sdk[VG_CLOSE])(dmm,reply,l->ref.handle);
  if(dmm_status(rc,reply)){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}l->opened=0;
 }
 if(l->shared){memset(reply,0,24);
  rc=((int (*)(void *,void *,unsigned short,unsigned short))sdk[VG_FREE])(dmm,reply,l->ref.handle,0);
  if(dmm_status(rc,reply)){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}l->shared=0;
 }
 return 0;
}
/* Candidate listings are hints. Only a pinned, valid SSYC with a 0x295 image
 * attachment can become the SDF source. No fixed address or first-pixel guess. */
static int find_source(lease *meta,lease *pixels){
 static unsigned scan_after;
 struct candidate {unsigned h,t,physical,bytes;} candidates[64];unsigned count=0;
 int fd=open("/proc/udm/dmm_units",0);if(fd<0)return -1;
 unsigned n=0;int r;
 while(n<sizeof(listing)-1 && (r=read(fd,listing+n,sizeof(listing)-1-n))>0)n+=(unsigned)r;
 close(fd);if(n==sizeof(listing)-1 || !n)return -1;listing[n]=0;
 char *p=(char *)listing;
 while(*p && count<64){char *end=p;while(*end && *end!='\n')end++;char saved=*end;*end=0;
  unsigned h,t,s,a,o,rd,se,re,ad,sz;
  if(sscanf(p,"%x %x %x %x %x %x %x %x %x %x",&h,&t,&s,&a,&o,&rd,&se,&re,&ad,&sz)==10 &&
     h && h>scan_after && h<=65535 && s==2 && a && sz>=128 && sz<=sizeof(source_snapshot) &&
     ad && ad<0x40000000u && sz<=0x40000000u-ad &&
     h!=destination_sds.handle && h!=destination_image.handle && h!=input_sds.handle)
   candidates[count++]=(struct candidate){h,t,ad,sz};
  *end=saved;if(!saved)break;p=end+1;
 }
 for(unsigned i=0;i<count && !stopping;i++){
  /* Read-only signature peek is just a hint from the listing, not a lease.
   * No pixels are consumed and no SDF command is sent until Share/Open and
   * complete metadata validation below. Avoid IPC on unrelated small units. */
  mapping peek={0};unsigned char signature[12];
  if(map_memory(candidates[i].physical,candidates[i].bytes,&peek,0))continue;
  memcpy(signature,peek.bytes,sizeof(signature));
  if(unmap_memory(&peek)){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
  if(memcmp(signature,"SSYC",4) || signature[8]!=1 || signature[9] || signature[10] || signature[11])continue;
  *meta=(lease){0};*pixels=(lease){0};
  if(take(meta,candidates[i].h,candidates[i].t))return -1;
  sony_yc_metadata m,m2;sony_yc_state_info state;sony_yc_multiple_segment_info multi;
  if(meta->ref.bytes>sizeof(source_snapshot)) {if(drop(meta))return -1;continue;}
  memcpy(source_snapshot,meta->map.bytes,meta->ref.bytes);barrier();
  if(memcmp(source_snapshot,meta->map.bytes,meta->ref.bytes) ||
     sony_yc_sds_decode_image(source_snapshot,meta->ref.bytes,&m) ||
     sony_yc_sds_decode_state(source_snapshot,meta->ref.bytes,&state) ||
     sony_yc_sds_decode_multi_segment(source_snapshot,meta->ref.bytes,&multi)!=-2 ||
     m.unit_type!=0x295 || !m.unit_handle || m.unit_handle==meta->ref.handle){
   if(drop(meta))return -1;continue;
  }
  if(take(pixels,m.unit_handle,m.unit_type))return -1;
  if(sony_yc_sds_decode_image(meta->map.bytes,meta->ref.bytes,&m2) || memcmp(&m,&m2,sizeof(m)) ||
     vga_source_contract(&m,pixels->ref.bytes,pixels->ref.handle)){
   if(drop(pixels) || drop(meta))return -1;continue;
  }
  trace("SOURCE",meta->ref.handle,m.unit_handle,(m.canvas_size_x<<16)|m.canvas_size_y);
  if(!generation)trace("SOURCE_FLAGS",m.yc_compress,(m.data_placement<<24)|(m.data_content<<16)|(m.data_scan<<8)|m.yc_bit_depth,m.strip_width);
  scan_after=0;return 0;
 }
 scan_after=count==64?candidates[count-1].h:0;
 return 1;
}
static int destination(void){
 if(destination_ready)return 0;
 trace("ALLOCATE",0x220,640,480);
 /* Original allocNewSdsAndYc and original YC metadata constructor/store. */
 int rc=((int (*)(void *,void *,unsigned,void *))obj[VG_ALLOC_PAIR])(allocator,&destination_sds,0x220,0);
 if(rc){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;} /* Partial success/rollback details not inferred. */
 if(!destination_sds.handle || destination_sds.type!=0xe0b00 ||
    !dram(destination_sds.physical,destination_sds.bytes) || destination_sds.bytes>65536){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
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
 unsigned char command[68]={0},cmp[24]={0},ack[16]={0};
 if(collision(destination_image.physical,destination_image.bytes,pixels->ref.physical,pixels->ref.bytes) ||
    collision(destination_image.physical,destination_image.bytes,source->ref.physical,source->ref.bytes)){
  __atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;
 }
 if(freeze_input(source,pixels))return -1;
 if(!generation)evidence("/log/yuy2_640_v30vga/input-ssyc.bin",input_mapping.bytes,input_sds.bytes);
 memcpy(command+0x18,&input_sds.type,4);memcpy(command+0x1c,&input_sds.handle,2);
 command[0x25]=1;memcpy(command+0x38,&destination_sds.type,4);memcpy(command+0x3c,&destination_sds.handle,2);
 trace("RESIZE",input_sds.handle,destination_sds.handle,generation);
 int rc=((int (*)(void *,void *,void *,void *))sdk[VG_RESIZE])(sdf,cmp,ack,command);
 unsigned ack_status,cmp_status;memcpy(&ack_status,ack+8,4);memcpy(&cmp_status,cmp+8,4);
 if(rc || ack_status || cmp_status){trace("REJECTED",rc,ack_status,cmp_status);__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}
 return 0;
}
static void *worker(void *unused){
 (void)unused;lease meta={0},pixels={0},outmeta={0},outpixels={0};
 if(!initialized){if(load_calls()){trace("GUARD_FAILED",0,0,0);__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);goto done;}initialized=1;}
 if(destination())goto done;
 while(!stopping && !fault){
  /* One pending frame is enough. Do not keep invoking SDF while the host is
   * absent or the USB worker has not consumed the previous completed copy. */
  if(available){usleep(10000);continue;}
  int found=find_source(&meta,&pixels);
  if(found<0)break;
  if(found){trace("NO_SOURCE_SSYC",0,0,0);usleep(500000);continue;}
  if(stopping){drop(&pixels);drop(&meta);break;}
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
   evidence("/log/yuy2_640_v30vga/destination-ssyc.bin",outmeta.map.bytes,outmeta.ref.bytes);
  }
  if(!__sync_lock_test_and_set(&lock,1)){
   memcpy(published,outpixels.map.bytes+m.unit_data_offset,VGA_BYTES);
   __atomic_add_fetch(&shared_generation,1,__ATOMIC_RELEASE);if(!generation)__atomic_add_fetch(&shared_generation,1,__ATOMIC_RELEASE);barrier();__atomic_store_n(&shared_available,1,__ATOMIC_RELEASE);__sync_lock_release(&lock);
   trace("COMPLETE",generation,VGA_BYTES,m.data_placement);
  }
  if(drop(&outpixels) || drop(&outmeta) || drop(&pixels) || drop(&meta))break;
  usleep(100000);
 }
done:
 /* Unknown SDK outcome: retain refs and mappings. Never free buffers that
  * might still be read/written by hardware; no new worker until cold boot. */
 if(fault){trace("QUARANTINED",meta.ref.handle,pixels.ref.handle,destination_sds.handle);return 0;}
 __atomic_store_n(&shared_available,0,__ATOMIC_RELEASE);barrier();__atomic_store_n(&shared_running,0,__ATOMIC_RELEASE);trace("STOPPED",generation,0,0);return 0;
}
int vga_resize_copy(void *out,unsigned capacity,uint32_t *sequence,uint32_t physical,uint32_t stage,uint32_t stage_bytes){
 if(!out || capacity<VGA_BYTES || !sequence || fault || stopping)return -1;
 if(!running){
  if(!dram(physical,capacity) || !dram(stage,stage_bytes) || collision(physical,capacity,stage,stage_bytes))return -1;
  if(__sync_val_compare_and_swap(&shared_running,0,1)!=0)return 1;
  usb_physical=physical;usb_capacity=capacity;staging_physical=stage;staging_capacity=stage_bytes;
  unsigned long thread;int e=pthread_create(&thread,0,worker,0);
  if(e){__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);trace("THREAD_FAILED",e,0,0);return -1;}pthread_detach(thread);return 1;
 }
 if(physical!=usb_physical || capacity!=usb_capacity || stage!=staging_physical || stage_bytes!=staging_capacity)return -1;
 if(!available || __sync_lock_test_and_set(&lock,1))return 1;
 if(!available){__sync_lock_release(&lock);return 1;}
 memcpy(out,published,VGA_BYTES);*sequence=generation;__atomic_store_n(&shared_available,0,__ATOMIC_RELEASE);__sync_lock_release(&lock);return 0;
}
void vga_resize_stop(void){if(running){__atomic_store_n(&shared_stopping,1,__ATOMIC_RELEASE);barrier();trace("STOP_REQUESTED",running,generation,fault);}}
int vga_resize_reusable(void){return !stopping && !fault;}
