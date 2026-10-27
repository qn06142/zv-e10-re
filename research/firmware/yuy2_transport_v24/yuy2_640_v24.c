/* Volatile synthetic YUY2 producer for the inspected ZV-E10 binaries. */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef unsigned long size_t;
extern int open(const char*,int,...),close(int),read(int,void*,unsigned),write(int,const void*,unsigned);
extern int snprintf(char*,unsigned,const char*,...),sscanf(const char*,const char*,...);
extern int mprotect(void*,unsigned,int),usleep(unsigned);
extern void *mmap(void*,unsigned,int,int,int,long),*malloc(unsigned);
extern void free(void*);
extern int memcmp(const void*,const void*,unsigned);
extern void *memcpy(void*,const void*,unsigned),*memset(void*,int,unsigned);
extern void *dlopen(const char*,int),*dlsym(void*,const char*);
extern long syscall(long,...);
extern int *__errno_location(void);

#define FRAME_BYTES (640u*480u*2u)
#define INTERVAL_100NS 1000000u
#define LOG "/log/yuy2_640_v24/runtime.log"
static u32 sb,cb;
static int ready,init_error;
static unsigned failures,queue_attempts,in_flight,recovering,staging_waits,host_waits;
static int (*sem_lock)(void*),(*sem_unlock)(void*);
static int (*send_event)(unsigned),(*send_complete)(unsigned,void*);
static void *(*get_machine)(void*);
static int (*change_state)(void*,void*);
static int (*original_connect)(void*,void*);
static int (*original_start)(void*),(*original_stop)(void*),(*original_finish)(void*);
extern int munmap(void*,unsigned);
#define SOURCE_UNIT 0x276u
#define MAX_RETRIES 5u
#define FAIL_RESULT 0x10000003u
static int connect_hook(void*,void*),start_hook(void*),stop_hook(void*),finish_hook(void*);
static int failure_hook(void*,void*);
/* Filled by the builder from the exact inspected image. */
static const unsigned extra_offsets[6]={0x7aa8,0x903e,0x8f9c,0x8dbe,0x894c,0x83c8};
static const u8 extra_guards[6][10]={{0x2d,0xe9,0xf0,0x41,0x92,0xb0,0x0,0x22,0x4,0x46},{0xf0,0xb5,0x4,0x46,0x83,0xb0,0x2,0xaf,0x4,0x20},{0xf0,0xb5,0x4,0x46,0x83,0xb0,0x4,0x20,0x3,0x21},{0xb0,0xb5,0x4,0x46,0x1,0x21,0x4,0x20,0x0,0x22},{0x80,0xb5,0x3,0x20,0x0,0xaf,0x1,0x21,0x0,0x22},{0x3,0x20,0x0,0x22,0x80,0xb5,0x1,0x46,0x0,0xaf}};
/* A successfully initialized source is reserved for this module's lifetime.
 * manager is only the CURRENT worker binding, never the DMM allocation owner.
 * Clear it while its lifecycle call still owns a live self; never dereference
 * an old manager in a later session. Partial initialization still rolls back. */
static void *manager,*pixels,*mapping;
static unsigned map_len,capacity,physical,frames;
static u16 handle;
static int (*alloc_unit)(void*,unsigned,u16*,u32*,u32*);
static int (*dealloc_unit)(void*,u16*);
static int (*wait_video)(void);
struct frame_event {u32 size,physical;};
static int (*submit_video)(struct frame_event);
static int (*judge)(void*,void*,int);
static int (*probe_method)(void*,void*),(*commit_method)(void*,void*);
static u8 descriptor[2][77];
static u8 old_tables[2][8];
/* PAL and NTSC registration records have different enclosing layouts. */
static const u32 table_offsets[2]={0x1cab8,0x1cdb0};

static void log3(const char *event,u32 a,u32 b,u32 c) {
 char s[180];int n=snprintf(s,sizeof(s),"YUY2 %s %08x %08x %08x\n",event,a,b,c);
 int fd=open(LOG,0x441,0644);if(fd>=0){if(n>0 && n<(int)sizeof(s))write(fd,s,n);close(fd);}
}
static void w16(u8*p,unsigned x){p[0]=x;p[1]=x>>8;}
static void w32(u8*p,unsigned x){p[0]=x;p[1]=x>>8;p[2]=x>>16;p[3]=x>>24;}
static int protect(u32 address,unsigned size,int flags) {
 u32 lo=address&~4095u,hi=(address+size+4095u)&~4095u;
 return mprotect((void*)lo,hi-lo,flags);
}
static void flush(u32 a,unsigned n){syscall(0xf0002,a,a+n,0);}
static void jump_thumb(u32 address,void *target) {
 u32 v=(u32)target;u16 x[5];
 unsigned z=v&65535;
 x[0]=0xf240|((z>>12)&15)|(((z>>11)&1)<<10);x[1]=(((z>>8)&7)<<12)|(12<<8)|(z&255);
 z=v>>16;
 x[2]=0xf2c0|((z>>12)&15)|(((z>>11)&1)<<10);x[3]=(((z>>8)&7)<<12)|(12<<8)|(z&255);x[4]=0x4760;
 memcpy((void*)address,x,10);flush(address,10);
}
static int get_base(const char *needle,u32 *base) {
 char *all=malloc(131072);if(!all)return -1;int fd=open("/proc/self/maps",0);if(fd<0){free(all);return -1;}
 int n=0,r;while(n<131071 && (r=read(fd,all+n,131071-n))>0)n+=r;close(fd);if(n<=0){free(all);return -1;}all[n]=0;
 extern char *strstr(const char*,const char*),*strchr(const char*,int);
 char*p=all;
 while(p && *p){char*end=strchr(p,'\n');if(end)*end=0;
  if(strstr(p,needle) && strstr(p,"r-xp") && sscanf(p,"%x",base)==1){free(all);return 0;}
  if(!end)break;p=end+1;
 }free(all);return -1;
}
static int staging_size(unsigned *size,unsigned *address) {
 char *text=malloc(16384);if(!text)return -1;int fd=open("/proc/udm/dmm_units",0);if(fd<0){free(text);return -1;}
 int n=read(fd,text,16383);close(fd);if(n<=0){free(text);return -1;}text[n]=0;
 extern char *strchr(const char*,int);char*p=text;
 while(p && *p){char*end=strchr(p,'\n');if(end)*end=0;
  unsigned h,t,s,a,o,rd,se,re,ad,sz;
  if(sscanf(p,"%x %x %x %x %x %x %x %x %x %x",&h,&t,&s,&a,&o,&rd,&se,&re,&ad,&sz)==10 && t==0x50e){*size=sz;*address=ad;free(text);return 0;}
  if(!end)break;p=end+1;
 }free(text);return -1;
}

/* Free only our own allocation and only after the driver's read-complete query.
 * A failed query pins the source: an uncertain DMA lifetime must never become
 * a use-after-free. Cleanup may be retried on a later start/stop/finish. */
static int cleanup_source(void) {
 if(in_flight){if(wait_video()) {log3("SOURCE_PINNED",physical,capacity,0);return 30;}in_flight=0;}
 if(mapping){if(munmap(mapping,map_len)){log3("UNMAP_FAILED",physical,map_len,0);return 31;}mapping=0;pixels=0;}
 if(handle){int e=dealloc_unit(manager,&handle);if(e){log3("FREE_FAILED",e,handle,0);return 32;}handle=0;}
 manager=0;physical=capacity=map_len=0;pixels=0;return 0;
}
static int prepare_source(void *self) {
 unsigned staging=0,staging_phys=0;
 /* The gadget allocates staging only after Ready connect succeeds. Source
  * memory is owned independently; validate staging at the submission boundary. */
 /* Configured JPEG workspace: type 0x276 -> extent 0x333, 0x320000 bytes.
  * JPEG configuration is bypassed. DMM must grant exclusive ownership: never
  * borrow an existing unit and never substitute audio/staging memory. */
 manager=self;handle=0;physical=capacity=0;
 unsigned err=alloc_unit(self,SOURCE_UNIT,&handle,&physical,&capacity);
 log3("ALLOC_RESULT",err,physical,capacity);
 if(err){if(handle)cleanup_source();return 21;}
 if(!handle || !physical || capacity<FRAME_BYTES || physical+capacity<physical){
  log3("SOURCE_RANGE_REJECTED",physical,capacity,staging_phys);cleanup_source();return 22;
 }
 unsigned delta=physical&4095u;map_len=(delta+FRAME_BYTES+4095u)&~4095u;
 int fd=open("/dev/stream",2);if(fd<0){cleanup_source();return 23;}
 mapping=mmap(0,map_len,3,1,fd,(long)(physical&~4095u));close(fd);
 if(mapping==(void*)-1){mapping=0;cleanup_source();return 24;}
 pixels=(u8*)mapping+delta;
 static const u8 bars[8][3]={{235,128,128},{210,16,146},{170,166,16},{145,54,34},{106,202,222},{81,90,240},{41,240,110},{16,128,128}};
 u8*p=pixels;
 for(unsigned y=0;y<480;y++)for(unsigned x=0;x<640;x+=2){const u8*b=bars[x/80];*p++=b[0];*p++=b[1];*p++=b[0];*p++=b[2];}
 log3("SOURCE_READY",physical,capacity,staging);return 0;
}
static int ensure_source(void *self) {
 if(manager && manager!=self)return 33;
 if(pixels){
  /* Binding alone does not write, free, unmap or submit. A pinned source is
   * immutable until produce obtains a successful driver completion query. */
  manager=self;log3("SOURCE_REBOUND",physical,capacity,in_flight);return 0;
 }
 if(cleanup_source())return 34;
 for(unsigned n=0;n<MAX_RETRIES;n++){
  init_error=prepare_source(self);
  if(!init_error)return 0;
  log3("SOURCE_RETRY",n+1,init_error,handle);
  if(cleanup_source())return 34;
  if(n+1<MAX_RETRIES)usleep(150000);
 }
 log3("SOURCE_EXHAUSTED",MAX_RETRIES,init_error,0);return init_error;
}
static int connect_hook(void *state,void *message) {
 if(!state || !message)return 1;
 void *sm=get_machine(state);if(!sm)return 1;
 void *self=*(void**)((u8*)sm+0x34);if(!self)return 1;
 int e=ensure_source(self);
 if(e){
  /* This is before original Ready::funcConnectCmd saves its async token or
   * enters Starting. Complete the caller directly on the original main thread. */
  u32 reply[2]={0x2003,FAIL_RESULT};u32 token=*(u32*)((u8*)message+4);
  int r=send_complete(token,reply);log3("CONNECT_REJECTED",e,token,r);return r?r:4;
 }
 failures=queue_attempts=recovering=staging_waits=host_waits=0;frames=0;
 return original_connect(state,message);
}
static void request_failure(unsigned error) {
 init_error=error;recovering=1;
 if(queue_attempts<MAX_RETRIES){
  int e=send_event(10);queue_attempts++;log3("FAILURE_EVENT",error,e,queue_attempts);
  if(!e)queue_attempts=MAX_RETRIES;
 }
}
static int start_hook(void *self) {
 int e=ensure_source(self);
 if(e){request_failure(e);return 4;}
 frames=failures=queue_attempts=recovering=staging_waits=host_waits=0;init_error=0;
 return original_start(self);
}
static int detach_source(void *self) {
 if(manager && manager!=self){log3("DETACH_WRONG_MANAGER",(u32)manager,(u32)self,0);return 33;}
 if(!pixels)return cleanup_source();
 int c=0;
 if(in_flight){
  if(wait_video()){c=30;log3("SOURCE_PINNED",physical,capacity,0);}
  else in_flight=0;
 }
 /* original_stop/finish have excluded the old worker. Keep the exclusive
  * source and mapping intact, even when the fd is already closed. The next
  * driver completion check is still mandatory before any pixel mutation. */
 manager=0;
 log3("SOURCE_RETAINED",physical,capacity,in_flight);
 return c;
}
static int stop_hook(void *self) {
 int e=original_stop(self);
 if(!e){int c=detach_source(self);log3("STOP_CLEANUP",c,handle,in_flight);}
 return e;
}
static int finish_hook(void *self) {
 int e=original_finish(self);
 if(!e){int c=detach_source(self);log3("FINISH_CLEANUP",c,handle,in_flight);}
 return e;
}
static int failure_hook(void *state,void *message) {
 (void)message;
 void *sm=get_machine(state);if(!sm)return 1;
 void *self=*(void**)((u8*)sm+0x34);if(!self)return 1;
 /* Invoked by the streaming-main queue after producer returns/releases scalar
  * semaphore. Never call original_stop recursively from the worker thread. */
 int e=original_stop(self);
 int l=sem_lock(*(void**)((u8*)self+0x10));
 if(l){log3("RECOVERY_LOCK_FAILED",l,e,0);return 4;}
 unsigned st=*(u8*)self;
 sem_unlock(*(void**)((u8*)self+0x10));
 if(st!=1){log3("RECOVERY_STOP_FAILED",e,st,0);return 4;}
 int c=detach_source(self);
 u32 token=*(u32*)((u8*)sm+0x18),reply[2]={0x2003,FAIL_RESULT};
 int r=token?send_complete(token,reply):0;
 if(r){log3("RECOVERY_REPLY_FAILED",r,token,c);return 4;}
 *(u32*)((u8*)sm+0x18)=0;
 e=change_state(sm,*(void**)((u8*)sm+8));
 failures=0;log3("RECOVERED_READY",init_error,e,c);return e;
}
static int produce(void *self,void *info) {
 if(!ready || !info)return 4;
 usleep(100000);
 if(recovering){request_failure(init_error);return 4;}
 if(!pixels || manager!=self){request_failure(35);return 4;}
 unsigned staging=0,base=0;
 if(staging_size(&staging,&base) || !base){
  staging_waits++;
  if(staging_waits==1 || staging_waits%5==0)log3("STAGING_WAIT",staging_waits,staging,base);
  /* At most 30 rate-limited polls (nominally 3s); never submit without staging. */
  if(staging_waits>=30)request_failure(38);
  return 4;
 }
 staging_waits=0;
 if(staging/2<FRAME_BYTES+12 || base+staging<base ||
    (physical<base+staging && base<physical+capacity)){
  log3("STAGING_RANGE_REJECTED",base,staging,physical);request_failure(39);return 4;
 }
 /* The common wrapper reduces every negative ioctl result to 1, but libc
  * ioctl preserves the actual errno in this worker's TLS. EBUSY (16) is the
  * kernel's documented both-staging-buffers-pending condition, not a fatal
  * stream error. A missing/slow host can leave it asserted indefinitely.
  * Do not call judge(false) here: the stock notifier independently sends a
  * stop event after ten failures. Preserve the source and retry at 10 Hz. */
 int *ep=__errno_location();*ep=0;
 int err=wait_video(),wait_error=err?*ep:0;
 if(err){
  if(wait_error==16){
   failures=0;
   if(host_waits<0xffffffffu)host_waits++;
   if(host_waits==1 || host_waits%300==0)log3("HOST_WAIT",host_waits,frames,in_flight);
   return 4;
  }
  host_waits=0;
  log3("WAIT_ERROR",wait_error,failures+1,in_flight);judge(self,info,0);
  if(++failures>=MAX_RETRIES)request_failure(36);return 4;
 }
 if(host_waits){log3("HOST_RESUMED",host_waits,frames,in_flight);host_waits=0;}
 in_flight=0;
 u8*p=(u8*)pixels+472*1280;
 for(unsigned y=472;y<480;y++)for(unsigned x=0;x<640;x+=2){unsigned bit=(x/40)&15;u8 v=(frames&(1u<<bit))?235:16;*p++=v;*p++=128;*p++=v;*p++=128;}
 __asm__ volatile("dmb sy" ::: "memory");
 struct frame_event ev={FRAME_BYTES,physical};
 /* Conservatively pin even a rejected submission until a completion query. */
 in_flight=1;err=submit_video(ev);judge(self,info,err==0);
 if(!err){failures=0;frames++;if(frames<=3 || frames%30==0)log3("SUBMITTED",frames,ev.size,ev.physical);}
 else{log3("SUBMIT_FAILED",err,failures+1,0);if(++failures>=MAX_RETRIES)request_failure(37);}
 return err?4:0;
}
static int probe(u32 word,u32 interval) {
 (void)interval;u32 v[2]={(word&65535u)|0x01010000u,INTERVAL_100NS};
 void *g=*(void**)(cb+0x1f108);if(!g)return 1;
 int r=probe_method(g,v);log3("PROBE",v[0],v[1],r);return r<0;
}
static int commit(u32 word,u32 interval) {
 (void)interval;u32 v[2]={(word&65535u)|0x01010000u,INTERVAL_100NS};
 void *g=*(void**)(cb+0x1f108);if(!g)return 1;
 int r=commit_method(g,v);log3("COMMIT",v[0],v[1],r);return r<0;
}
static void make_descriptor(u8*p,const u8*old) {
 static const u8 guid[16]={'Y','U','Y','2',0,0,0x10,0,0x80,0,0,0xaa,0,0x38,0x9b,0x71};
 memcpy(p,old,14);w16(p+4,77);
 u8*f=p+14;memset(f,0,27);f[0]=27;f[1]=0x24;f[2]=4;f[3]=1;f[4]=1;memcpy(f+5,guid,16);f[21]=16;f[22]=1;
 f+=27;memset(f,0,30);f[0]=30;f[1]=0x24;f[2]=5;f[3]=1;w16(f+5,640);w16(f+7,480);
 w32(f+9,FRAME_BYTES*8*10);w32(f+13,FRAME_BYTES*8*10);w32(f+17,FRAME_BYTES);w32(f+21,INTERVAL_100NS);f[25]=1;w32(f+26,INTERVAL_100NS);
 /* SMPTE 170M / BT.601 matrix, BT.709 transfer, matching limited-range bars. */
 f+=30;f[0]=6;f[1]=0x24;f[2]=13;f[3]=4;f[4]=1;f[5]=4;
}

static void *make_trampoline(unsigned i) {
 u8 *p=mmap(0,4096,3,0x22,-1,0);if(p==(void*)-1)return 0;
 memcpy(p,extra_guards[i],10);jump_thumb((u32)p+10,(void*)(sb+extra_offsets[i]+11));
 if(mprotect(p,4096,5)){munmap(p,4096);return 0;}return (void*)((u32)p|1);
}
__attribute__((visibility("default"))) int yuy2_status(void){return ready;}
__attribute__((constructor)) static void install(void) {
 log3("LOAD",FRAME_BYTES,INTERVAL_100NS,0);
 if(get_base("/usr/lib/libInfraStreamingUsb.so",&sb) || get_base("/usr/lib/libInfraUsbCmn.so",&cb)){log3("BASE_FAILED",sb,cb,0);return;}
 /* Entire target files and these byte guards are checked by the host first. */
 static const u8 path_guard[10]={0x2d,0xe9,0xf0,0x43,0xad,0xf5,0x1f,0x7d,0x0,0xaf};
 static const u8 data_guard[10]={0x2d,0xe9,0xf0,0x41,0x8a,0xb0,0x4,0x46,0x0,0xaf};
 static const u8 ctrl_guard[10]={0x80,0xb5,0x84,0xb0,0x0,0xaf,0x87,0xe8,0x3,0x0};
 if(memcmp((void*)(sb+0x8e14),path_guard,10) || memcmp((void*)(sb+0x9618),data_guard,10) || memcmp((void*)(cb+0x12064),ctrl_guard,10) || memcmp((void*)(cb+0x12098),ctrl_guard,10)){log3("CODE_GUARD_FAILED",sb,cb,0);return;}
 for(unsigned i=0;i<2;i++){
  u32*t=(u32*)(cb+table_offsets[i]);u32 expect=cb+(i?0x12625:0x12537);
  if(t[0]!=61 || t[1]!=expect || memcmp((void*)expect,"\x0e\x24\x01\x01\x3d\x00",6)){log3("DESC_GUARD_FAILED",i,t[0],t[1]);return;}
  memcpy(old_tables[i],t,8);make_descriptor(descriptor[i],(void*)expect);
 }
 for(unsigned i=0;i<6;i++)if(memcmp((void*)(sb+extra_offsets[i]),extra_guards[i],10)){log3("LIFECYCLE_GUARD_FAILED",i,0,0);return;}
 void *s=dlopen("/usr/lib/libInfraStreamingUsb.so",2|4),*c=dlopen("/usr/lib/libInfraUsbCmn.so",2|4);
 if(!s || !c){log3("HANDLE_FAILED",(u32)s,(u32)c,0);return;}
 alloc_unit=dlsym(s,"_ZN14VideoEsManager18alloc_video_memoryEjPtPjS1_");
 dealloc_unit=dlsym(s,"_ZN14VideoEsManager20dealloc_video_memoryEPt");
 wait_video=dlsym(c,"_Z16WaitVideoReadCmpv");submit_video=dlsym(c,"_Z17UpdateVideoBufEvt22StreamingVideoDataInfo");
 judge=dlsym(s,"_ZN14VideoEsManager27judge_notify_start_stop_evtEPNS_14VIDEO_MGR_INFOEb");
 probe_method=dlsym(c,"_ZN19CUsbGadgetStreaming13SendProbeInfoEP29usbg_video_probe_commit_ctrls");
 commit_method=dlsym(c,"_ZN19CUsbGadgetStreaming14SendCommitInfoEP29usbg_video_probe_commit_ctrls");
 if(!alloc_unit || !dealloc_unit || !wait_video || !submit_video || !judge || !probe_method || !commit_method){log3("SYMBOL_FAILED",0,0,0);return;}

 sem_lock=dlsym(s,"_ZN3UFW3Sem4LockEv");sem_unlock=dlsym(s,"_ZN3UFW3Sem6UnlockEv");
 send_event=dlsym(s,"SendEvtStreamingMain");send_complete=dlsym(s,"_Z11sendCompMsgjP16ST_MSG_ASYNC_CMP");
 get_machine=dlsym(s,"_ZN12StateMachine5State15getStateMachineEv");
 change_state=dlsym(s,"_ZN12StateMachine11changeStateEPNS_5StateE");
 if(!sem_lock || !sem_unlock || !send_event || !send_complete || !get_machine || !change_state){log3("LIFECYCLE_SYMBOL_FAILED",0,0,0);return;}
 void *tramp[4]={0};
 for(unsigned i=0;i<4;i++)if(!(tramp[i]=make_trampoline(i))){
  for(unsigned j=0;j<i;j++)munmap((void*)((u32)tramp[j]&~1u),4096);
  log3("TRAMPOLINE_FAILED",i,0,0);return;
 }
 original_connect=tramp[0];original_start=tramp[1];original_stop=tramp[2];original_finish=tramp[3];
 /* All affected streaming sites lie on pages 0x7000..0x9000. Protect all
  * before mutation; rollback protection and discard trampolines on failure. */
 if(protect(sb+0x7000,0x3000,7) || protect(cb+0x12064,62,7) || protect(cb+0x1cab0,0x30c,3)){
  protect(sb+0x7000,0x3000,5);protect(cb+0x12064,62,5);
  for(unsigned j=0;j<4;j++)munmap((void*)((u32)tramp[j]&~1u),4096);
  log3("PROTECT_FAILED",0,0,0);return;
 }
 /* No SDF/JPEG configuration is sent: retain existing manager/semaphore lifecycle. */
 u16 no_codec[2]={0x2000,0x4770};memcpy((void*)(sb+0x8e14),no_codec,4);flush(sb+0x8e14,4);
 jump_thumb(sb+0x9618,produce);jump_thumb(cb+0x12064,probe);jump_thumb(cb+0x12098,commit);
 for(unsigned i=0;i<2;i++){u32*t=(u32*)(cb+table_offsets[i]);t[1]=(u32)descriptor[i];t[0]=77;}
 protect(cb+0x12064,62,5);

 void *targets[6]={connect_hook,start_hook,stop_hook,finish_hook,failure_hook,failure_hook};
 for(unsigned i=0;i<6;i++)jump_thumb(sb+extra_offsets[i],targets[i]);
 protect(sb+0x7000,0x3000,5);
 ready=1;log3("INSTALLED_V24",sb,cb,SOURCE_UNIT);
}
