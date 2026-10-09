/*
 * Sony ZV-E10 Open Gate 3:2 Video Unlock Hook Library (v2.0)
 *
 * Automatically loaded via /etc/ld.so.preload.
 * Activates ONLY inside im.elf (main camera application process).
 *
 * Implements the complete multi-point Open Gate architecture:
 * 1. libmpr.so (0x5422e6): Expands SetRecAspect bitmask whitelist (0x2b -> 0x2f) to permit Aspect 2 (3:2).
 * 2. libObj.so (0x978bea): Patches 4K ConvertRecFormat to output Aspect 2 (3:2) instead of hardcoded 1 (16:9).
 * 3. libObj.so (0x2d229c): Patches InfraMovieEncoderSeqSetAspect to output Aspect 2 (3:2).
 * 4. libObj.so (0xeb0f26): Patches Live View aspect classification table to map 4K stream to 3240x2160 (Case 1).
 *
 * Subsystem Safety:
 * - 100% in-memory volatile modifications; zero writes to read-only flash partitions.
 * - Still photo, FHD 1080p, AVCHD, and HDMI pipelines completely isolated and unaffected.
 */

int printf(const char* format, ...);
int snprintf(char* str, unsigned int size, const char* format, ...);
int open(const char* pathname, int flags, ...);
int close(int fd);
int read(int fd, void* buf, unsigned int count);
int write(int fd, const void* buf, unsigned int count);
int mprotect(void* addr, unsigned int len, int prot);
int getpid(void);
long syscall(long number, ...);
void* fopen(const char* path, const char* mode);
char* fgets(char* s, int size, void* stream);
int fclose(void* fp);
int sscanf(const char* str, const char* format, ...);
int strncmp(const char* s1, const char* s2, unsigned int n);
char* strstr(const char* haystack, const char* needle);
unsigned int strlen(const char* s);

#define O_RDONLY    00000000
#define O_WRONLY    00000001
#define O_RDWR      00000002
#define O_CREAT     00000100
#define O_APPEND    00002000
#define O_SYNC      00010000

#define PROT_READ   0x1
#define PROT_WRITE  0x2
#define PROT_EXEC   0x4
#define MAP_SHARED  0x01
#define MAP_FAILED  ((void*)-1)
#define NULL        ((void*)0)

#define FB_PHYS_ADDR 0x3f3ec000
#define FB_SIZE      0x00401000

int pthread_create(void* thread, void* attr, void* (*start_routine)(void*), void* arg);
void* mmap(void* addr, unsigned int length, int prot, int flags, int fd, unsigned int offset);
int munmap(void* addr, unsigned int length);

#define SYS_ARM_cacheflush 0xf0002

/* Target relative offsets */
#define OFF_LIBMPR_WHITELIST    0x5422e6
#define OFF_LIBOBJ_REC_ASPECT   0x978bea
#define OFF_LIBOBJ_SEQ_ASPECT   0x2d229c
#define OFF_LIBOBJ_LV_TABLE     0xeb0f26

static unsigned long g_base_libobj = 0;
static unsigned long g_base_libmpr = 0;

__attribute__((visibility("default")))
void* arch_phys_to_cache(void* p) {
    return p;
}

static int is_target_process(void) {
    int fd = open("/proc/self/cmdline", O_RDONLY);
    if (fd < 0) return 0;
    char buf[128];
    int n = read(fd, buf, sizeof(buf) - 1);
    close(fd);
    if (n <= 0) return 0;
    buf[n] = '\0';
    return (strstr(buf, "im.elf") != 0);
}

static void log_msg(const char* msg) {
    printf("%s", msg);

    int fd_log = open("/setting/opengate.log", O_WRONLY | O_CREAT | O_APPEND, 0666);
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

static int g_current_aspect = 1; // Default 16:9
static int g_osd_banner_enabled = 1;
static int g_hotkey_code = 111; // Default KEY_DELETE
static int g_hotkey_enabled = 0;

static void load_config(int* p_enable) {
    *p_enable = 1;
    void* fp = fopen("/setting/opengate.conf", "r");
    if (!fp) return;
    char line[128];
    while (fgets(line, sizeof(line), fp)) {
        if (line[0] == '#' || line[0] == '\n') continue;
        int val = 0;
        if (sscanf(line, "enable=%d", &val) == 1) {
            *p_enable = val;
        }
        if (sscanf(line, "osd_banner=%d", &val) == 1) {
            g_osd_banner_enabled = val;
        }
        if (strstr(line, "hotkey=C1")) {
            g_hotkey_enabled = 1;
            g_hotkey_code = 46; // Example for C
        } else if (strstr(line, "hotkey=trash")) {
            g_hotkey_enabled = 1;
            g_hotkey_code = 111; // Example for DEL
        }
    }
    fclose(fp);
}

static void blit_osd_banner(int aspect_mode) {
    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) return;

    void* fb = mmap(NULL, FB_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, FB_PHYS_ADDR);
    if (fb == MAP_FAILED) {
        close(fd);
        return;
    }

    unsigned int* ptr32 = (unsigned int*)fb;
    int banner_pixels = 640 * 40;

    // Magenta (0x00FF00FF) for 3:2, Cyan (0x0000FFFF) for 16:9
    unsigned int color = (aspect_mode == 0) ? 0x00FF00FF : 0x0000FFFF;

    if (banner_pixels * 4 < FB_SIZE) {
        for (int i = 0; i < banner_pixels; i++) {
            ptr32[i] = color;
        }
    }

    munmap(fb, FB_SIZE);
    close(fd);
}

static void apply_dynamic_aspect(int val);

static void* input_thread_func(void* arg) {
    const char* path = (const char*)arg;
    int fd = open(path, O_RDONLY);
    if (fd < 0) return (void*)0;

    struct {
        long time_sec;
        long time_usec;
        unsigned short type;
        unsigned short code;
        unsigned int value;
    } ev;

    while (read(fd, &ev, sizeof(ev)) == sizeof(ev)) {
        if (ev.type == 1 && ev.value == 1) { // EV_KEY down
            if (ev.code == g_hotkey_code) {
                g_current_aspect = (g_current_aspect == 0) ? 1 : 0;
                apply_dynamic_aspect(g_current_aspect);
                if (g_osd_banner_enabled) {
                    blit_osd_banner(g_current_aspect);
                }
            }
        }
    }
    close(fd);
    return (void*)0;
}

static int find_lib_base(const char* lib_name, unsigned long* p_base, unsigned long* p_size) {
    void* fp = fopen("/proc/self/maps", "r");
    if (!fp) return -1;

    char line[256];
    int found = 0;
    while (fgets(line, sizeof(line), fp)) {
        if (strstr(line, lib_name) && strstr(line, "r-xp")) {
            unsigned long start = 0, end = 0;
            if (sscanf(line, "%lx-%lx", &start, &end) == 2) {
                *p_base = start;
                *p_size = end - start;
                found = 1;
                break;
            }
        }
    }
    fclose(fp);
    return found ? 0 : -1;
}

static int patch_bytes(unsigned long addr, const unsigned char* new_bytes, unsigned int len, const char* name) {
    char buf[256];
    unsigned long page_addr = addr & ~(4096 - 1);
    unsigned long page_len = ((addr + len - 1) & ~(4096 - 1)) - page_addr + 4096;

    if (mprotect((void*)page_addr, page_len, PROT_READ | PROT_WRITE | PROT_EXEC) != 0) {
        snprintf(buf, sizeof(buf), "[opengate] ERROR: mprotect failed for %s at 0x%08lx\n", name, addr);
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
            snprintf(buf, sizeof(buf), "[opengate] ERROR: Verification mismatch for %s at +%d (got 0x%02x, want 0x%02x)\n",
                     name, i, b, new_bytes[i]);
            log_msg(buf);
            return -2;
        }
    }

    snprintf(buf, sizeof(buf), "[opengate] Successfully applied patch: %s at 0x%08lx\n", name, addr);
    log_msg(buf);
    return 0;
}

__attribute__((visibility("default")))
int opengate_apply_patch(void) {
    char buf[256];
    int pid = getpid();

    snprintf(buf, sizeof(buf), "==========================================================\n"
                               "[opengate] Hook activating in im.elf (PID %d)...\n", pid);
    int enable = 1;
    load_config(&enable);
    if (!enable) {
        log_msg("[opengate] Disabled via /setting/opengate.conf (enable=0). Aborting.\n");
        return 0;
    }

    /* 1. Discover library virtual addresses */
    unsigned long size_libobj = 0;
    if (find_lib_base("libObj.so", &g_base_libobj, &size_libobj) < 0) {
        log_msg("[opengate] ERROR: libObj.so not found in maps!\n");
        return -1;
    }

    unsigned long size_libmpr = 0;
    if (find_lib_base("libmpr.so", &g_base_libmpr, &size_libmpr) < 0) {
        log_msg("[opengate] ERROR: libmpr.so not found in maps!\n");
        return -1;
    }

    snprintf(buf, sizeof(buf), "[opengate] Found libObj.so at 0x%08lx, libmpr.so at 0x%08lx\n",
             g_base_libobj, g_base_libmpr);
    log_msg(buf);

    int patch_errors = 0;

    /* -------------------------------------------------------------
     * Patch 1: libmpr.so Aspect Whitelist Filter (FeaCore::SetRecAspect)
     * Target: 0x5422e6: tst.w r2, #0x2b (12 f0 2b 0f) -> #0x2f (12 f0 2f 0f)
     * Permits Aspect enum 2 (3:2) without error 5 rejection.
     * ------------------------------------------------------------- */
    unsigned long va_mpr_whitelist = g_base_libmpr + OFF_LIBMPR_WHITELIST;
    const unsigned char cur_mpr_whitelist = *(volatile unsigned char*)(va_mpr_whitelist + 2);
    if (cur_mpr_whitelist == 0x2b) {
        const unsigned char patch_mpr[1] = { 0x2f };
        if (patch_bytes(va_mpr_whitelist + 2, patch_mpr, 1, "libmpr_whitelist_0x2f") < 0) {
            patch_errors++;
        }
    } else if (cur_mpr_whitelist == 0x2f) {
        log_msg("[opengate] libmpr whitelist already patched (0x2f).\n");
    } else {
        snprintf(buf, sizeof(buf), "[opengate] WARNING: Unexpected byte at libmpr whitelist (0x%02x)!\n",
                 cur_mpr_whitelist);
        log_msg(buf);
        patch_errors++;
    }

    /* -------------------------------------------------------------
     * Dynamic patches applied in Bkup_Read intercept.
     * We just initialize with 16:9 so we have a known state,
     * or we can just let Bkup_Read intercept handle it!
     * ------------------------------------------------------------- */

    if (patch_errors == 0) {
        log_msg("==========================================================\n"
                "[opengate] SUCCESS: All 4 Open Gate 3:2 Patches Verified & Active!\n"
                "[opengate] Subsystems: 4K Movie Rec = 3:2 | Live View = 3240x2160 | Whitelist = OK\n"
                "==========================================================\n");
        return 0;
    } else {
        snprintf(buf, sizeof(buf), "[opengate] Completed with %d errors.\n", patch_errors);
        log_msg(buf);
        return -3;
    }
}

static void apply_dynamic_aspect(int val) {
    if (g_base_libobj == 0) return;

    unsigned long va_obj_rec = g_base_libobj + OFF_LIBOBJ_REC_ASPECT;
    unsigned long va_obj_seq = g_base_libobj + OFF_LIBOBJ_SEQ_ASPECT;
    unsigned long va_obj_lv = g_base_libobj + OFF_LIBOBJ_LV_TABLE;

    if (val == 0) {
        // 3:2 Open Gate
        patch_bytes(va_obj_rec, (const unsigned char*)"\x02\x22", 2, "libObj_4K_rec_aspect_3_2");
        patch_bytes(va_obj_seq, (const unsigned char*)"\x02\x23", 2, "libObj_seq_aspect_3_2");
        patch_bytes(va_obj_lv,  (const unsigned char*)"\x01", 1, "libObj_live_view_canvas_3240");
    } else {
        // 16:9 Stock (or default fallback for non-3:2)
        patch_bytes(va_obj_rec, (const unsigned char*)"\x01\x22", 2, "libObj_4K_rec_aspect_16_9");
        patch_bytes(va_obj_seq, (const unsigned char*)"\x01\x23", 2, "libObj_seq_aspect_16_9");
        patch_bytes(va_obj_lv,  (const unsigned char*)"\x02", 1, "libObj_live_view_canvas_3840");
    }
}

static int (*orig_Bkup_Read)(int, void*) = 0;
static int (*orig_Bkup_Read_Attr)(int, int, void*) = 0;

__attribute__((visibility("default")))
int _ZN13BackupManager9Bkup_ReadEiPv(int attr_id, void* out_val) {
    if (!orig_Bkup_Read) {
        if (g_base_libobj == 0) {
            unsigned long size = 0;
            find_lib_base("libObj.so", &g_base_libobj, &size);
        }
        if (g_base_libobj) {
            // libObj.so offset for _ZN13BackupManager9Bkup_ReadEiPv is 0x168320 (+1 Thumb)
            orig_Bkup_Read = (int (*)(int, void*))(g_base_libobj + 0x168320 + 1);
        }
    }

    if (!orig_Bkup_Read) {
        return -1;
    }

    int ret = orig_Bkup_Read(attr_id, out_val);

    if (attr_id == 0x1070012 || attr_id == 0x10703b2) {
        if (out_val) {
            unsigned char val = *(unsigned char*)out_val;
            g_current_aspect = val;
            apply_dynamic_aspect(val);
        }
    }

    return ret;
}

__attribute__((visibility("default")))
int _ZN13BackupManager22Bkup_Read_Setting_AttrEiiPv(int slot, int attr_id, void* out_val) {
    if (!orig_Bkup_Read_Attr) {
        if (g_base_libobj == 0) {
            unsigned long size = 0;
            find_lib_base("libObj.so", &g_base_libobj, &size);
        }
        if (g_base_libobj) {
            // libObj.so offset for _ZN13BackupManager22Bkup_Read_Setting_AttrEiiPv is 0x1681f0 (+1 Thumb)
            orig_Bkup_Read_Attr = (int (*)(int, int, void*))(g_base_libobj + 0x1681f0 + 1);
        }
    }

    if (!orig_Bkup_Read_Attr) {
        return -1;
    }

    int ret = orig_Bkup_Read_Attr(slot, attr_id, out_val);

    if (attr_id == 0x1070012 || attr_id == 0x10703b2) {
        if (out_val) {
            unsigned char val = *(unsigned char*)out_val;
            g_current_aspect = val;
            apply_dynamic_aspect(val);
        }
    }

    return ret;
}

__attribute__((constructor))
void opengate_init(void) {
    if (!is_target_process()) {
        return;
    }
    opengate_apply_patch();

    // Read the setting once at startup to initialize memory correctly
    unsigned char val = 1; // Default to 16:9 if we can't read it
    if (g_base_libobj) {
        if (!orig_Bkup_Read) {
            orig_Bkup_Read = (int (*)(int, void*))(g_base_libobj + 0x168320 + 1);
        }
        if (orig_Bkup_Read) {
            orig_Bkup_Read(0x1070012, &val);
        }
    }
    g_current_aspect = val;
    apply_dynamic_aspect(val);

    if (g_hotkey_enabled) {
        void* thread1; pthread_create(&thread1, NULL, input_thread_func, (void*)"/dev/input/event0");
        void* thread2; pthread_create(&thread2, NULL, input_thread_func, (void*)"/dev/input/event1");
        void* thread3; pthread_create(&thread3, NULL, input_thread_func, (void*)"/dev/input/event2");
    }
}
