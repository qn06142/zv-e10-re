extern long syscall(long,...);
extern int printf(const char*,...);
int main(void){const char *paths[2]={"/usr","/log"};for(unsigned i=0;i<2;i++){unsigned s[32]={0};long rc=syscall(99,paths[i],s);if(rc || !s[1] || s[3]>s[2] || s[4]>s[2])return 1;unsigned long long bytes=(unsigned long long)s[1]*s[4];printf("V27_SPACE %s available_bytes=%llu\n",paths[i],bytes);if(bytes<8388608ull)return 2;}return 0;}
