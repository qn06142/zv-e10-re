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

#define PROT_READ   0x1
#define PROT_WRITE  0x2
#define PROT_EXEC   0x4

#define SYS_ARM_cacheflush 0xf0002

/* Target relative offsets */
#define OFF_LIBMPR_WHITELIST    0x5422e6
#define OFF_LIBOBJ_REC_ASPECT   0x978bea
#define OFF_LIBOBJ_SEQ_ASPECT   0x2d229c
#define OFF_LIBOBJ_LV_TABLE     0xeb0f26

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
    }
    fclose(fp);
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
    unsigned long base_libobj = 0, size_libobj = 0;
    if (find_lib_base("libObj.so", &base_libobj, &size_libobj) < 0) {
        log_msg("[opengate] ERROR: libObj.so not found in maps!\n");
        return -1;
    }

    unsigned long base_libmpr = 0, size_libmpr = 0;
    if (find_lib_base("libmpr.so", &base_libmpr, &size_libmpr) < 0) {
        log_msg("[opengate] ERROR: libmpr.so not found in maps!\n");
        return -1;
    }

    snprintf(buf, sizeof(buf), "[opengate] Found libObj.so at 0x%08lx, libmpr.so at 0x%08lx\n",
             base_libobj, base_libmpr);
    log_msg(buf);

    int patch_errors = 0;

    /* -------------------------------------------------------------
     * Patch 1: libmpr.so Aspect Whitelist Filter (FeaCore::SetRecAspect)
     * Target: 0x5422e6: tst.w r2, #0x2b (12 f0 2b 0f) -> #0x2f (12 f0 2f 0f)
     * Permits Aspect enum 2 (3:2) without error 5 rejection.
     * ------------------------------------------------------------- */
    unsigned long va_mpr_whitelist = base_libmpr + OFF_LIBMPR_WHITELIST;
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
     * Patch 2: libObj.so ConvertRecFormat 4K Aspect Assignment (0x978bea)
     * Target: movs r2, #1 (01 22) -> movs r2, #2 (02 22)
     * Forces 4K video recording to select Aspect 2 (3:2 Open Gate).
     * ------------------------------------------------------------- */
    unsigned long va_obj_rec = base_libobj + OFF_LIBOBJ_REC_ASPECT;
    const unsigned short cur_obj_rec = *(volatile unsigned short*)va_obj_rec;
    if (cur_obj_rec == 0x2201) {
        const unsigned char patch_obj_rec[2] = { 0x02, 0x22 };
        if (patch_bytes(va_obj_rec, patch_obj_rec, 2, "libObj_4K_rec_aspect_3_2") < 0) {
            patch_errors++;
        }
    } else if (cur_obj_rec == 0x2202) {
        log_msg("[opengate] libObj 4K rec aspect already patched (r2=2).\n");
    } else {
        snprintf(buf, sizeof(buf), "[opengate] WARNING: Unexpected opcode at libObj rec aspect (0x%04x)!\n",
                 cur_obj_rec);
        log_msg(buf);
        patch_errors++;
    }

    /* -------------------------------------------------------------
     * Patch 3: libObj.so InfraMovieEncoderSeqSetAspect (0x2d229c)
     * Target: movs r3, #1 (01 23) -> movs r3, #2 (02 23)
     * Direct encoder configuration aspect packet payload.
     * ------------------------------------------------------------- */
    unsigned long va_obj_seq = base_libobj + OFF_LIBOBJ_SEQ_ASPECT;
    const unsigned short cur_obj_seq = *(volatile unsigned short*)va_obj_seq;
    if (cur_obj_seq == 0x2301) {
        const unsigned char patch_obj_seq[2] = { 0x02, 0x23 };
        if (patch_bytes(va_obj_seq, patch_obj_seq, 2, "libObj_seq_aspect_3_2") < 0) {
            patch_errors++;
        }
    } else if (cur_obj_seq == 0x2302) {
        log_msg("[opengate] libObj seq aspect already patched (r3=2).\n");
    } else {
        snprintf(buf, sizeof(buf), "[opengate] WARNING: Unexpected opcode at libObj seq aspect (0x%04x)!\n",
                 cur_obj_seq);
        log_msg(buf);
        patch_errors++;
    }

    /* -------------------------------------------------------------
     * Patch 4: libObj.so Live View Aspect Ratio Map Table (0xeb0f26)
     * Target: table[4] (16:9 ratio entry) = 0x02 (Case 2: 3840x2160)
     * Patched: 0x01 (Case 1: 3240x2160 3:2 Open Gate Canvas)
     * ------------------------------------------------------------- */
    unsigned long va_obj_lv = base_libobj + OFF_LIBOBJ_LV_TABLE;
    const unsigned char cur_obj_lv = *(volatile unsigned char*)va_obj_lv;
    if (cur_obj_lv == 0x02) {
        const unsigned char patch_obj_lv[1] = { 0x01 };
        if (patch_bytes(va_obj_lv, patch_obj_lv, 1, "libObj_live_view_canvas_3240") < 0) {
            patch_errors++;
        }
    } else if (cur_obj_lv == 0x01) {
        log_msg("[opengate] libObj live view canvas table already patched (Case 1).\n");
    } else {
        snprintf(buf, sizeof(buf), "[opengate] WARNING: Unexpected value in live view table (0x%02x)!\n",
                 cur_obj_lv);
        log_msg(buf);
        patch_errors++;
    }

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

__attribute__((constructor))
void opengate_init(void) {
    if (!is_target_process()) {
        return;
    }
    opengate_apply_patch();
}
