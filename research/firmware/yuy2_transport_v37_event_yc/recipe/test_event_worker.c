/* Native services mocked; exercise the real continuous worker and ref ledger. */
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
#include <assert.h>
extern int puts(const char *);
static unsigned char sm[4096],spix[2073600],dm[4096],dpix[VGA_BYTES],im[4096],got[VGA_BYTES];
static unsigned refs[256],opens[256],mode,grants,acks,resizes,consumed,dropped,close_calls;
static void w16(unsigned char *p,unsigned v){p[0]=v;p[1]=v>>8;}
static void w32(unsigned char *p,unsigned v){w16(p,v);w16(p+2,v>>16);}
static void reply(void *p,unsigned op,unsigned h){unsigned char *r=p;memset(r,0,24);w16(r,op|0x8000);w16(r+4,h);w16(r+6,0x611a);}
static void make_sds(unsigned char *p,unsigned type,unsigned handle,unsigned width,unsigned height,unsigned comp){
 memset(p,0,4096);memcpy(p,"SSYC",4);w32(p+8,1);w32(p+12,2);w32(p+16,32);
 memcpy(p+32,"ETRY",4);w32(p+44,64);w32(p+48,60);w32(p+52,128);memcpy(p+128,"ETRY",4);w32(p+132,1);w32(p+140,160);w32(p+144,6);
 unsigned char *m=p+64;m[0]=1;w32(m+4,type);w16(m+8,handle);
 w16(m+0x18,width);w16(m+0x1a,height);w16(m+0x20,width);w16(m+0x22,height);w16(m+0x28,width);w16(m+0x2a,height);m[0x2f]=comp;m[0x30]=m[0x31]=m[0x33]=1;m[0x32]=2;
}
int fake_open(const char *s,int flags,...){(void)flags;
 if(!memcmp(s,"/dev/stream",12))return 6;
 if(!memcmp(s,"/log/",5))return 7;
 assert(!"Worker attempted an unapproved file or memory-pool scan");return -1;
}
int fake_close(int fd){(void)fd;return 0;}
int fake_read(int fd,void *p,unsigned n){(void)fd;(void)p;(void)n;assert(0);return -1;}
int fake_write(int fd,const void *p,unsigned n){(void)fd;(void)p;return n;}
void *fake_mmap(void *p,unsigned n,int prot,int flags,int fd,long phys){(void)p;(void)n;(void)prot;(void)flags;assert(fd==6);
 switch(phys){case 0x10000:return sm;case 0x20000:return spix;case 0x300000:return dm;case 0x400000:return dpix;case 0x500000:return im;}assert(0);return (void *)-1;
}
int fake_munmap(void *p,unsigned n){(void)p;(void)n;return 0;}
int fake_sleep(unsigned n){(void)n;return 0;}
void *fake_dlopen(const char *p,int n){(void)p;(void)n;return 0;}
void *fake_dlsym(void *p,const char *s){(void)p;(void)s;return 0;}
int fake_create(unsigned long *t,const void *a,void *(*f)(void *),void *p){(void)t;(void)a;(void)f;(void)p;return -1;}
int fake_detach(unsigned long t){(void)t;return 0;}
static int share_call(void *self,void *p,unsigned type,unsigned short h,unsigned short flags){
 assert(self==dmm && !flags);assert(h==9 || h==30 || h==40); /* Source credits must NEVER be shared speculatively. */
 assert(type==(h==9?0x276:h==30?0xe0b00:0x220));reply(p,2,h);
 if(mode==5 && h==9){w16((unsigned char *)p+2,0xfffb);w16((unsigned char *)p+10,0xfdfb);return 0;}
 w32((unsigned char *)p+12,type);refs[h]++;return 0;
}
static int open_call(void *self,void *p,unsigned short h,unsigned short flags,unsigned wait){
 assert(self==dmm && refs[h] && !flags && !wait);reply(p,5,h);
 if(mode==1 && h==10){w16((unsigned char *)p+2,0xffff);return 0;}
 w16((unsigned char *)p+8,1);w32((unsigned char *)p+16,h==10?0x10000:h==20?0x20000:h==30?0x300000:0x400000);
 w32((unsigned char *)p+20,h==10 || h==30?4096:h==20?sizeof(spix):sizeof(dpix));opens[h]++;return 0;
}
static int close_call(void *self,void *p,unsigned short h){assert(self==dmm && opens[h]);if(mode==3 && h==20)return 1;reply(p,6,h);opens[h]--;return 0;}
static int free_call(void *self,void *p,unsigned short h,unsigned short flags){assert(self==dmm && refs[h] && !opens[h]);assert(flags==(h==10 || h==20?2:0));reply(p,4,h);refs[h]--;return 0;}
static int alloc_input(void *self,void *p,unsigned type,unsigned short flags,unsigned wait){assert(self==dmm && type==0xe0b00 && flags==1 && wait==0xffffffff);reply(p,1,50);w16((unsigned char *)p+8,1);w32((unsigned char *)p+16,0x500000);w32((unsigned char *)p+20,4096);return 0;}
static int pair(void *self,void *out,unsigned type,void *geometry){assert(self==allocator && type==0x220 && !geometry);*(memory_set *)out=(memory_set){30,0,0xe0b00,0x300000,4096};return 0;}
static void yc_ctor(void *out,const void *ref,unsigned a,unsigned b){assert(((const memory_set *)ref)->handle==30 && !a && !b);memset(out,0,512);memcpy((unsigned char *)out+0x124,dm+64,60);}
static void geometry(void *out,const void *raw){const uint16_t *g=raw;for(unsigned n=0;n<10;n++)w16((unsigned char *)out+0x124+0x18+2*n,g[n]);}
static int store(void *p){memcpy(dm+64,(unsigned char *)p+0x124,60);return 0;}
static void yc_dtor(void *p){(void)p;}
static int resize(void *self,void *cmp,void *ack,void *cmd){assert(self==sdf && refs[10] && refs[20] && opens[10] && opens[20]);(void)cmd;
 resizes++;memset(cmp,0,24);memset(ack,0,16);if(mode==2)w32((unsigned char *)cmp+8,7);
 for(unsigned i=0;i<VGA_BYTES;i+=4){dpix[i]=128;dpix[i+1]=(unsigned char)(resizes*20);dpix[i+2]=128;dpix[i+3]=(unsigned char)(resizes*20+1);}
 if(mode==9)__atomic_store_n(&shared_stopping,1,__ATOMIC_RELEASE);return 0;
}
static unsigned is_closed;
int yc_port_init(void *a,void *b,yc_port_log l){(void)a;(void)b;(void)l;return mode==6?-1:0;}
int yc_port_close(void){close_calls++;is_closed=1;return 0;}
int yc_port_is_closed(void){return is_closed;}
int yc_port_complete(void){acks++;return 0;}
int yc_port_next(yc_port_frame *ev,unsigned timeout){(void)timeout;
 if(is_closed)return 2;
 if(available){
  if(mode==7 && dropped<3)dropped++;
  else {uint32_t seq=0;assert(!vga_resize_copy(got,sizeof(got),&seq,usb_physical,staging_physical,staging_capacity,usb_handle));assert(seq==resizes && got[0]==(unsigned char)(resizes*20) && got[1]==128 && got[2]==(unsigned char)(resizes*20+1));consumed++;if(consumed==100)__atomic_store_n(&shared_stopping,1,__ATOMIC_RELEASE);return 1;}
 }
 assert(!refs[10] && !refs[20] && !opens[10] && !opens[20]);refs[10]=refs[20]=1;grants++;*ev=(yc_port_frame){0xe0b00,0,10,0};
 if(mode==8)__atomic_store_n(&shared_stopping,1,__ATOMIC_RELEASE);return 0;
}
int main(int argc,char **argv){if(argc>1)assert(sscanf(argv[1],"%u",&mode)==1);
 make_sds(sm,mode==4?0x280:0x295,20,1920,1080,1);make_sds(dm,0x220,40,0,0,0);w32(dmm+4,0x35611a);initialized=1;
 usb_physical=0x10000000;usb_capacity=VGA_BYTES;staging_physical=0x11000000;staging_capacity=1843200;usb_handle=9;shared_running=1;
 sdk[VG_SHARE]=share_call;sdk[VG_OPEN]=open_call;sdk[VG_CLOSE]=close_call;sdk[VG_FREE]=free_call;sdk[VG_ALLOC_NEW]=alloc_input;sdk[VG_RESIZE]=resize;
 obj[VG_ALLOC_PAIR]=pair;obj[VG_YC_CTOR]=yc_ctor;obj[VG_GEOMETRY]=geometry;obj[VG_STORE]=store;obj[VG_YC_DTOR]=yc_dtor;
 worker(0);assert(!running && stopping);
 if(mode==0 || mode==7){assert(!fault && consumed==100 && resizes==100 && generation==100 && acks==grants && close_calls==1);assert(refs[9]==1);for(unsigned h=10;h<256;h++)assert(!refs[h] && !opens[h]);}
 if(mode==1 || mode==2 || mode==3 || mode==4){assert(fault && !close_calls && refs[10] && refs[20]);}
 if(mode==5)assert(fault && !grants && !resizes && !close_calls);
 if(mode==6)assert(fault && !grants && !resizes);
 if(mode==8 || mode==9){assert(!fault && !generation && acks==1 && grants==1 && !refs[10] && !refs[20] && close_calls==1);}
 puts("PASS event-driven worker: continuous publication and transferred-reference ledger");return 0;
}
