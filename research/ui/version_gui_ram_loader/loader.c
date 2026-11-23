#include "payload.h"
extern int ram_open(const char*,unsigned,unsigned);
extern int ram_read(int,void*,unsigned);
extern int ram_close(int);
extern void *ram_mmap2(void*,unsigned,unsigned,unsigned,int,unsigned);
extern int ram_mprotect(void*,unsigned,unsigned);
extern int ram_munmap(void*,unsigned);
extern int ram_cacheflush(void*,void*,unsigned);
static unsigned word(const unsigned char *p) {
    return (unsigned)p[0]|((unsigned)p[1]<<8)|((unsigned)p[2]<<16)|((unsigned)p[3]<<24);
}
static unsigned crc32(const unsigned char *p,unsigned n) {
    unsigned crc=~0u,i;
    while(n--) {crc^=*p++;for(i=0;i<8;++i)crc=(crc>>1)^((0u-(crc&1u))&0xedb88320u);}
    return ~crc;
}
/* Status 0=returned payload, 1=open, 2=map, 3=read, 4=header,
   5=length/entry, 6=CRC, 7=protect, 8=cache, 9=return/API, 10=unmap. */
unsigned load_payload(unsigned result[2]) {
    static const unsigned char magic[8]={'Z','V','R','A','M','0','0','1'};
    static const char path[]="/log/zve10-ram-loader/payload.bin";
    unsigned char *map;unsigned used=0,attempts=0,body,entry,i,status=3,returned;
    int fd,n;char text[9];unsigned char extra;
    struct ram_api api;
    fd=ram_open(path,0,0);if(fd<0)return 1;
    map=ram_mmap2(0,4096,3,0x22,-1,0);
    if((unsigned)map>=0xfffff001u) {ram_close(fd);return 2;}
    while(used<4096 && attempts++<64) {
        n=ram_read(fd,map+used,4096-used);
        if(n==-4)continue;
        if(n<0)goto done;
        if(n==0)break;
        if((unsigned)n>4096-used)goto done;
        used+=(unsigned)n;
    }
    if(attempts>=64)goto done;
    if(used==4096) {
        n=ram_read(fd,&extra,1);if(n!=0)goto done;
    }
    status=4;
    if(used<32)goto done;
    for(i=0;i<8;++i)if(map[i]!=magic[i])goto done;
    if(word(map+8)!=1 || word(map+12)!=32 || word(map+28)!=RAM_ABI)goto done;
    body=word(map+16);entry=word(map+20);status=5;
    if(body<2 || body>2048 || (body&1) || used!=32+body || entry>=body || (entry&1))goto done;
    status=6;if(crc32(map+32,body)!=word(map+24))goto done;
    /* Root Linux syscall wrappers: never request writable+executable pages. */
    status=7;if(ram_mprotect(map,4096,5)!=0)goto done;
    status=8;if(ram_cacheflush(map+32,map+used,0)!=0)goto done;
    for(i=0;i<9;++i)text[i]=0;
    api.version=RAM_ABI;api.size=sizeof(api);api.text=text;api.capacity=sizeof(text);
    returned=((unsigned(*)(struct ram_api*))((unsigned)(map+32+entry)|1u))(&api);
    status=9;if(returned!=RAM_RETURN || text[8]!=0)goto done;
    for(i=0;i<8 && text[i];++i)
        if((unsigned char)text[i]<32 || (unsigned char)text[i]>126)goto done;
    for(i=0;i<8;++i)((char*)result)[i]=text[i]?text[i]:' ';
    /* NUL ends the payload's display string, including any later tail bytes. */
    {unsigned ended=0;for(i=0;i<8;++i){if(!text[i])ended=1;if(ended)((char*)result)[i]=' ';}}
    status=0;
done:
    ram_close(fd);
    if(ram_munmap(map,4096)!=0 && status==0)status=10;
    return status;
}
