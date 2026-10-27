#include "raw_live_source.h"
#include <string.h>
#include <stdio.h>
#include <stddef.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"line %d: %s\n",__LINE__,#x); return __LINE__; } } while(0)
typedef struct {
    raw_live_frame f;
    uint8_t p[2][32];
    int acquisitions, releases, maps, unmaps, error_acquire, error_map;
    int error_release, error_unmap, release_fail_count;
    unsigned timeout;
    char order[64]; unsigned order_n;
} fake;
static void record(fake *f, char c) { f->order[f->order_n++] = c; }
static int acquire(void *o,uint32_t t,raw_live_frame *out) {
    fake *f=o;f->acquisitions++;f->timeout=t;record(f,'A');
    if (!f->error_acquire || f->error_acquire == -7) *out=f->f;
    return f->error_acquire;
}
static int release(void *o,uintptr_t token) {
    fake *f=o; if(token!=7) return -99;
    f->releases++;record(f,'R');
    if(f->release_fail_count){f->release_fail_count--;return -7;}
    return f->error_release;
}
static int map(void *o,const raw_live_plane *p,size_t n,raw_live_mapping *out) {
    fake *f=o;f->maps++;record(f,'M');
    if (f->maps==f->error_map) return -3;
    unsigned i=p->physical==f->f.plane[0].physical?0:1;
    out->base=f->p[i];out->data=f->p[i];out->length=n;
    return 0;
}
static int unmap(void *o,raw_live_mapping *m) {
    fake *f=o;(void)m;f->unmaps++;record(f,'U');return f->error_unmap;
}
static raw_live_ops ops={RAW_LIVE_ABI,sizeof(raw_live_ops),acquire,release,map,unmap};
static void setup(fake *f, raw_frame_pixfmt_t format) {
    memset(f,0,sizeof(*f));f->f=(raw_live_frame){.token=7,.sequence=123,.width=4,.height=2,.format=format,.flags=15,
        .plane={{0x1000,32,4},{0x2000,32,4}}};
    if(format==RAW_FRAME_PIXFMT_YUY2)f->f.plane[0].stride=8;
    for(int j=0;j<2;j++)for(int i=0;i<32;i++)f->p[j][i]=(uint8_t)(i+j*60);
}
int main(void) {
    unsigned passed=0;uint8_t dst[20];uint32_t seq=999;fake f;raw_live_source s;
    for(int fmt=1;fmt<=3;fmt++) {
        setup(&f,(raw_frame_pixfmt_t)fmt);s=(raw_live_source){0};memset(dst,0xee,sizeof(dst));
        CHECK(!raw_live_init(&s,&ops,&f,4,2,7));CHECK(!raw_live_fill(&s,dst,16,0x9000,&seq));
        CHECK(seq==123 && f.timeout==7 && f.acquisitions==1 && f.releases==1);
        CHECK(f.maps==(fmt==1?1:2) && f.unmaps==f.maps && !s.leased.token);
        for(int i=16;i<20;i++)CHECK(dst[i]==0xee);
        if(fmt==1)CHECK(!memcmp(dst,f.p[0],16));
        else for(int y=0;y<2;y++)for(int x=0;x<4;x+=2){
            unsigned uv=(fmt==3?0:y)*4+x;unsigned at=y*8+x*2;
            CHECK(dst[at]==f.p[0][y*4+x] && dst[at+1]==f.p[1][uv]);
            CHECK(dst[at+2]==f.p[0][y*4+x+1] && dst[at+3]==f.p[1][uv+1]);
        }
        CHECK(!raw_live_shutdown(&s));passed++;
    }
    /* Invalid metadata is rejected before mapping or pixel modification. */
    for(int bad=0;bad<11;bad++) {
        setup(&f,RAW_FRAME_PIXFMT_NV16);s=(raw_live_source){0};memset(dst,0xee,sizeof(dst));
        CHECK(!raw_live_init(&s,&ops,&f,4,2,10));uint32_t phys=0x9000;
        switch(bad){
        case 0:f.f.flags=0;break;case 1:f.f.width=6;break;
        case 2:f.f.format=RAW_FRAME_PIXFMT_UNKNOWN;break;
        case 3:f.f.plane[0].stride=3;break;case 4:f.f.plane[1].bytes=1;break;
        case 5:f.f.plane[0].physical=0xfffffffcu;break;
        case 6:f.f.plane[1].physical=0x1000;break;
        case 7:phys=0x1000;break;case 8:f.f.plane[0].stride=SIZE_MAX;break;
        case 9:f.f.plane[0].physical=0;break;case 10:f.f.token=0;break;
        }
        CHECK(raw_live_fill(&s,dst,16,phys,&seq)<0);CHECK(!f.maps);
        CHECK(f.releases==(bad==10?0:1));for(int i=0;i<20;i++)CHECK(dst[i]==0xee);passed++;
    }
    for(int fail=1;fail<=2;fail++) {
        setup(&f,RAW_FRAME_PIXFMT_NV16);s=(raw_live_source){0};f.error_map=fail;
        CHECK(!raw_live_init(&s,&ops,&f,4,2,10));CHECK(raw_live_fill(&s,dst,16,0x9000,&seq)==-3);
        CHECK(f.releases==1 && f.unmaps==fail-1 && !s.leased.token);passed++;
    }
    setup(&f,RAW_FRAME_PIXFMT_YUY2);s=(raw_live_source){0};f.error_release=-7;
    CHECK(!raw_live_init(&s,&ops,&f,4,2,10));CHECK(raw_live_fill(&s,dst,16,0x9000,&seq)==-7);
    CHECK(s.leased.token==7 && f.unmaps==1);
    CHECK(raw_live_fill(&s,dst,16,0x9000,&seq)==-7 && f.acquisitions==1);
    CHECK(raw_live_shutdown(&s)==-7 && s.initialized);
    f.error_release=0;CHECK(!raw_live_shutdown(&s) && !s.initialized);passed++;
    setup(&f,RAW_FRAME_PIXFMT_NV16);s=(raw_live_source){0};f.error_unmap=-7;
    CHECK(!raw_live_init(&s,&ops,&f,4,2,10));CHECK(raw_live_fill(&s,dst,16,0x9000,&seq)==-7);
    CHECK(f.releases==0 && s.leased.token==7);
    CHECK(raw_live_fill(&s,dst,16,0x9000,&seq)==-7 && f.acquisitions==1);
    f.error_unmap=0;CHECK(!raw_live_shutdown(&s) && f.releases==1);passed++;
    for(int error=-7;error<=-4;error+=3) {
        setup(&f,RAW_FRAME_PIXFMT_YUY2);s=(raw_live_source){0};f.error_acquire=error;
        CHECK(!raw_live_init(&s,&ops,&f,4,2,10));CHECK(raw_live_fill(&s,dst,16,0x9000,&seq)==error);
        CHECK(f.maps==0 && f.releases==(error==-7?1:0));passed++;
    }
    setup(&f,RAW_FRAME_PIXFMT_YUY2);s=(raw_live_source){0};
    CHECK(raw_live_init(&s,&ops,&f,4,2,11)==-1 && raw_live_init(&s,&ops,&f,4,2,0)==-1);passed++;
    CHECK(raw_live_init(&s,&ops,&f,3,2,10)==-1);passed++;
    CHECK(!raw_live_init(&s,&ops,&f,4,2,10));CHECK(raw_live_init(&s,&ops,&f,4,2,10)==-6);passed++;
    CHECK(raw_live_fill(&s,dst,15,0x9000,&seq)==-1 && f.acquisitions==0);passed++;
    CHECK(raw_live_fill(&s,dst,16,0xfffffffcu,&seq)==-1 && f.acquisitions==0);passed++;
    setup(&f,RAW_FRAME_PIXFMT_YUY2);s=(raw_live_source){0};
    CHECK(raw_live_fill(&s,dst,16,0x9000,&seq)==-2);passed++;

    /* Test real compiled struct PIN_YC_IMAGE_SIZE_INFO (60 bytes) and offsets */
    CHECK(sizeof(struct PIN_YC_IMAGE_SIZE_INFO) == 60);
    CHECK(offsetof(struct PIN_YC_IMAGE_SIZE_INFO, image_attach) == 0x00);
    CHECK(offsetof(struct PIN_YC_IMAGE_SIZE_INFO, unit_type) == 0x04);
    CHECK(offsetof(struct PIN_YC_IMAGE_SIZE_INFO, unit_handle) == 0x08);
    CHECK(offsetof(struct PIN_YC_IMAGE_SIZE_INFO, unit_data_offset) == 0x0c);
    CHECK(offsetof(struct PIN_YC_IMAGE_SIZE_INFO, record_size_x) == 0x14);
    CHECK(offsetof(struct PIN_YC_IMAGE_SIZE_INFO, valid_size_x) == 0x20);
    CHECK(offsetof(struct PIN_YC_IMAGE_SIZE_INFO, target_size_x) == 0x28);
    CHECK(offsetof(struct PIN_YC_IMAGE_SIZE_INFO, data_placement) == 0x31);
    CHECK(offsetof(struct PIN_YC_IMAGE_SIZE_INFO, strip_width) == 0x34);
    CHECK(offsetof(struct PIN_YC_IMAGE_SIZE_INFO, cam_freq_char_h) == 0x38);
    passed++;

    /* Test real compiled struct PIN_YC_YC_STATE_INFO (6 bytes) and offsets */
    CHECK(sizeof(struct PIN_YC_YC_STATE_INFO) == 6);
    CHECK(offsetof(struct PIN_YC_YC_STATE_INFO, y_range) == 0x00);
    CHECK(offsetof(struct PIN_YC_YC_STATE_INFO, colorimetry) == 0x01);
    CHECK(offsetof(struct PIN_YC_YC_STATE_INFO, chroma_phase) == 0x02);
    CHECK(offsetof(struct PIN_YC_YC_STATE_INFO, scanline) == 0x03);
    CHECK(offsetof(struct PIN_YC_YC_STATE_INFO, copy_protection) == 0x04);
    CHECK(offsetof(struct PIN_YC_YC_STATE_INFO, author) == 0x05);
    passed++;

    /* Test real compiled struct PIN_PROPERTY (16 bytes) and offsets */
    CHECK(sizeof(PIN_PROPERTY) == 16);
    CHECK(offsetof(PIN_PROPERTY, subsystem_id) == 0x00);
    CHECK(offsetof(PIN_PROPERTY, unit_id) == 0x04);
    CHECK(offsetof(PIN_PROPERTY, pin_id) == 0x08);
    CHECK(offsetof(PIN_PROPERTY, flags_queue_id) == 0x0c);
    passed++;

    /* Test real compiled struct dmm_extent_t (40 bytes) and offsets */
    CHECK(sizeof(dmm_extent_t) == 40);
    CHECK(offsetof(dmm_extent_t, unit_handle) == 0x00);
    CHECK(offsetof(dmm_extent_t, num_planes) == 0x02);
    CHECK(offsetof(dmm_extent_t, total_size) == 0x04);
    CHECK(offsetof(dmm_extent_t, planes[0].phy_addr) == 0x08);
    CHECK(offsetof(dmm_extent_t, planes[0].size_or_stride) == 0x0c);
    CHECK(offsetof(dmm_extent_t, planes[1].phy_addr) == 0x10);
    CHECK(offsetof(dmm_extent_t, planes[1].size_or_stride) == 0x14);
    passed++;

    /* Fallback on acquire error/timeout: verify synthetic frame generation into workspace */
    setup(&f, RAW_FRAME_PIXFMT_YUY2); s = (raw_live_source){0};
    f.error_acquire = RAW_FRAME_ERR_TIMEOUT;
    CHECK(!raw_live_init(&s, &ops, &f, 4, 2, 10));
    CHECK(raw_live_fill(&s, dst, 16, 0x9000, &seq) == RAW_FRAME_ERR_TIMEOUT);
    raw_frame_generate_synthetic_fallback(dst, 4, 2, 42);
    CHECK(dst[0] == 235 && dst[1] == 128 && dst[2] == 235 && dst[3] == 128);
    passed++;

    /* Lease retain verification across repeated failed drain attempts */
    setup(&f, RAW_FRAME_PIXFMT_YUY2); s = (raw_live_source){0};
    f.error_release = -7;
    CHECK(!raw_live_init(&s, &ops, &f, 4, 2, 10));
    CHECK(raw_live_fill(&s, dst, 16, 0x9000, &seq) == -7);
    CHECK(s.leased.token == 7);
    CHECK(raw_live_fill(&s, dst, 16, 0x9000, &seq) == -7);
    CHECK(f.acquisitions == 1);
    CHECK(raw_live_drain(&s) == -7);
    CHECK(s.leased.token == 7);
    f.error_release = 0;
    CHECK(!raw_live_drain(&s));
    CHECK(s.leased.token == 0);
    CHECK(!raw_live_shutdown(&s));
    passed++;

    puts("Raw live source ownership/conversion checks passed");printf("cases=%u\n",passed);return 0;
}
