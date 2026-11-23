/* Host hardware-boundary fixture. Sony methods are mocked here; original ARM
 * request/geometry instructions are checked separately by Unicorn oracles. */
#define open fake_open
#define close fake_close
#define read fake_read
#define write fake_write
#define mmap fake_mmap
#define munmap fake_munmap
#define usleep fake_sleep
#define dlopen fake_dlopen
#define dlsym fake_dlsym
#define pthread_create fake_create
#define pthread_detach fake_detach
#include "vga_resize.c"
extern int puts(const char *);
extern size_t strlen(const char *);
extern char *strstr(const char *,const char *);
extern void abort(void);
#define CHECK(x) do{if(!(x)){puts("FAILED: " #x);abort();}}while(0)
static unsigned char sm[4096],spix[2073600],dm[4096],dpix[VGA_BYTES],got[VGA_BYTES],im[4096];
static unsigned shared[256],opened[256],calls,calls_h20,read_at,mode,consumed,resize_calls,source_maps,devopens,log_used,acquisition_hot,log_opens;
static char diagnostic_log[131072];
static unsigned max_write,fail_write_after,zero_writes,write_calls;
static void w16(unsigned char*p,unsigned v){p[0]=v;p[1]=v>>8;}
static void w32(unsigned char*p,unsigned v){w16(p,v);w16(p+2,v>>16);}
static void reply_ok(void *raw,unsigned command,unsigned h){unsigned char *r=raw;memset(r,0,24);w16(r,command|0x8000);w16(r+4,h);w16(r+6,0x611a);}
static void sds(unsigned char *p,unsigned type,unsigned handle,unsigned w,unsigned h,unsigned comp){
 memset(p,0,4096);memcpy(p,"SSYC",4);w32(p+8,1);w32(p+12,2);w32(p+16,32);
 memcpy(p+32,"ETRY",4);w32(p+44,64);w32(p+48,60);w32(p+52,128);memcpy(p+128,"ETRY",4);w32(p+132,1);w32(p+140,160);w32(p+144,6);
 unsigned char *m=p+64;m[0]=1;w32(m+4,type);w16(m+8,handle);
 w16(m+0x18,w);w16(m+0x1a,h);w16(m+0x20,w);w16(m+0x22,h);w16(m+0x28,w);w16(m+0x2a,h);m[0x2f]=comp;m[0x30]=1;m[0x31]=1;m[0x32]=2;m[0x33]=1;
}
int fake_open(const char *path,int flags,...){(void)flags;
 if(!memcmp(path,"/proc/udm/dmm_units",19)){read_at=0;return 5;}
 if(!memcmp(path,"/dev/stream",12)){devopens++;if(mode==15 && devopens==3)return -1;return 6;}
 if(!memcmp(path,"/log/",5)){if(!fault)CHECK(!acquisition_hot);log_opens++;return flags==0x441?7:8;}
 return -1;
}
int fake_close(int fd){(void)fd;return 0;}
int fake_read(int fd,void *out,unsigned n){
 const char row[]="000a 000e0b00 0002 01 01 00 01 01 00010000 00001000\n";
 const char two_rows[]="000a 000e0b00 0002 01 01 00 01 01 00010000 00001000\n000b 000e0b00 0002 01 01 00 01 01 00010000 00001000\n";
 if((mode==18 || mode==27 || mode==29) && fd==5 && !read_at){CHECK(n>=sizeof(two_rows));memcpy(out,two_rows,sizeof(two_rows)-1);read_at=1;return sizeof(two_rows)-1;}
 if(fd!=5 || read_at)return 0;CHECK(n>=sizeof(row));memcpy(out,row,sizeof(row)-1);read_at=1;return sizeof(row)-1;
}
int fake_write(int fd,const void *p,unsigned n){
 if(fd==7){
  write_calls++;if(zero_writes)return 0;if(fail_write_after && log_used>=fail_write_after)return -1;
  if(max_write && n>max_write)n=max_write;
  CHECK(log_used+n<sizeof(diagnostic_log));memcpy(diagnostic_log+log_used,p,n);log_used+=n;diagnostic_log[log_used]=0;
  if(mode==33 && strstr(diagnostic_log,"RESIZE_READY"))__atomic_store_n(&shared_stopping,1,__ATOMIC_RELEASE);
 }
 return n;
}
void *fake_mmap(void *p,unsigned n,int prot,int flags,int fd,long phys){
 (void)p;(void)n;(void)flags;CHECK(fd==6);CHECK(prot==1 || (prot==3 && phys==0x500000));
 switch(phys){case 0x10000:source_maps++;if(mode==14 && source_maps==2)return (void *)-1;return sm;case 0x20000:return spix;case 0x300000:return dm;case 0x400000:return dpix;case 0x500000:return im;}return (void *)-1;
}
int fake_munmap(void *p,unsigned n){(void)n;if(mode==38 && p==sm && source_maps>=2)return 1;return 0;}
void *fake_dlopen(const char *s,int flags){(void)s;(void)flags;return 0;}
void *fake_dlsym(void *p,const char *s){(void)p;(void)s;return 0;}
int fake_create(unsigned long *t,const void *a,void *(*fn)(void *),void *p){(void)t;(void)a;(void)fn;(void)p;return 1;}
int fake_detach(unsigned long t){(void)t;return 0;}
static int share_call(void *self,void *r,unsigned type,unsigned short h,unsigned short flags){
 CHECK(self==dmm && !flags && (h==10 || h==11 || h==20 || h==30 || h==40));
 if(h==10 || h==11)acquisition_hot=1;else if(h==20)acquisition_hot=0;
 CHECK(type==(h==20?0x295:h==40?0x220:0xe0b00));memset(r,0,24);
 if(h==20 && (mode==26 || (mode==27 && calls_h20++==0) || mode==28 || (mode==29 && calls_h20++==0) || (mode>=36 && mode<=38))){
  unsigned char *b=r;w16(b,0x8002);w16(b+2,0xfffb);w16(b+4,h);w16(b+6,0x611a);w16(b+10,0xfdfb);w32(b+12,type);
  if(mode==28 || mode==29 || (mode>=36 && mode<=38)){w16(b+2,0xffff);w16(b+10,0xffff);}
  return 0;
 }
 if(h==10 && mode>=17 && mode<=25){
  unsigned char *b=r;w16(b,0x8002);w16(b+2,0xffff);w16(b+4,h);w16(b+6,0x611a);w16(b+10,0xffff);w32(b+12,type);
  if(mode==19)w16(b+6,0x611b);
  if(mode==20)w16(b+4,h+1);
  if(mode==21)w16(b,0x8005);
  if(mode==22)w32(b+12,type+1);
  if(mode==24)w16(b+10,0xfdfb);
  if(mode==25)w32(b+16,0x10000);
  acquisition_hot=0;return mode==23?1:0;
 }
 if(h==10 && mode==9){acquisition_hot=0;return 1;}
 if(h==10 && mode==10){acquisition_hot=0;w16((unsigned char *)r+2,0xff80);w32((unsigned char *)r+4,0x11223344);w32((unsigned char *)r+20,0x55667788);return 0;}
 reply_ok(r,2,h);w32((unsigned char *)r+12,type);shared[h]++;calls++;
 if((mode==31 && h==10) || (mode==32 && h==20))__atomic_store_n(&shared_stopping,1,__ATOMIC_RELEASE);
 return 0;
}
static int open_call(void *self,void *raw,unsigned short h,unsigned short flags,unsigned wait){
 CHECK(self==dmm && shared[h] && !flags && !wait);unsigned char *r=raw;reply_ok(r,5,h);w16(r+8,1);
 if(mode==11 && h==10){w16(r+2,0xff81);return 0;}
 if(mode==12 && h==10)w16(r+8,2);
 unsigned phys=(h==10 || h==11)?0x10000:h==20?0x20000:h==30?0x300000:0x400000;
 unsigned bytes=h==10 || h==11 || h==30?4096:h==20?sizeof(spix):sizeof(dpix);
 if(mode==4 && h==40)bytes=VGA_BYTES-1;
 if(mode==5 && h==20)return 1;
 if(mode==6 && h==20)w16(sm+64+8,21);
 if(mode==7 && h==20)phys=0x40000000u;
 if(mode==13 && h==10)phys=0;
 if(mode==16 && h==10)phys=usb_physical;
 w32(r+16,phys);w32(r+20,bytes);opened[h]++;return 0;
}
static int close_call(void *self,void *r,unsigned short h){CHECK(self==dmm && opened[h]);if((mode==36 && h==10) || (mode==47 && h==40 && resize_calls))return 1;opened[h]--;reply_ok(r,6,h);return 0;}
static int free_call(void *self,void *r,unsigned short h,unsigned short flags){CHECK(self==dmm && shared[h] && !opened[h] && !flags);if((mode==37 && h==10) || (mode==48 && h==10))return 1;shared[h]--;if(h==10 || h==11)acquisition_hot=0;reply_ok(r,4,h);return 0;}
static int alloc_input(void *self,void *raw,unsigned type,unsigned short flags,unsigned wait){
 CHECK(self==dmm && type==0xe0b00 && flags==1 && wait==0xffffffffu);
 unsigned char *r=raw;reply_ok(r,1,50);if(mode==41)__atomic_store_n(&shared_stopping,1,__ATOMIC_RELEASE);w16(r+4,50);w16(r+8,1);w32(r+16,0x500000);w32(r+20,sizeof(im));return 0;
}
static int pair_call(void *self,void *out,unsigned type,void *geometry){
 CHECK(self==allocator && type==0x220 && !geometry);if(mode==40)__atomic_store_n(&shared_stopping,1,__ATOMIC_RELEASE);*(memory_set *)out=(memory_set){30,0,0xe0b00,0x300000,4096};return 0;
}
static void yc_ctor(void *out,const void *ref,unsigned fresh,unsigned cache){
 CHECK(((const memory_set *)ref)->handle==30 && !fresh && !cache);memset(out,0,512);memcpy((unsigned char *)out+0x124,dm+64,60);
}
static void geometry_call(void *out,const void *raw){
 const uint16_t *g=raw;CHECK(g[0]==640 && g[1]==480 && !g[2] && !g[3] && g[4]==640 && g[5]==480 && !g[6] && !g[7] && g[8]==640 && g[9]==480);
 unsigned char *m=(unsigned char *)out+0x124;for(unsigned i=0;i<10;i++)w16(m+0x18+i*2,g[i]);
}
static int store_call(void *out){memcpy(dm+64,(unsigned char *)out+0x124,60);return 0;}
static void yc_dtor(void *p){(void)p;}
static int resize_call(void *self,void *cmp,void *ack,void *raw){
 CHECK(self==sdf && shared[(mode==18 || mode==27 || mode==29)?11:10] && shared[20] && opened[(mode==18 || mode==27 || mode==29)?11:10] && opened[20]);unsigned char *c=raw;
 CHECK(c[0x25]==1 && c[0x1c]==50 && c[0x3c]==30);CHECK(c[0x18]==0 && c[0x19]==0x0b && c[0x1a]==0x0e);
 CHECK(c[0x38]==0 && c[0x39]==0x0b && c[0x3a]==0x0e);resize_calls++;
 sony_yc_metadata captured;CHECK(!sony_yc_sds_decode_image(im,sizeof(im),&captured));CHECK(captured.unit_handle==20);
 /* Producer metadata may change AFTER the owned copy. SDF must not see it. */
 w16(sm+64+8,99);CHECK(!sony_yc_sds_decode_image(im,sizeof(im),&captured));CHECK(captured.unit_handle==20);
 memset(cmp,0,24);memset(ack,0,16);if(mode==2)return 1;
 for(unsigned i=0;i<VGA_BYTES;i++)dpix[i]=(unsigned char)(i*17u+3u);
 if(mode==3)dm[64+0x2f]=1;
 if(mode==43)w32((unsigned char *)ack+8,5);
 if(mode==44)w32((unsigned char *)cmp+8,7);
 if(mode==34)__atomic_store_n(&shared_stopping,1,__ATOMIC_RELEASE);
 return 0;
}
int fake_sleep(unsigned us){(void)us;
 if(mode==50)return 0;
 if(generation){uint32_t seq=0;CHECK(!vga_resize_copy(got,sizeof(got),&seq,usb_physical,staging_physical,staging_capacity));CHECK(seq==1);CHECK(!memcmp(got,dpix,VGA_BYTES));consumed++;}
 __atomic_store_n(&shared_stopping,1,__ATOMIC_RELEASE);return 0;
}
int main(int argc,char **argv){
 if(argc>1)CHECK(sscanf(argv[1],"%u",&mode)==1);
 calls_h20=0;
 w32(dmm+4,0x0035611a);
 sds(sm,0x295,20,1920,1080,1);sds(dm,0x220,40,0,0,0);if(mode==1 || mode==50)sm[0]='X';
 if(mode==49)lock=1;
 usb_physical=0x10000000;usb_capacity=sizeof(got);staging_physical=mode==8?0x20000:0x11000000;staging_capacity=4096;initialized=1;__atomic_store_n(&shared_running,1,__ATOMIC_RELEASE);
 sdk[VG_ALLOC_NEW]=alloc_input;sdk[VG_SHARE]=share_call;sdk[VG_OPEN]=open_call;sdk[VG_CLOSE]=close_call;sdk[VG_FREE]=free_call;sdk[VG_RESIZE]=resize_call;
 obj[VG_ALLOC_PAIR]=pair_call;obj[VG_YC_CTOR]=yc_ctor;obj[VG_GEOMETRY]=geometry_call;obj[VG_STORE]=store_call;obj[VG_YC_DTOR]=yc_dtor;
 if(mode==35)__atomic_store_n(&shared_stopping,1,__ATOMIC_RELEASE);
 if(mode==39)initialized=0;
 worker(0);
 if(mode==0 || mode==18 || mode==27 || mode==29 || mode==45 || mode==46){
  CHECK(!consumed && generation==1 && resize_calls==1 && !fault && !running && shared_captured && !stopping);
  for(unsigned i=0;i<256;i++)CHECK(!shared[i] && !opened[i]);
  uint32_t seq=0;CHECK(!vga_resize_copy(got,sizeof(got),&seq,usb_physical,staging_physical,staging_capacity));CHECK(seq==1 && !memcmp(got,dpix,VGA_BYTES));
  unsigned char original=got[0];published[0]^=255;
  for(unsigned i=0;i<100;i++){CHECK(!vga_resize_copy(got,sizeof(got),&seq,usb_physical,staging_physical,staging_capacity));CHECK(got[0]==original && seq==1 && resize_calls==1 && !running);}
  CHECK(vga_resize_copy(dpix,sizeof(dpix),&seq,usb_physical,staging_physical,staging_capacity)<0);
  CHECK(vga_resize_copy(got,sizeof(got),&seq,usb_physical+4096,staging_physical,staging_capacity)<0);
  CHECK(strstr(diagnostic_log,"SNAPSHOT_READY"));
  vga_resize_stop();CHECK(vga_resize_copy(got,sizeof(got),&seq,usb_physical,staging_physical,staging_capacity)<0);
 }
 if(mode==1 || mode==6){CHECK(!fault && !resize_calls && !generation && !running);for(unsigned i=0;i<256;i++)CHECK(!shared[i] && !opened[i]);}
 if(mode==2 || mode==3 || mode==43 || mode==44){CHECK(fault && !running && !generation && resize_calls==1 && shared[10] && shared[20]);CHECK(vga_resize_copy(got,sizeof(got),&calls,usb_physical,staging_physical,staging_capacity)<0);}
 if(mode==4 || mode==5 || mode==7 || mode==8){CHECK(fault && !running && !resize_calls && !generation);}
 if((mode>=9 && mode<=16) || (mode>=19 && mode<=25)){
  CHECK(fault && !running && !resize_calls && !generation);
  const char *want=(mode<=10 || mode>=19)?"VGA SHARE_FAILED":mode==11?"VGA OPEN_FAILED":mode==12?"VGA OPEN_SITE_REJECTED":"VGA LEASE_MAP_FAILED";
  unsigned found=0;for(unsigned i=0;i+strlen(want)<=log_used;i++)if(!memcmp(diagnostic_log+i,want,strlen(want))){found=1;break;}CHECK(found);
  CHECK(!opened[20] && !shared[20]);
  CHECK(shared[10]==(mode<=10 || mode>=19?0:1));
  if(mode==10){CHECK(strstr(diagnostic_log,"DMM_REPLY_04 11223344 00000000 00000000"));CHECK(strstr(diagnostic_log,"DMM_REPLY_10 00000000 55667788"));}
  if(mode==13)CHECK(strstr(diagnostic_log,"LEASE_MAP_FAILED 0000000a ffffffff"));
  if(mode==14)CHECK(strstr(diagnostic_log,"LEASE_MAP_FAILED 0000000a fffffffa"));
  if(mode==15)CHECK(strstr(diagnostic_log,"LEASE_MAP_FAILED 0000000a fffffffb"));
  if(mode==16)CHECK(strstr(diagnostic_log,"LEASE_MAP_FAILED 0000000a fffffffe"));
 }
 if(mode==17){CHECK(!fault && !running && !generation && !shared[10] && !opened[10]);CHECK(strstr(diagnostic_log,"SOURCE_SHARE_DECLINED"));}
 if(mode==18)CHECK(strstr(diagnostic_log,"SOURCE_SHARE_DECLINED") && strstr(diagnostic_log,"COMPLETE"));
 if(mode==26 || mode==28){CHECK(!fault && !running && !generation && !shared[10] && !opened[10] && !shared[20] && !opened[20]);CHECK(strstr(diagnostic_log,"PIXEL_SHARE_DECLINED"));}
 if(mode==27 || mode==29)CHECK(strstr(diagnostic_log,"PIXEL_SHARE_DECLINED") && strstr(diagnostic_log,"COMPLETE"));
 if(mode>=31 && mode<=35){CHECK(!fault && !generation && !running);for(unsigned i=0;i<256;i++)CHECK(!shared[i] && !opened[i]);CHECK(resize_calls==(mode==34?1:0));}
 if(mode>=36 && mode<=38){CHECK(fault && !running && !generation && !resize_calls && shared[10]==1);CHECK(opened[10]==(mode==37?0:1));}
 if(mode==39)CHECK(fault && !running && !calls && !resize_calls);
 if(mode==40)CHECK(!fault && !running && !calls && !resize_calls);
 if(mode==41){CHECK(!fault && !running && !resize_calls && !generation);for(unsigned i=0;i<256;i++)CHECK(!shared[i] && !opened[i]);}
 if(mode==43)CHECK(strstr(diagnostic_log,"RESIZE_RETURN 00000000 00000005 00000000"));
 if(mode==44)CHECK(strstr(diagnostic_log,"RESIZE_RETURN 00000000 00000000 00000007"));
 if(mode==47 || mode==48){CHECK(fault && !shared_captured && !running && generation==1);CHECK(vga_resize_copy(got,sizeof(got),&calls,usb_physical,staging_physical,staging_capacity)<0);CHECK(!strstr(diagnostic_log,"SNAPSHOT_READY"));}
 if(mode==49)CHECK(fault && !shared_captured && !generation && !running && resize_calls==1);
 if(mode==50)CHECK(!fault && !shared_captured && !generation && !running && !resize_calls && strstr(diagnostic_log,"SOURCE_SEARCH_LIMIT 0000001e"));
 CHECK(stopping && !running);
 puts("PASS VGA worker fixture");return 0;
}

