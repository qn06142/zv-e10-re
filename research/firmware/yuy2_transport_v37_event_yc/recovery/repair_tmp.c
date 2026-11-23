/* Guarded FAT12 orphan repair. Never writes while either filesystem alias is mounted.
 * Exact source image, old/new FAT and helper identities must also be checked by caller.
 * --check only compares. --apply requires both ordinary unmounts to succeed. */
#ifndef HOST_TEST
extern int open(const char*,int,...),close(int),read(int,void*,unsigned),write(int,const void*,unsigned);
extern long lseek(int,long,int);
extern int mount(const char*,const char*,const char*,unsigned long,const void*),umount2(const char*,int);
extern int ioctl(int,unsigned long,...),fsync(int),printf(const char*,...),strcmp(const char*,const char*);
extern void sync(void);
extern int memcmp(const void*,const void*,unsigned);
extern char *strstr(const char*,const char*);
extern int *__errno_location(void);
#define LAST_ERROR (*__errno_location())
#else
#define LAST_ERROR 0
#endif
#include "repair_fat_images.h"
#define DIR "/log/yuy2_640_v37vga/"
#define DEVICE "/dev/nflasha10"
#define OPTIONS "fmask=0022,dmask=0022,codepage=cp437,iocharset=ascii,shortname=mixed,posix_attr,avoid_dlink,errors=remount-ro"
#define NORMAL_FLAGS (1024ul|16ul|128ul)
#define VOL_BYTES 12582912u
static unsigned char a[4096],b[4096];
static int tmp_mounted=1,etc_mounted=1,ro_attempted;
static int fullread(int fd,void *v,unsigned n){
 unsigned done=0;while(done<n){int r=read(fd,(unsigned char*)v+done,n-done);if(r<=0)return -1;done+=(unsigned)r;}return 0;
}
static int fullwrite(int fd,const void *v,unsigned n){
 unsigned done=0;while(done<n){int r=write(fd,(const unsigned char*)v+done,n-done);if(r<=0)return -1;done+=(unsigned)r;}return 0;
}
static unsigned fat_entry(const unsigned char*f,unsigned n){
 unsigned o=n+n/2,v=f[o]|((unsigned)f[o+1]<<8);return (n&1?v>>4:v)&4095u;
}
static int validate_fat(void){
 if(memcmp(old_fat,new_fat,3))return -1;
 unsigned freed=0;
 for(unsigned n=2;n<768;n++){
  unsigned old=fat_entry(old_fat,n),new=fat_entry(new_fat,n);int orphan=0;
  for(unsigned i=0;i<434;i++)if(orphan_indices[i]==n)orphan=1;
  if(orphan){if(!old || new)return -1;freed++;}
  else if(old!=new)return -1;
 }
 return freed==434?0:-1;
}
static int aliases(int expected){
 char text[16384];int fd=open("/proc/mounts",0);if(fd<0)return -1;
 int used=0,r;while(used<16383 && (r=read(fd,text+used,16383-used))>0)used+=r;
 close(fd);if(used==16383 || used<=0)return -1;text[used]=0;
 int count=0,t=0,e=0;char*p=text;
 while(*p){char*q=p;while(*q && *q!=10)q++;char end=*q;*q=0;
  if(strstr(p,DEVICE " ")==p){count++;if(strstr(p,DEVICE " /tmp vfat ")==p)t++;else if(strstr(p,DEVICE " /etc vfat ")==p)e++;else return -1;}
  if(!end)break;p=q+1;
 }
 return expected==2?(count==2 && t==1 && e==1?0:-1):(count==0?0:-1);
}
static int compare_volume(int dev,int image,int changed){
 if(lseek(dev,0,0)!=0 || lseek(image,0,0)!=0)return -1;
 for(unsigned off=0;off<VOL_BYTES;off+=sizeof(a)){
  if(fullread(dev,a,sizeof(a)) || fullread(image,b,sizeof(b)))return -1;
  for(unsigned i=0;i<sizeof(a);i++){
   unsigned p=off+i;unsigned char want=changed && p>=512 && p<2048?new_fat[p-512]:b[i];
   if(a[i]!=want){printf("V37_REPAIR_VOLUME_MISMATCH %u\n",p);return -1;}
  }
 }
 return 0;
}
static int write_fat(int fd,const unsigned char *fat){
 if(aliases(0) || lseek(fd,512,0)!=512 || fullwrite(fd,fat,1536) || fsync(fd) || ioctl(fd,0x1261ul,0))return -1;
 if(lseek(fd,512,0)!=512 || fullread(fd,a,1536) || memcmp(a,fat,1536))return -1;
 return 0;
}
static int restore_mounts(void){
 int e=0;
 if(!tmp_mounted){if(mount(DEVICE,"/tmp","vfat",NORMAL_FLAGS,OPTIONS))e=1;else tmp_mounted=1;}
 if(!etc_mounted){if(mount(DEVICE,"/etc","vfat",NORMAL_FLAGS,OPTIONS))e=1;else etc_mounted=1;}
 if(ro_attempted && tmp_mounted && mount(DEVICE,"/tmp","vfat",NORMAL_FLAGS|32ul,OPTIONS))e=1;
 if(ro_attempted && etc_mounted && mount(DEVICE,"/etc","vfat",NORMAL_FLAGS|32ul,OPTIONS))e=1;
 if(e)printf("V37_REPAIR_MOUNT_RECOVERY_REQUIRED\n");return e?-1:0;
}
int main(int argc,char **argv){
 if(argc==2 && (!strcmp(argv[1],"--log-stop") || !strcmp(argv[1],"--log-resume"))){
  /* Exact ioctl constants from original KikiLogGenerator_sus/init_proc.
   * Kernel suspend joins its worker and closes its retained FAT file. */
  int fd=open("/dev/usb/kikilog",2);if(fd<0)return 30;
  unsigned long cmd=!strcmp(argv[1],"--log-stop")?0x80044a20ul:0x80044a21ul;
  int rc=ioctl(fd,cmd,0);printf("V37_LOG_CONTROL %08lx rc=%d errno=%d\n",cmd,rc,LAST_ERROR);close(fd);return rc?31:0;
 }
 int apply=argc==2 && !strcmp(argv[1],"--apply");
 if(argc!=2 || (!apply && strcmp(argv[1],"--check")))return 2;
 if(validate_fat() || aliases(2))return 3;
 int dev=open(DEVICE,0),image=open(DIR "tmp-volume-preflash.bin",0);
 if(dev<0 || image<0)return 4;
 if(compare_volume(dev,image,0)){close(dev);close(image);return 5;}
 if(!apply){printf("V37_REPAIR_DRY_RUN_EXACT_VOLUME_AND_FAT_OK\n");close(dev);close(image);return 0;}
 sync();ro_attempted=1;
 if(mount(DEVICE,"/tmp","vfat",NORMAL_FLAGS|32ul|1ul,OPTIONS)){printf("V37_REPAIR_RO_FAILED errno=%d\n",LAST_ERROR);goto abort;}
 printf("V37_REPAIR_RO_OK\n");
 if(umount2("/etc",0)){printf("V37_REPAIR_UNMOUNT_ETC_FAILED errno=%d\n",LAST_ERROR);goto abort;}etc_mounted=0;
 printf("V37_REPAIR_ETC_UNMOUNTED\n");
 if(umount2("/tmp",0)){printf("V37_REPAIR_UNMOUNT_TMP_FAILED errno=%d\n",LAST_ERROR);goto abort;}tmp_mounted=0;
 printf("V37_REPAIR_TMP_UNMOUNTED\n");
 if(aliases(0)){printf("V37_REPAIR_MOUNT_ALIAS_GUARD_FAILED\n");goto abort;}
 close(dev);dev=open(DEVICE,2);
 if(dev<0){printf("V37_REPAIR_UNMOUNTED_DEVICE_OPEN_FAILED errno=%d\n",LAST_ERROR);goto abort;}
 if(ioctl(dev,0x1261ul,0)){printf("V37_REPAIR_FLUSH_FAILED errno=%d\n",LAST_ERROR);goto abort;}
 if(compare_volume(dev,image,0))goto abort;
 /* Only after both aliases are unmounted and the full original matches. */
 if(lseek(dev,512,0)!=512 || fullread(dev,a,1536) || memcmp(a,old_fat,1536))goto abort;
 printf("V37_REPAIR_BOTH_ALIASES_UNMOUNTED_EXACT_VOLUME_VERIFIED\n");
 if(write_fat(dev,new_fat) || compare_volume(dev,image,1)){
  printf("V37_REPAIR_WRITE_FAILED_RESTORING_OLD_FAT\n");
  if(write_fat(dev,old_fat) || compare_volume(dev,image,0)){
   printf("V37_REPAIR_RAW_RECOVERY_REQUIRED_KEEP_UNMOUNTED\n");close(dev);close(image);return 20;
  }
  printf("V37_REPAIR_OLD_FAT_RESTORED\n");goto abort;
 }
 printf("V37_REPAIR_FAT_READBACK_AND_FULL_VOLUME_VERIFIED\n");
 close(dev);close(image);
 if(restore_mounts() || aliases(2))return 21;
 printf("V37_REPAIR_APPLIED_REMOUNTED_7110656_BYTES_RECLAIMED\n");return 0;
abort:
 close(dev);close(image);restore_mounts();printf("V37_REPAIR_ABORTED\n");return 10;
}
