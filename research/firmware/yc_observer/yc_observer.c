/* Passive Linux YC observation. No subscription, DMM open, pixel read or free. */
#include <stdint.h>
#include <stddef.h>
extern int open(const char *,int,...),close(int),write(int,const void *,unsigned);
extern int snprintf(char *,unsigned,const char *,...),strcmp(const char *,const char *);
extern int mprotect(void *,unsigned,int);
extern void *dlopen(const char *,int),*dlsym(void *,const char *);
extern long syscall(long,...);
typedef struct {uint32_t type,offset,vaddr,paddr,filesz,memsz,flags,align;} phdr;
typedef struct {uint32_t address;const char *name;const phdr *headers;uint16_t count;} dl_info;
typedef struct {int32_t tag;uint32_t value;} dyn;
typedef struct {uint32_t offset,info;} rel;
typedef struct {uint32_t name,value,size;uint8_t info,other;uint16_t section;} sym;
extern int dl_iterate_phdr(int (*)(dl_info *,size_t,void *),void *);
#define PATH "/log/yc_observer/runtime-v2.log"
#define GETALL "_ZN35C_DataflowInfra_Entry_ImageSizeInfo11GetData_AllEPN19DataflowInfra_StdYc22PIN_YC_IMAGE_SIZE_INFOE"
#define CTOR "_ZN26C_DataflowInfra_StdData_YCC1Ejjj"
static void (*original_getall)(void *,void *);
static void *(*original_ctor)(void *,uint32_t,uint32_t,uint32_t);
static unsigned active,hooks,meta_count,ctor_count;
static void line(const char *s,int n) {
    if(n<=0 || n>=240)return;
    int fd=open(PATH,0x441,0644);
    if(fd>=0){write(fd,s,n);close(fd);}
}
static void getall_hook(void *entry,void *out) {
    uintptr_t caller=(uintptr_t)__builtin_return_address(0);
    original_getall(entry,out);
    unsigned seq=__sync_add_and_fetch(&meta_count,1);
    if(seq>32 || !out)return;
    char s[240];int n=snprintf(s,sizeof(s),"YC_META %u caller=%08lx tid=%ld bytes=",seq,(unsigned long)caller,syscall(224));
    if(n<0 || n>100)return;
    const uint8_t *b=out;static const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<60;i++){s[n++]=hex[b[i]>>4];s[n++]=hex[b[i]&15];}
    s[n++]='\n';line(s,n);
}
static void *ctor_hook(void *self,uint32_t a,uint32_t b,uint32_t c) {
    uintptr_t caller=(uintptr_t)__builtin_return_address(0);
    void *result=original_ctor(self,a,b,c);
    unsigned seq=__sync_add_and_fetch(&ctor_count,1);
    if(seq<=16){char s[240];int n=snprintf(s,sizeof(s),"YC_CTOR %u caller=%08lx args=%08lx,%08lx,%08lx\n",seq,(unsigned long)caller,(unsigned long)a,(unsigned long)b,(unsigned long)c);line(s,n);}
    return result;
}
static uintptr_t pointer(uint32_t base,uint32_t value){return value<base?base+value:value;}
static void scan_relocations(dl_info *info,uintptr_t table,unsigned bytes,
                             const sym *symbols,const char *strings,unsigned strings_size) {
    if(!table || bytes>8u*1024*1024 || bytes%sizeof(rel))return;
    const rel *r=(const rel *)table;
    for(unsigned i=0;i<bytes/sizeof(rel);i++){
        unsigned type=r[i].info&255,index=r[i].info>>8;
        if((type!=21 && type!=22) || index>100000)continue;
        unsigned off=symbols[index].name;
        if(off>=strings_size)continue;
        const char *name=strings+off;void *hook=0;
        if(!strcmp(name,GETALL))hook=getall_hook;
        else if(!strcmp(name,CTOR))hook=ctor_hook;
        if(!hook)continue;
        uintptr_t address=pointer(info->address,r[i].offset);
        if(address&3)continue;
        unsigned protection=0;
        for(unsigned j=0;j<info->count;j++){
            const phdr *p=&info->headers[j];
            if(p->type==1 && address>=info->address+p->vaddr &&
               address+4<=info->address+p->vaddr+p->memsz){
                protection=(p->flags&4?1:0)|(p->flags&2?2:0)|(p->flags&1?4:0);break;
            }
        }
        /* Only writable data LOADs are eligible. Avoid text and RELRO pages:
         * read /proc maps is unnecessary because we never change protection. */
        if(!(protection&2) || protection&4)continue;
        int relro=0;
        for(unsigned j=0;j<info->count;j++){
            const phdr *p=&info->headers[j];
            if(p->type==0x6474e552 && address>=info->address+p->vaddr &&
               address<info->address+p->vaddr+p->memsz)relro=1;
        }
        if(relro)continue;
        volatile uintptr_t *slot=(volatile uintptr_t *)address;
        if(*slot==(uintptr_t)hook)continue;
        *slot=(uintptr_t)hook;__asm__ volatile("dmb sy" ::: "memory");hooks++;
        char s[240];int n=snprintf(s,sizeof(s),"YC_GOT module=%s slot=%08lx kind=%u\n",info->name?info->name:"",(unsigned long)address,hook==(void *)getall_hook?1:2);line(s,n);
    }
}
static int visit(dl_info *info,size_t bytes,void *arg) {
    (void)bytes;(void)arg;
    if(!info->name || (strcmp(info->name,"/usr/lib/libBizFw.so") && strcmp(info->name,"/usr/lib/libObj.so")))return 0;
    char progress[240];int progress_n=snprintf(progress,sizeof(progress),"YC_SCAN_BEGIN %s base=%08lx\n",info->name,(unsigned long)info->address);line(progress,progress_n);
    dyn *dynamic=0;unsigned maximum=0;
    for(unsigned i=0;i<info->count;i++)if(info->headers[i].type==2){dynamic=(dyn *)(info->address+info->headers[i].vaddr);maximum=info->headers[i].memsz/sizeof(dyn);break;}
    if(!dynamic)return 0;
    uintptr_t symbols=0,strings=0,jumps=0,rels=0;unsigned jump_bytes=0,rel_bytes=0,strings_size=0;
    for(unsigned i=0;i<maximum && dynamic[i].tag;i++){
        unsigned v=dynamic[i].value;
        switch(dynamic[i].tag){case 5:strings=pointer(info->address,v);break;
        case 6:symbols=pointer(info->address,v);break;case 10:strings_size=v;break;
        case 17:rels=pointer(info->address,v);break;case 18:rel_bytes=v;break;
        case 23:jumps=pointer(info->address,v);break;case 2:jump_bytes=v;break;}
    }
    if(symbols && strings && strings_size){
        scan_relocations(info,jumps,jump_bytes,(sym *)symbols,(char *)strings,strings_size);
        scan_relocations(info,rels,rel_bytes,(sym *)symbols,(char *)strings,strings_size);
    }
    return 0;
}
__attribute__((visibility("default"))) int yc_observer_activate(void) {
    if(active)return hooks!=0;
    const char enter[]="YC_ACTIVATE_ENTER_V2\n";line(enter,sizeof(enter)-1);
    void *h=dlopen("/usr/lib/dataflowInfraFramework.so",2|4);
    if(!h)return 0;
    original_getall=dlsym(h,GETALL);original_ctor=dlsym(h,CTOR);
    if(!original_getall || !original_ctor)return 0;
    const char resolved[]="YC_ORIGINALS_RESOLVED_V2\n";line(resolved,sizeof(resolved)-1);
    active=1;dl_iterate_phdr(visit,0);
    char s[240];int n=snprintf(s,sizeof(s),"YC_OBSERVER_ACTIVE hooks=%u originals=%08lx,%08lx\n",hooks,(unsigned long)original_getall,(unsigned long)original_ctor);line(s,n);
    return hooks!=0;
}
