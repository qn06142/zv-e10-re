/*
 * Sony ZV-E10 Volatile OSD Hook Library (Non-Persistent)
 * In-memory hook for OSD plane diagnostics and framebuffer blitting.
 */

int printf(const char* format, ...);
int open(const char* pathname, int flags, ...);
int close(int fd);
void* mmap(void* addr, unsigned int length, int prot, int flags, int fd, unsigned int offset);
int munmap(void* addr, unsigned int length);
int getpid(void);

#define O_RDWR     00000002
#define O_SYNC     00010000

#define PROT_READ  0x1
#define PROT_WRITE 0x2
#define MAP_SHARED 0x01
#define MAP_FAILED ((void*)-1)
#define NULL       ((void*)0)

#define FB_PHYS_ADDR 0x3f3ec000
#define FB_SIZE      0x00401000  /* 4MB display scanout buffer */

__attribute__((visibility("default")))
void* arch_phys_to_cache(void* p) {
    return p;
}

/* Direct OSD Framebuffer banner blit via /dev/mem */
static void blit_osd_test_banner(void) {
    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) {
        printf("[osd_hook] Failed to open /dev/mem\n");
        return;
    }

    void* fb = mmap(NULL, FB_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, FB_PHYS_ADDR);
    if (fb == MAP_FAILED) {
        printf("[osd_hook] Failed to mmap /dev/mem at 0x%08x\n", FB_PHYS_ADDR);
        close(fd);
        return;
    }

    printf("[osd_hook] Framebuffer mapped at %p (phys 0x%08x)\n", fb, FB_PHYS_ADDR);

    /* Draw a high-contrast test rectangle across the scanout buffer (e.g. top banner) */
    unsigned int* ptr32 = (unsigned int*)fb;
    /* 640 width * 40 height in 32-bit words */
    int banner_pixels = 640 * 40;
    if (banner_pixels * 4 < FB_SIZE) {
        /* Write distinct color pattern: 0x00FF00FF (Magenta) */
        for (int i = 0; i < banner_pixels; i++) {
            ptr32[i] = 0x00FF00FF;
        }
        printf("[osd_hook] Wrote 640x40 test banner to scanout buffer\n");
    }

    munmap(fb, FB_SIZE);
    close(fd);
}

/* Intercepted blit function for backward-compatible GRM callers */
__attribute__((visibility("default")))
int GRM_gpermRectblit(void* dst, void* src, void* rect, int flags) {
    printf("[osd_hook] GRM_gpermRectblit intercepted: dst=%p, src=%p\n", dst, src);
    blit_osd_test_banner();
    return 0;
}

/* Library constructor executed on dynamic load */
__attribute__((constructor))
void osd_hook_init(void) {
    int pid = getpid();
    printf("=========================================\n");
    printf("[*] ZV-E10 OSD In-Memory Hook Active (PID %d)\n", pid);
    printf("=========================================\n");

    /* Execute safe volatile test blit */
    blit_osd_test_banner();
}
