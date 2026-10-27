/* Force ptrace writes for ARM instruction-cache synchronization. */
typedef unsigned int u32;
extern int open(const char*,int,...),close(int),read(int,void*,unsigned),write(int,const void*,unsigned),waitpid(int,int*,int);
extern long lseek(int,long,int),ptrace(int,int,void*,void*);
extern unsigned long strtoul(const char*,char**,int);
extern int printf(const char*,...),memcmp(const void*,const void*,unsigned),snprintf(char*,unsigned,const char*,...);
extern int *__errno_location(void);
static unsigned char before[4096],after[4096],check[4096];
static int file_read(const char *p,void *b){int f=open(p,0);if(f<0)return -1;int n=read(f,b,4096);close(f);return n;}
int main(int argc,char **argv){
 if(argc==1){printf("CHECKED_MEMPATCH_ARM_READY\n");return 0;}
 if(argc!=6){printf("usage: checked_mempatch PID ADDRESS_HEX BEFORE AFTER\n");return 1;}
 int pid=strtoul(argv[1],0,10);u32 addr=strtoul(argv[2],0,16);
 int n=file_read(argv[3],before),m=file_read(argv[4],after);
 /* argv[5] is a mandatory literal arm-volatile acknowledgement. */
 extern int strcmp(const char*,const char*);
 if(strcmp(argv[5],"arm-volatile") || n<1 || n!=m || n>4096 || addr<65536 || addr+n<addr)return 2;
 char p[80];snprintf(p,sizeof(p),"/proc/%d/mem",pid);
 int fd=open(p,0);if(fd<0)return 3;
 if(lseek(fd,addr,0)!=(long)addr || read(fd,check,n)!=n || memcmp(check,before,n)){printf("PRECONDITION_MISMATCH %08x\n",addr);close(fd);return 4;}
 if(ptrace(16,pid,0,0)<0){printf("ATTACH_FAILED %d\n",*__errno_location());close(fd);return 5;}
 int status=0;if(waitpid(pid,&status,0)!=pid){ptrace(17,pid,0,0);close(fd);return 6;}
 int bad=0;u32 lo=addr&~3u,hi=(addr+n+3)&~3u;
 for(u32 at=lo;at<hi;at+=4){
  *__errno_location()=0;u32 word=ptrace(2,pid,(void*)at,0);
  if(*__errno_location()){bad=1;break;}
  unsigned char *b=(unsigned char*)&word;
  for(unsigned j=0;j<4;j++)if(at+j>=addr && at+j<addr+n)b[j]=after[at+j-addr];
  if(ptrace(5,pid,(void*)at,(void*)word)<0){bad=1;break;}
 }
 if(bad){
  /* Restore every original byte while still attached. */
  for(u32 at=lo;at<hi;at+=4){u32 word=ptrace(2,pid,(void*)at,0);unsigned char *b=(unsigned char*)&word;
   for(unsigned j=0;j<4;j++)if(at+j>=addr && at+j<addr+n)b[j]=before[at+j-addr];ptrace(5,pid,(void*)at,(void*)word);}
 }
 ptrace(17,pid,0,0);
 int ok=!bad && lseek(fd,addr,0)==(long)addr && read(fd,check,n)==n && !memcmp(check,after,n);close(fd);
 printf("%s %08x %d\n",ok?"PATCH_VERIFIED":"PATCH_FAILED",addr,n);return ok?0:7;
}
