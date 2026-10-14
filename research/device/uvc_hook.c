/*
 * Sony ZV-E10 UVC USB Webcam Hijack Hook Library (v1.0)
 *
 * Automatically loaded via /setting/mode/preload inside im.elf, or
 * injected dynamically into the running camera process.
 *
 * Unlocks High-Speed USB 2.0 UVC Video Streaming:
 * - 1080p Full HD (1920x1080) @ 30fps / 60fps
 * - 3.2K 3:2 Open Gate (3240x2160) @ 24fps / 30fps
 * - 2.2K 3:2 Open Gate (2160x1440) @ 30fps
 * - High-Bitrate MJPEG (saturating USB 2.0 Bulk throughput ~40-43 MB/s)
 *
 * Volatile RAM patching only: Zero NAND flash modifications.
 */

int open(const char* pathname, int flags, ...);
int close(int fd);
int read(int fd, void* buf, unsigned int count);
int write(int fd, const void* buf, unsigned int count);
int mprotect(void* addr, unsigned int len, int prot);
int getpid(void);
long syscall(long number, ...);
int snprintf(char* str, unsigned int size, const char* format, ...);
char* strstr(const char* haystack, const char* needle);
int strcmp(const char* s1, const char* s2);
unsigned int strlen(const char* s);
int usleep(unsigned int usec);

#define O_RDONLY    00000000
#define O_WRONLY    00000001
#define O_RDWR      00000002
#define O_CREAT     00000100
#define O_APPEND    00002000

#define PROT_READ   0x1
#define PROT_WRITE  0x2
#define PROT_EXEC   0x4

#define SYS_ARM_cacheflush 0xf0002

/* Target relative offsets in libInfraUsbCmn.so */
#define OFF_PAL_FRAME_DESC      0x12550
#define OFF_NTSC_FRAME_DESC     0x1263e

/* Target relative offsets in libInfraStreamingUsb.so */
#define OFF_STREAM_WIDTH_INST   0x908a  /* mov.w r2, #1280 (4 bytes) */
#define OFF_STREAM_BITRATE_INST 0x908e  /* mov.w r3, #300  (4 bytes) */
#define OFF_STREAM_FPS_INST     0x9098  /* movs r2, #30    (2 bytes) */

static unsigned long g_base_usbcmn = 0;
static unsigned long g_base_streaming = 0;

/* Streaming mode configuration */
typedef struct {
    unsigned short width;
    unsigned short height;
    unsigned int fps;
    unsigned int bitrate_mbps;
    unsigned char stream_inst_width[4];
    unsigned char stream_inst_bitrate[4];
    unsigned char stream_inst_fps[2];
} uvc_config_t;

static uvc_config_t g_cfg = {
    .width = 1920,
    .height = 1080,
    .fps = 30,
    .bitrate_mbps = 300,
    .stream_inst_width = { 0x4f, 0xf4, 0xf0, 0x62 },   /* mov.w r2, #1920 */
    .stream_inst_bitrate = { 0x4f, 0xf4, 0x96, 0x73 }, /* mov.w r3, #300  */
    .stream_inst_fps = { 0x1e, 0x22 }                   /* movs r2, #30    */
};

static void log_msg(const char* msg) {
    int fd_log = open("/setting/uvc.log", O_WRONLY | O_CREAT | O_APPEND, 0666);
    if (fd_log >= 0) {
        write(fd_log, msg, strlen(msg));
        close(fd_log);
    }
    int fd_kmsg = open("/dev/kmsg", O_WRONLY);
    if (fd_kmsg >= 0) {
        write(fd_kmsg, msg, strlen(msg));
        close(fd_kmsg);
    }
}

static int is_target_process(void) {
    int fd = open("/proc/self/cmdline", O_RDONLY);
    if (fd < 0) return 0;
    char buf[256];
    int n = read(fd, buf, sizeof(buf) - 1);
    close(fd);
    if (n <= 0) return 0;
    buf[n] = '\0';

    if (strstr(buf, "sh") == buf || strstr(buf, "busybox") != 0) return 0;
    if (strstr(buf, "bootin") != 0) return 0;

    return (strstr(buf, "im.elf") != 0);
}

static unsigned long parse_hex(const char* s) {
    unsigned long val = 0;
    while (*s) {
        if (*s >= '0' && *s <= '9') val = (val << 4) | (*s - '0');
        else if (*s >= 'a' && *s <= 'f') val = (val << 4) | (*s - 'a' + 10);
        else if (*s >= 'A' && *s <= 'F') val = (val << 4) | (*s - 'A' + 10);
        else break;
        s++;
    }
    return val;
}

static int find_lib_base(const char* lib_name, unsigned long* p_base) {
    int fd = open("/proc/self/maps", O_RDONLY);
    if (fd < 0) return -1;
    char buf[1024];
    char line[256];
    int line_pos = 0;
    int n;
    int found = 0;
    while ((n = read(fd, buf, sizeof(buf))) > 0) {
        for (int i = 0; i < n; i++) {
            if (buf[i] == '\n' || line_pos >= (int)sizeof(line) - 2) {
                line[line_pos] = '\0';
                if (strstr(line, lib_name) != 0 && strstr(line, "r-xp") != 0) {
                    *p_base = parse_hex(line);
                    found = 1;
                    break;
                }
                line_pos = 0;
            } else {
                line[line_pos++] = buf[i];
            }
        }
        if (found) break;
    }
    close(fd);
    return found ? 0 : -1;
}

static void read_config(void) {
    int fd = open("/setting/uvc.conf", O_RDONLY);
    if (fd < 0) {
        log_msg("[uvc_hook] /setting/uvc.conf not found, using default 1080p 30fps\n");
        return;
    }
    char buf[512];
    int n = read(fd, buf, sizeof(buf) - 1);
    close(fd);
    if (n <= 0) return;
    buf[n] = '\0';

    if (strstr(buf, "mode=opengate") != 0 || strstr(buf, "mode=3.2k") != 0) {
        log_msg("[uvc_hook] Configured mode: 3.2K 3:2 Open Gate (3240x2160 @ 24fps)\n");
        g_cfg.width = 3240;
        g_cfg.height = 2160;
        g_cfg.fps = 24;
        g_cfg.bitrate_mbps = 300;
        /* movw r2, #3240 (0x0ca8) -> 40 f6 a8 42 */
        g_cfg.stream_inst_width[0] = 0x40;
        g_cfg.stream_inst_width[1] = 0xf6;
        g_cfg.stream_inst_width[2] = 0xa8;
        g_cfg.stream_inst_width[3] = 0x42;
        /* movs r2, #24 -> 18 22 */
        g_cfg.stream_inst_fps[0] = 0x18;
        g_cfg.stream_inst_fps[1] = 0x22;
    } else if (strstr(buf, "mode=2k_opengate") != 0) {
        log_msg("[uvc_hook] Configured mode: 2.2K 3:2 Open Gate (2160x1440 @ 30fps)\n");
        g_cfg.width = 2160;
        g_cfg.height = 1440;
        g_cfg.fps = 30;
        g_cfg.bitrate_mbps = 300;
        /* movw r2, #2160 (0x0870) -> 40 f6 70 02 */
        g_cfg.stream_inst_width[0] = 0x40;
        g_cfg.stream_inst_width[1] = 0xf6;
        g_cfg.stream_inst_width[2] = 0x70;
        g_cfg.stream_inst_width[3] = 0x02;
        /* movs r2, #30 -> 1e 22 */
        g_cfg.stream_inst_fps[0] = 0x1e;
        g_cfg.stream_inst_fps[1] = 0x22;
    } else if (strstr(buf, "mode=1080p60") != 0) {
        log_msg("[uvc_hook] Configured mode: 1080p Full HD (1920x1080 @ 60fps)\n");
        g_cfg.width = 1920;
        g_cfg.height = 1080;
        g_cfg.fps = 60;
        g_cfg.bitrate_mbps = 320;
        /* mov.w r2, #1920 -> 4f f4 f0 62 */
        g_cfg.stream_inst_width[0] = 0x4f;
        g_cfg.stream_inst_width[1] = 0xf4;
        g_cfg.stream_inst_width[2] = 0xf0;
        g_cfg.stream_inst_width[3] = 0x62;
        /* movs r2, #60 -> 3c 22 */
        g_cfg.stream_inst_fps[0] = 0x3c;
        g_cfg.stream_inst_fps[1] = 0x22;
    } else {
        log_msg("[uvc_hook] Configured mode: 1080p Full HD (1920x1080 @ 30fps)\n");
    }
}

static int patch_bytes(unsigned long addr, const unsigned char* new_bytes, unsigned int len, const char* name) {
    char buf[256];
    unsigned long page_addr = addr & ~(4096 - 1);
    unsigned long page_len = ((addr + len - 1) & ~(4096 - 1)) - page_addr + 4096;

    if (mprotect((void*)page_addr, page_len, PROT_READ | PROT_WRITE | PROT_EXEC) != 0) {
        snprintf(buf, sizeof(buf), "[uvc_hook] ERROR: mprotect failed for %s at 0x%08lx\n", name, addr);
        log_msg(buf);
        return -1;
    }

    for (unsigned int i = 0; i < len; i++) {
        *(volatile unsigned char*)(addr + i) = new_bytes[i];
    }

    __builtin___clear_cache((char*)addr, (char*)(addr + len));
    syscall(SYS_ARM_cacheflush, addr, addr + len, 0);

    mprotect((void*)page_addr, page_len, PROT_READ | PROT_EXEC);

    /* Verification */
    for (unsigned int i = 0; i < len; i++) {
        unsigned char b = *(volatile unsigned char*)(addr + i);
        if (b != new_bytes[i]) {
            snprintf(buf, sizeof(buf), "[uvc_hook] ERROR: Verification mismatch for %s at +%d (got 0x%02x, want 0x%02x)\n",
                     name, i, b, new_bytes[i]);
            log_msg(buf);
            return -2;
        }
    }
    return 0;
}

static int patch_frame_descriptor(unsigned long desc_va, const char* label, unsigned int default_interval_100ns) {
    unsigned char patch[30];
    char buf[256];

    /* Standard UVC VS_FRAME_MJPEG descriptor (30 bytes) */
    patch[0]  = 0x1e; /* bLength = 30 */
    patch[1]  = 0x24; /* CS_INTERFACE */
    patch[2]  = 0x07; /* VS_FRAME_MJPEG */
    patch[3]  = 0x01; /* bFrameIndex = 1 */
    patch[4]  = 0x00; /* bmCapabilities */

    /* wWidth (little-endian) */
    patch[5]  = (unsigned char)(g_cfg.width & 0xff);
    patch[6]  = (unsigned char)((g_cfg.width >> 8) & 0xff);

    /* wHeight (little-endian) */
    patch[7]  = (unsigned char)(g_cfg.height & 0xff);
    patch[8]  = (unsigned char)((g_cfg.height >> 8) & 0xff);

    /* dwMinBitRate (bps, e.g. 350 Mbps = 350,000,000 = 0x14dc9380) */
    unsigned int bps = g_cfg.bitrate_mbps * 1000000;
    patch[9]  = (unsigned char)(bps & 0xff);
    patch[10] = (unsigned char)((bps >> 8) & 0xff);
    patch[11] = (unsigned char)((bps >> 16) & 0xff);
    patch[12] = (unsigned char)((bps >> 24) & 0xff);

    /* dwMaxBitRate */
    patch[13] = patch[9];
    patch[14] = patch[10];
    patch[15] = patch[11];
    patch[16] = patch[12];

    /* dwMaxVideoFrameBufferSize (14,745,600 = 0x00e10000) */
    unsigned int buf_sz = 14745600;
    patch[17] = (unsigned char)(buf_sz & 0xff);
    patch[18] = (unsigned char)((buf_sz >> 8) & 0xff);
    patch[19] = (unsigned char)((buf_sz >> 16) & 0xff);
    patch[20] = (unsigned char)((buf_sz >> 24) & 0xff);

    /* dwDefaultFrameInterval (100ns units) */
    patch[21] = (unsigned char)(default_interval_100ns & 0xff);
    patch[22] = (unsigned char)((default_interval_100ns >> 8) & 0xff);
    patch[23] = (unsigned char)((default_interval_100ns >> 16) & 0xff);
    patch[24] = (unsigned char)((default_interval_100ns >> 24) & 0xff);

    /* bFrameIntervalType = 1 (discrete) */
    patch[25] = 0x01;

    /* dwFrameInterval[0] */
    patch[26] = patch[21];
    patch[27] = patch[22];
    patch[28] = patch[23];
    patch[29] = patch[24];

    snprintf(buf, sizeof(buf), "[uvc_hook] Patching %s descriptor at 0x%08lx: %dx%d, interval=%u (%.1f fps)\n",
             label, desc_va, g_cfg.width, g_cfg.height, default_interval_100ns,
             10000000.0 / (double)default_interval_100ns);
    log_msg(buf);

    return patch_bytes(desc_va, patch, sizeof(patch), label);
}

static void apply_uvc_patches(void) {
    char buf[256];
    snprintf(buf, sizeof(buf), "[uvc_hook] Active in im.elf (PID %d)\n", getpid());
    log_msg(buf);

    read_config();

    if (find_lib_base("libInfraUsbCmn.so", &g_base_usbcmn) < 0) {
        log_msg("[uvc_hook] WARNING: libInfraUsbCmn.so not yet in maps, using fallback\n");
    }
    if (find_lib_base("libInfraStreamingUsb.so", &g_base_streaming) < 0) {
        log_msg("[uvc_hook] WARNING: libInfraStreamingUsb.so not yet in maps, using fallback\n");
    }

    snprintf(buf, sizeof(buf), "[uvc_hook] Module bases: libInfraUsbCmn=0x%08lx, libInfraStreamingUsb=0x%08lx\n",
             g_base_usbcmn, g_base_streaming);
    log_msg(buf);

    int errors = 0;

    /* 1. Patch UVC Descriptors in libInfraUsbCmn.so */
    if (g_base_usbcmn != 0) {
        unsigned int pal_interval = 10000000 / (g_cfg.fps == 60 ? 50 : (g_cfg.fps == 24 ? 25 : g_cfg.fps));
        unsigned int ntsc_interval = 10000000 / g_cfg.fps;

        if (patch_frame_descriptor(g_base_usbcmn + OFF_PAL_FRAME_DESC, "PAL_MJPEG_DESC", pal_interval) < 0) errors++;
        if (patch_frame_descriptor(g_base_usbcmn + OFF_NTSC_FRAME_DESC, "NTSC_MJPEG_DESC", ntsc_interval) < 0) errors++;
    }

    /* 2. Patch VideoEsManager::video_stream_start in libInfraStreamingUsb.so */
    if (g_base_streaming != 0) {
        unsigned long va_width = g_base_streaming + OFF_STREAM_WIDTH_INST;
        unsigned long va_bitrate = g_base_streaming + OFF_STREAM_BITRATE_INST;
        unsigned long va_fps = g_base_streaming + OFF_STREAM_FPS_INST;

        if (patch_bytes(va_width, g_cfg.stream_inst_width, 4, "video_stream_start_width") < 0) errors++;
        if (patch_bytes(va_bitrate, g_cfg.stream_inst_bitrate, 4, "video_stream_start_bitrate") < 0) errors++;
        if (patch_bytes(va_fps, g_cfg.stream_inst_fps, 2, "video_stream_start_fps") < 0) errors++;
    }

    if (errors == 0) {
        snprintf(buf, sizeof(buf), "[uvc_hook] === UVC WEBCAM HIJACK COMPLETE: %dx%d @ %u fps (bitrate %u Mbps) ===\n",
                 g_cfg.width, g_cfg.height, g_cfg.fps, g_cfg.bitrate_mbps);
        log_msg(buf);
    } else {
        snprintf(buf, sizeof(buf), "[uvc_hook] === UVC HIJACK COMPLETED WITH %d ERRORS ===\n", errors);
        log_msg(buf);
    }
}

__attribute__((constructor))
void uvc_hook_init(void) {
    if (!is_target_process()) return;
    apply_uvc_patches();
}
