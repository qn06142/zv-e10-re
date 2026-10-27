/* Loader isolation only: no YC hooks, Sony API, frame access or constructors. */
extern int open(const char *,int,...),close(int),write(int,const void *,unsigned);
__attribute__((visibility("default"))) int yc_observer_activate(void) {
 static unsigned done;
 if(done)return 1;
 const char marker[]="YC_V3_LOADER_ACTIVATION_OK\n";
 int fd=open("/log/yc_observer/runtime-v3.log",0x441,0644);
 if(fd<0)return 0;
 int ok=write(fd,marker,sizeof(marker)-1)==sizeof(marker)-1;
 close(fd);if(ok)done=1;return ok;
}
