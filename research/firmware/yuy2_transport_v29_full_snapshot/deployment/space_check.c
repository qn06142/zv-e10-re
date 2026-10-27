extern long syscall(long,...);
extern int printf(const char*,...),open(const char*,int,...),close(int),read(int,void*,unsigned),write(int,const void*,unsigned),unlink(const char*),memcmp(const void*,const void*,unsigned);
static unsigned char zero[4096],check[4096];
int main(void){
 const char *paths[3]={"/usr","/log","/tmp"};
 for(unsigned i=0;i<3;i++){
  unsigned s[32]={0};long rc=syscall(99,paths[i],s);
  if(rc || !s[1] || s[3]>s[2] || s[4]>s[2])return 1;
  unsigned long long bytes=(unsigned long long)s[1]*s[4];printf("V28_SPACE %s available_bytes=%llu\n",paths[i],bytes);
  if(bytes<(i==2?2097152ull:8388608ull))return 2;
 }
 const char *p="/tmp/v28-writecheck.bin";int fd=open(p,0xc1,0600);if(fd<0)return 3;
 int good=write(fd,zero,4096)==4096;close(fd);
 if(good){fd=open(p,0);if(fd<0)good=0;else{good=read(fd,check,4096)==4096 && !memcmp(check,zero,4096);close(fd);}}
 int clean=unlink(p)==0;if(!good || !clean)return 4;
 printf("V28_TMP_WRITE_READBACK_OK\n");return 0;
}
