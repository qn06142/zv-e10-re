/* Position-independent user-space payload for the already installed GUI RAM loader. */
#include "payload.h"
static long call3(unsigned n,unsigned a,unsigned b,unsigned c) {
    register unsigned r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c,r7 __asm__("r7")=n;
    __asm__ volatile("svc 0":"+r"(r0):"r"(r1),"r"(r2),"r"(r7):"memory","cc");
    return (int)r0;
}
static long map_module(void) {
    register unsigned r0 __asm__("r0")=0,r1 __asm__("r1")=16384,r2 __asm__("r2")=3,
        r3 __asm__("r3")=0x22,r4 __asm__("r4")=~0u,r5 __asm__("r5")=0,r7 __asm__("r7")=192;
    __asm__ volatile("svc 0":"+r"(r0):"r"(r1),"r"(r2),"r"(r3),"r"(r4),"r"(r5),"r"(r7):"memory","cc");
    return (int)r0;
}
static unsigned result(struct ram_api *api,const char *text) {
    unsigned i;
    if(!api||api->version!=RAM_ABI||api->size!=sizeof(*api)||api->capacity<9)return 0;
    for(i=0;i<8 && text[i];++i)api->text[i]=text[i];
    api->text[i]=0;return RAM_RETURN;
}
static int state_ready(void) {
    static const char path[]="/sys/module/zve10_ram_boot/parameters/state";
    char value[16];int fd,n;
    fd=call3(5,(unsigned)path,0,0);if(fd<0)return -1;
    n=call3(3,fd,(unsigned)value,15);call3(6,fd,0,0);
    if(n<5)return 0;value[n]=0;
    return value[0]=='R'&&value[1]=='E'&&value[2]=='A'&&value[3]=='D'&&value[4]=='Y'&&
        (!value[5]||(value[5]=='\n'&&!value[6]));
}
unsigned payload_entry(struct ram_api *api) {
    static const char path[]="/log/zve10-ram-boot/boot.ko";
    static const char command[]="/sys/module/zve10_ram_boot/parameters/command";
    static const char empty[]="",go[]="GO";
    unsigned char *image;unsigned used=0,attempt=0;int fd,n,rc,ready;
    ready=state_ready();
    if(ready==1) {
        /* A separate confirmed GUI invocation is required after module staging. */
        call3(36,0,0,0);
        fd=call3(5,(unsigned)command,1,0);if(fd<0)return result(api,"GO OPEN");
        n=call3(4,fd,(unsigned)go,2);call3(6,fd,0,0);
        return result(api,n==2?"BOOTING":"GO ERR");
    }
    if(ready==0)return result(api,"NOT RDY");
    fd=call3(5,(unsigned)path,0,0);if(fd<0)return result(api,"NO MOD");
    image=(void*)map_module();
    if((unsigned)image>=0xfffff001u){call3(6,fd,0,0);return result(api,"MAP ERR");}
    while(used<16384 && attempt++<64) {
        n=call3(3,fd,(unsigned)(image+used),16384-used);
        if(n==-4)continue;
        if(n<0){used=0;break;}
        if(!n)break;used+=(unsigned)n;
    }
    call3(6,fd,0,0);
    if(attempt>=64||used<52||used==16384||image[0]!=127||image[1]!='E'||image[2]!='L'||image[3]!='F'||
       image[4]!=1||image[5]!=1||image[16]!=1||image[17]!=0||image[18]!=40||image[19]!=0) {
        call3(91,(unsigned)image,16384,0);return result(api,"MOD BAD");
    }
    rc=call3(128,(unsigned)image,used,(unsigned)empty);
    call3(91,(unsigned)image,16384,0);
    if(rc)return result(api,"MOD ERR");
    return result(api,state_ready()==1?"BOOT RDY":"NOT RDY");
}
