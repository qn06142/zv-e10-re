#include "native_dmm.h"
#include "native_dmm_sdk_guards.h"
extern void *dlopen(const char *,int),*dlsym(void *,const char *);
extern int memcmp(const void *,const void *,size_t);
extern int open(const char *,int,...),read(int,void *,unsigned),close(int);
extern int sscanf(const char *,const char *,...);
extern char *strchr(const char *,int);
static native_dmm backend;
static unsigned char channel[4096] __attribute__((aligned(8)));
static char listing[131072];
static size_t minimum_bytes;
static unsigned last_listing_bytes;
static int initialized,failed;
static int (*snd)(void *,void *,unsigned short,unsigned,unsigned);
static int (*rcv)(void *,void *,unsigned short,unsigned,unsigned);
int native_dmm_select_text(char *text,size_t minimum,native_dmm_candidate *out) {
 unsigned best=UINT32_MAX;native_dmm_candidate result={0};char *p=text;
 if(!text || !out || !minimum)return RAW_FRAME_ERR_INVALID_PARAM;
 while(*p){
  char *end=strchr(p,'\n');if(end)*end=0;
  unsigned h,t,s,a,o,rd,se,re,ad,sz;
  if(sscanf(p,"%x %x %x %x %x %x %x %x %x %x",&h,&t,&s,&a,&o,&rd,&se,&re,&ad,&sz)==10){
   unsigned priority=native_dmm_source_priority(t);
   if(priority<best && h && h<=65535 && s==2 && a && o && sz>=minimum &&
      ad && ad<0x40000000u && sz<=0x40000000u-ad){
    result.handle=h;result.type=t;best=priority;
   }
  }
  if(!end)break;p=end+1;
 }
 if(best==UINT32_MAX)return RAW_FRAME_ERR_TIMEOUT;
 *out=result;return 0;
}
static int select_unit(void *unused,native_dmm_candidate *out){
 (void)unused;int fd=open("/proc/udm/dmm_units",0);if(fd<0)return RAW_FRAME_ERR_IO;
 unsigned n=0;int r=0;
 while(n<sizeof(listing)-1 && (r=read(fd,listing+n,sizeof(listing)-1-n))>0)n+=r;
 /* Reject truncated listings rather than selecting from an incomplete record. */
 if(n==sizeof(listing)-1){char extra;r=read(fd,&extra,1);if(r!=0){close(fd);return RAW_FRAME_ERR_IO;}}
 close(fd);if(r<0 || !n)return RAW_FRAME_ERR_IO;listing[n]=0;last_listing_bytes=n;
 return native_dmm_select_text(listing,minimum_bytes,out);
}
static int send_request(void *unused,const unsigned char *p){
 (void)unused;return snd(channel,(void *)p,24,backend.io.queue,NATIVE_DMM_QUEUE);
}
static int receive_reply(void *unused,unsigned char *p){
 (void)unused;return rcv(channel,p,24,backend.io.queue,0);
}
int native_dmm_target_bind(raw_live_source *source,size_t offset){
 if(failed)return RAW_FRAME_ERR_IO;
 if(offset>UINT32_MAX-614400u)return RAW_FRAME_ERR_INVALID_PARAM;
 minimum_bytes=offset+614400u;
 if(!initialized){
  /* No constructors/hooks on Sony global methods. All traffic uses a private
   * native channel, resolved from the loaded library with SDK prologue guards. */
  void *lib=dlopen("libBizFw.so",6);void *symbols[4];
  if(!lib){failed=1;return RAW_FRAME_ERR_NOT_INIT;}
  for(unsigned i=0;i<4;i++){
   symbols[i]=dlsym(lib,sdk_names[i]);
   if(!symbols[i] || memcmp((void *)((uintptr_t)symbols[i]&~(uintptr_t)1),sdk_guards[i],16)){
    failed=1;return RAW_FRAME_ERR_IO;
   }
  }
  void (*ctor)(void *,unsigned short)=(void *)symbols[0];
  int (*alloc)(void *,unsigned *,unsigned)=(void *)symbols[1];
  snd=(void *)symbols[2];rcv=(void *)symbols[3];
  ctor(channel,1);
  if(alloc(channel,&backend.io.queue,1) || !backend.io.queue){failed=1;return RAW_FRAME_ERR_IO;}
  backend.io.select=select_unit;backend.io.send=send_request;backend.io.receive=receive_reply;
  initialized=1;
 }
 raw_live_ops ops={RAW_LIVE_ABI,sizeof(ops),native_dmm_acquire,native_dmm_release,
                    raw_live_target_map_readonly,raw_live_target_unmap};
 return raw_live_init(source,&ops,&backend,640,480,10);
}
int native_dmm_target_quiesce(void){return initialized?native_dmm_quiesce(&backend):0;}

int native_dmm_target_offset(size_t offset){
 if(!initialized)return 0;
 if(backend.state!=ND_IDLE)return RAW_FRAME_ERR_DEVICE_BUSY;
 if(offset>UINT32_MAX-614400u)return RAW_FRAME_ERR_INVALID_PARAM;
 minimum_bytes=offset+614400u;return 0;
}
