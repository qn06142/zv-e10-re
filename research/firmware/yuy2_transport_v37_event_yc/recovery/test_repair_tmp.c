#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
static unsigned char original[12582912],device[12582912];
static unsigned pos[5];static int mounted_tmp=1,mounted_etc=1,readonly,mode,writes,flushes,fsyncs,partial_done;
static char mounts_text[300];
static int mo(const char*p,int f,...){
 if(!strcmp(p,"/dev/nflasha10")){if(f==2)assert(!mounted_tmp && !mounted_etc);pos[1]=0;return 1;}
 if(strstr(p,"tmp-volume-preflash.bin")){pos[2]=0;return 2;}
 if(!strcmp(p,"/proc/mounts")){
  mounts_text[0]=0;if(mounted_tmp)strcat(mounts_text,"/dev/nflasha10 /tmp vfat rw 0 0\n");
  if(mounted_etc)strcat(mounts_text,"/dev/nflasha10 /etc vfat rw 0 0\n");strcat(mounts_text,"rootfs / rootfs rw 0 0\n");pos[3]=0;return 3;
 }assert(0);return -1;
}
static int mc(int f){(void)f;return 0;}
static int mr(int f,void*p,unsigned n){
 const unsigned char*src=f==1?device:f==2?original:(unsigned char*)mounts_text;unsigned len=f==3?(unsigned)strlen(mounts_text):12582912;
 if(pos[f]+n>len)n=len-pos[f];memcpy(p,src+pos[f],n);pos[f]+=n;return (int)n;
}
static int mw(int f,const void*p,unsigned n){
 assert(f==1 && !mounted_tmp && !mounted_etc && readonly);writes++;
 if(mode==5 && !partial_done){n=512;partial_done=1;}
 else if(mode==5 && partial_done==1){partial_done=2;return -1;}
 memcpy(device+pos[f],p,n);pos[f]+=n;return (int)n;
}
static long ml(int f,long off,int whence){assert(whence==0 && off>=0);pos[f]=(unsigned)off;return off;}
static int mm(const char*s,const char*t,const char*f,unsigned long flags,const void*o){
 (void)s;(void)f;(void)o;
 if(flags&32){
  if(mode==8 && (flags&1))return -1;
  readonly=(flags&1)!=0;return 0;
 }
 if(!strcmp(t,"/tmp"))mounted_tmp=1;else if(!strcmp(t,"/etc"))mounted_etc=1;else assert(0);return 0;
}
static int mu(const char*t,int f){
 assert(f==0 && readonly);
 if(!strcmp(t,"/etc")){if(mode==2)return -1;mounted_etc=0;}
 else if(!strcmp(t,"/tmp")){if(mode==3)return -1;mounted_tmp=0;if(mode==4)device[10000]^=1;}
 else assert(0);return 0;
}
static int mi(int f,unsigned long req,...){assert(f==1 && req==0x1261 && !mounted_tmp && !mounted_etc);flushes++;if(mode==9 && flushes==1)return -1;return 0;}
static int mf(int f){assert(f==1);fsyncs++;if(mode==7 && fsyncs==1)return -1;if(mode==6 && fsyncs==1)device[700]^=1;return 0;}
static void ms(void){}
#define HOST_TEST
#define open mo
#define close mc
#define read mr
#define write mw
#define lseek ml
#define mount mm
#define umount2 mu
#define ioctl mi
#define fsync mf
#define sync ms
#define main repair_main
#include "repair_tmp.c"
#undef main
int main(int argc,char**argv){
 assert(argc==3);mode=atoi(argv[2]);FILE*f=fopen(argv[1],"rb");assert(f);assert(fread(original,1,sizeof(original),f)==sizeof(original));fclose(f);memcpy(device,original,sizeof(device));
 if(mode==1)device[10000]^=1;
 char *args[]={"repair",mode==10?"--check":"--apply",0};int rc=repair_main(2,args);
 assert(mounted_tmp && mounted_etc && !readonly);
 if(mode==0){assert(rc==0 && writes==1);assert(!memcmp(device,original,512));assert(!memcmp(device+512,new_fat,1536));assert(!memcmp(device+2048,original+2048,sizeof(device)-2048));}
 else if(mode==10){assert(rc==0 && writes==0 && !memcmp(device,original,sizeof(device)));}
 else{
  assert(rc!=0);
  if(mode==1 || mode==4){assert(writes==0);device[10000]^=1;}
  assert(!memcmp(device,original,sizeof(device)));
  if(mode==5 || mode==6 || mode==7)assert(writes>=2);else assert(writes==0);
 }
 printf("PASS_REPAIR_CASE_%d\n",mode);return 0;
}
