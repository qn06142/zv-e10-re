/*
 * Sony ZV-E10 Standalone Sidecar OSD Demo
 * Probes SUGILITE Graphics Engine and VDF Display Plane
 */

int printf(const char* format, ...);
void* dlopen(const char* filename, int flag);
void* dlsym(void* handle, const char* symbol);
char* dlerror(void);
int dlclose(void* handle);

#define RTLD_LAZY   0x00001
#define RTLD_NOW    0x00002
#define RTLD_GLOBAL 0x00100

__attribute__((visibility("default")))
void* arch_phys_to_cache(void* p) {
    return p;
}

int main(int argc, char** argv) {
    printf("=========================================\n");
    printf("[*] ZV-E10 Standalone OSD Sidecar starting\n");
    printf("=========================================\n");

    /* 1. Open libObj.so */
    void* hObj = dlopen("/usr/lib/libObj.so", RTLD_LAZY | RTLD_GLOBAL);
    if (!hObj) {
        printf("[-] Failed to dlopen libObj.so: %s\n", dlerror());
        return 1;
    }
    printf("[+] libObj.so loaded at %p\n", hObj);

    /* 2. Resolve GraphicsEngine and Blitter symbols */
    void* (*p_getInstance)(void) = (void* (*)(void))dlsym(hObj, "_ZN2ux6gfxeng14GraphicsEngine15sys_getInstanceEv");
    unsigned short (*p_getWidth)(void*) = (unsigned short (*)(void*))dlsym(hObj, "_ZNK2ux6gfxeng14GraphicsEngine19getFramebufferWidthEv");
    unsigned short (*p_getHeight)(void*) = (unsigned short (*)(void*))dlsym(hObj, "_ZNK2ux6gfxeng14GraphicsEngine20getFramebufferHeightEv");
    void* (*p_getScreen)(int) = (void* (*)(int))dlsym(hObj, "GRM_screenGetOnBitmap");
    void* p_rectblit = dlsym(hObj, "GRM_gpermRectblit");

    printf("[+] GraphicsEngine::sys_getInstance = %p\n", p_getInstance);
    printf("[+] GRM_screenGetOnBitmap           = %p\n", p_getScreen);
    printf("[+] GRM_gpermRectblit               = %p\n", p_rectblit);

    if (p_getInstance && p_getWidth && p_getHeight) {
        void* ge = p_getInstance();
        printf("[+] Active GraphicsEngine instance: %p\n", ge);
        if (ge) {
            unsigned short w = p_getWidth(ge);
            unsigned short h = p_getHeight(ge);
            printf("[+] Live Framebuffer Geometry: %u x %u\n", w, h);
        }
    }

    if (p_getScreen) {
        void* screen_bmp = p_getScreen(0);
        printf("[+] Active Screen Bitmap (Layer 0): %p\n", screen_bmp);
    }

    /* 3. Open libBizFw.so for VDF Control */
    void* hBiz = dlopen("/usr/lib/libBizFw.so", RTLD_LAZY | RTLD_GLOBAL);
    if (hBiz) {
        printf("[+] libBizFw.so loaded at %p\n", hBiz);
        void* vdf_ctor = dlsym(hBiz, "_ZN17OBJAVBBCBASECLASS5VdfChC1Et");
        void* vdf_setOsd = dlsym(hBiz, "_ZN17OBJAVBBCBASECLASS5VdfCh11setOSDOnOffERKN3VDF28VDF_PRM_INPUT_SET_OSD_ON_OFFE");
        printf("[+] VdfCh::VdfCh(channel)           = %p\n", vdf_ctor);
        printf("[+] VdfCh::setOSDOnOff              = %p\n", vdf_setOsd);
        dlclose(hBiz);
    }

    dlclose(hObj);
    printf("[*] Sidecar OSD Demo check completed successfully!\n");
    return 0;
}
