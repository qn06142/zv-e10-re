#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "capture.c"
#define open io_open
#define close io_close
#define write io_write
#define fsync io_fsync
#define mkdir io_mkdir
#define getpagesize io_pagesize
#define mmap io_mmap
#define munmap io_munmap
#define __errno_location io_errno
#include "runtime.c"
static unsigned char ram[70000],files[3][70000];
static unsigned lengths[3],saves,forwarded,writes,closes,unmaps;
static int err,fail_open,fail_write,fail_sync,eintr_once,zero_once;
int *io_errno(void){return &err;}
int io_open(const char*p,int flags,...){
 if(!strcmp(p,"/dev/mem"))return 3;
 if(flags!=(1|64|128|131072)){fprintf(stderr,"badflags\n");exit(3);}
 if(fail_open){err=17;return -1;}
 if(!strcmp(p,meta))return 10;
 if(!strcmp(p,bin))return 11;
 if(!strcmp(p,done))return 12;
 exit(4);
}
int io_close(int fd){(void)fd;closes++;return 0;}
int io_write(int fd,const void*p,unsigned n){
 writes++;
 if(eintr_once){eintr_once=0;err=4;return -1;}
 if(fail_write&&fd==11){err=5;return -1;}
 if(zero_once){zero_once=0;return 0;}
 if(n>13)n=13;
 unsigned i=(unsigned)(fd-10);if(i>2||lengths[i]+n>sizeof(files[i]))exit(5);
 memcpy(files[i]+lengths[i],p,n);lengths[i]+=n;return n;
}
int io_fsync(int fd){return fail_sync&&fd==11?-1:0;}
int io_mkdir(const char*p,unsigned m){(void)p;(void)m;err=17;return -1;}
int io_pagesize(void){return 4096;}
void *io_mmap(void*p,unsigned n,int prot,int flags,int fd,long off){
 (void)p;if(n>sizeof(ram)||prot!=1||flags!=1||fd!=3||off!=0x20000000)exit(6);return ram;
}
int io_munmap(void*p,unsigned n){(void)n;if(p!=ram)exit(7);unmaps++;return 0;}
static int fallback(void*self,const raw_packet*p){(void)self;(void)p;forwarded++;return 77;}
static void check(int x){if(!x){fprintf(stderr,"check failed\n");exit(2);}}
static void reset(void){state=selected=0;original=0;memset(&ops,0,sizeof(ops));memset(lengths,0,sizeof(lengths));forwarded=saves=writes=closes=unmaps=0;err=fail_open=fail_write=fail_sync=eintr_once=zero_once=0;}
int main(void){
 for(unsigned i=0;i<sizeof(ram);i++)ram[i]=(unsigned char)(i*37+i/256);
 raw_packet p={1,0x701,0x20000003,10037,7,0,0,0,0,0};unsigned cases=0;
 for(int mode=0;mode<6;mode++){
  reset();check(raw_v01_bind(fallback)==0);check(raw_v01_arm()==0);
  fail_open=mode==1;fail_write=mode==2;fail_sync=mode==3;eintr_once=mode==4;zero_once=mode==5;
  int ok=raw_v01_dispatch(0,&p);check(ok==(mode==0||mode==4));
  if(ok){check(lengths[0]==24&&lengths[1]==p.bytes&&lengths[2]==24);check(!memcmp(files[0],&p,24));check(!memcmp(files[1],ram+3,p.bytes));check(!memcmp(files[2],&p,24));check(raw_v01_status()==4);}
  else{check(lengths[2]==0);check(raw_v01_status()==5);}
  check(unmaps==1&&raw_v01_arm()!=0);cases++;
 }
 reset();check(raw_v01_bind(fallback)==0);check(raw_v01_dispatch(0,&p)==77);check(forwarded==1&&!writes);cases++;
 reset();check(raw_v01_bind(fallback)==0);check(raw_v01_arm()==0);p.mode=8;check(raw_v01_dispatch(0,&p)==77&&!writes);cases++;p.mode=0;
 reset();check(raw_v01_bind(fallback)==0);check(raw_v01_arm()==0);p.tag=2;check(raw_v01_dispatch(0,&p)==77&&!writes);cases++;p.tag=0x701;
 for(int i=0;i<4;i++){
  reset();check(raw_v01_bind(fallback)==0);check(raw_v01_arm()==0);
  raw_packet q=p;if(i==0)q.address=0;if(i==1)q.bytes=0;if(i==2)q.bytes=64u*1024u*1024u+1;if(i==3){q.address=0x3fffffff;q.bytes=2;}
  check(raw_v01_dispatch(0,&q)==0&&raw_v01_status()==5&&!writes&&!unmaps);cases++;
 }
 printf("Passed %u receiver adapter cases; real copy compared byte-for-byte.\n",cases);return 0;
}
