/*
 * Sony ZV-E10 Open Gate 3:2 Video Unlock Hook Library (v3.0)
 *
 * Automatically loaded via /setting/mode/preload inside im.elf.
 *
 * Implements the complete multi-point Open Gate architecture:
 * 1. Process Guard: Activates ONLY in im.elf (ignores sh, ash, busybox, bootin).
 * 2. Whitelist Bypass: libmpr.so (0x5422e6) expanded 0x2b -> 0x2f (unlocks 3:2 Aspect 2).
 * 3. ObjRenderer Aspect Override: libObj.so (0x25f918) -> returns Aspect 2 (3:2).
 * 4. Live View 3:2 Canvas: libObj.so (0xeb0f26) -> Case 1 (3240x2160 edge-to-edge).
 * 5. ConvertRecFormat 4K Aspect: libObj.so (0x978bea) -> Aspect 2 (3:2).
 * 6. Movie Encoder Pipeline: libObj.so (0x2d2388, 0x2d23a0, 0x2d23c4, 0x2d229c) -> Aspect 2 (3:2).
 * 7. 60 Recording Profiles: libmpr.so all 60 4K profiles width -> 3240 (0x0ca8).
 * 8. NVRAM Anti-Clamp Intercept:
 *    - Bkup_Read / Bkup_Read_Setting_Attr: Returns 0x02 for 0x1070012 & 0x10703b2.
 *    - Bkup_Write / Bkup_Write_Setting_Attr: Forces 0x02 for 0x1070012 & 0x10703b2.
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

/* Target relative offsets */
#define OFF_LIBMPR_WHITELIST    0x5422e6
#define OFF_LIBOBJ_RENDERER     0x25f918
#define OFF_LIBOBJ_LV_TABLE     0xeb0f26
#define OFF_LIBOBJ_REC_ASPECT   0x978bea
#define OFF_LIBOBJ_SEQ_1        0x2d2388
#define OFF_LIBOBJ_SEQ_2        0x2d23a0
#define OFF_LIBOBJ_SEQ_3        0x2d23c4
#define OFF_LIBOBJ_SEQ_4        0x2d229c

/* Primary Astra Movie Encoder Sequence (ZV-E10 main recording engine) */
#define OFF_LIBOBJ_ASTRA_SET_ASP1   0x2ccb3a  /* ldrb r3, [r5, #0x18] -> movs r3, #2 */
#define OFF_LIBOBJ_ASTRA_SET_ASP2   0x2ccb4a  /* ldrb r3, [r5, #0x19] -> movs r3, #2 */
#define OFF_LIBOBJ_ASTRA_MSG_ASP    0x2cce38  /* ldrb.w r3, [r7, #0x1ea] -> movs r3, #2; nop */
#define OFF_LIBOBJ_ASTRA_THM_W      0x2d0020  /* mov.w r3, #0x500 -> mov.w r3, #0x438 (1080) */
#define OFF_LIBOBJ_ASTRA_THM_W_S    0x2d002c  /* movs r3, #0xa0 -> movs r3, #0xb4 (180) */

/* Live View 4K Canvas Dimensions (edge-to-edge 3:2 on physical 3:2 screen) */
#define OFF_LIBOBJ_LV_CANVAS_W      0x260916  /* mov.w r2, #0xf00 -> movw r2, #0xca8 (3240) */
#define OFF_LIBOBJ_LV_CASE2_W       0x26095e  /* mov.w r3, #0xf00 -> movw r3, #0xca8 (3240) */

static unsigned long g_base_libobj = 0;
static unsigned long g_base_libmpr = 0;

static const unsigned long g_mpr_profile_offsets[60] = {
    0x00c4a8f6, 0x00c4a98e, 0x00c4aa26, 0x00c4aabe, 0x00c4b736, 0x00c4b7ce,
    0x00c4b866, 0x00c4b8fe, 0x00c4bc8e, 0x00c4bd26, 0x00c4bdbe, 0x00c4be56,
    0x00c4c79a, 0x00c4c832, 0x00c4c8ca, 0x00c4c962, 0x00c4c9fa, 0x00c4ca92,
    0x00c4cb2a, 0x00c4cbc2, 0x00c4cc5a, 0x00c4ccf2, 0x00c4cd8a, 0x00c4ce22,
    0x00c4ceba, 0x00c4cf52, 0x00c4cfea, 0x00c4d082, 0x00c4d11a, 0x00c4d1b2,
    0x00c4d24a, 0x00c4d2e2, 0x00c4d37a, 0x00c4d412, 0x00c4d4aa, 0x00c4d542,
    0x00c507ba, 0x00c50852, 0x00c508ea, 0x00c50982, 0x00c50a1a, 0x00c50ab2,
    0x00c5198a, 0x00c51a22, 0x00c51aba, 0x00c51b52, 0x00c51bea, 0x00c51c82,
    0x00c5493a, 0x00c549d2, 0x00c54a6a, 0x00c54b02, 0x00c5518a, 0x00c55222,
    0x00c552ba, 0x00c55352, 0x00c5564a, 0x00c556e2, 0x00c5577a, 0x00c55812,
};

static void log_msg(const char* msg) {
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

static int is_target_process(void) {
    int fd = open("/proc/self/cmdline", O_RDONLY);
    if (fd < 0) return 0;
    char buf[256];
    int n = read(fd, buf, sizeof(buf) - 1);
    close(fd);
    if (n <= 0) return 0;
    buf[n] = '\0';

    // Must NOT be a shell or bootin wrapper
    if (strstr(buf, "sh") == buf || strstr(buf, "busybox") != 0) return 0;
    if (strstr(buf, "bootin") != 0) return 0;

    // Must match im.elf
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
    return 0;
}

static void apply_all_patches(void) {
    char buf[256];
    snprintf(buf, sizeof(buf), "[opengate] Hook activating in im.elf (PID %d)...\n", getpid());
    log_msg(buf);

    if (g_base_libobj == 0) find_lib_base("libObj.so", &g_base_libobj);
    if (g_base_libobj == 0) g_base_libobj = 0x06592000;

    if (g_base_libmpr == 0) find_lib_base("libmpr.so", &g_base_libmpr);
    if (g_base_libmpr == 0) g_base_libmpr = 0x07a2b000;

    snprintf(buf, sizeof(buf), "[opengate] Bases: libObj=0x%08lx, libmpr=0x%08lx\n",
             g_base_libobj, g_base_libmpr);
    log_msg(buf);

    int errors = 0;

    // 1. libmpr.so whitelist mask (0x2b -> 0x2f)
    unsigned long va_mpr_whitelist = g_base_libmpr + OFF_LIBMPR_WHITELIST;
    const unsigned char patch_wl[1] = { 0x2f };
    if (patch_bytes(va_mpr_whitelist + 2, patch_wl, 1, "mpr_whitelist_0x2f") < 0) errors++;

    // 2. libObj.so ObjRenderer (Aspect query -> 3:2)
    const unsigned char patch_renderer[4] = { 0x01, 0x20, 0x70, 0x47 }; // movs r0, #1; bx lr
    if (patch_bytes(g_base_libobj + OFF_LIBOBJ_RENDERER, patch_renderer, 4, "obj_renderer_3_2") < 0) errors++;

    // 3. libObj.so Live View Classification Table (Case 1: 3240x2160 3:2 canvas)
    const unsigned char patch_lv[1] = { 0x01 };
    if (patch_bytes(g_base_libobj + OFF_LIBOBJ_LV_TABLE, patch_lv, 1, "obj_lv_table_3240") < 0) errors++;

    // 4. libObj.so ConvertRecFormat (4K Aspect -> 2 3:2)
    const unsigned char patch_rec[2] = { 0x02, 0x22 }; // movs r2, #2
    if (patch_bytes(g_base_libobj + OFF_LIBOBJ_REC_ASPECT, patch_rec, 2, "obj_rec_aspect_3_2") < 0) errors++;

    // 5. libObj.so InfraMovieEncoderSeqSetAspect (legacy sequence)
    const unsigned char patch_seq_r2[2] = { 0x02, 0x22 }; // movs r2, #2
    const unsigned char patch_seq_r3[2] = { 0x02, 0x23 }; // movs r3, #2
    if (patch_bytes(g_base_libobj + OFF_LIBOBJ_SEQ_1, patch_seq_r2, 2, "obj_seq_1") < 0) errors++;
    if (patch_bytes(g_base_libobj + OFF_LIBOBJ_SEQ_2, patch_seq_r2, 2, "obj_seq_2") < 0) errors++;
    if (patch_bytes(g_base_libobj + OFF_LIBOBJ_SEQ_3, patch_seq_r3, 2, "obj_seq_3") < 0) errors++;
    if (patch_bytes(g_base_libobj + OFF_LIBOBJ_SEQ_4, patch_seq_r3, 2, "obj_seq_4") < 0) errors++;

    // 5b. libObj.so InfraMovieEncoderSeqEncStart2Astra (Primary Astra Movie Engine)
    // Overrides both encoder aspect inputs (0x1002 and 0x1010) to 2 (3:2)
    const unsigned char patch_astra_asp[2] = { 0x02, 0x23 }; // movs r3, #2
    if (patch_bytes(g_base_libobj + OFF_LIBOBJ_ASTRA_SET_ASP1, patch_astra_asp, 2, "obj_astra_asp1") < 0) errors++;
    if (patch_bytes(g_base_libobj + OFF_LIBOBJ_ASTRA_SET_ASP2, patch_astra_asp, 2, "obj_astra_asp2") < 0) errors++;

    // 5c. libObj.so InfraMovieEncoderSeqEncStart2Astra AVBBC Msg Aspect Override
    // Forces AVBBC 0x55001f packet aspect field to 2 (3:2 Open Gate)
    const unsigned char patch_astra_msg[4] = { 0x02, 0x23, 0x00, 0xbf }; // movs r3, #2; nop
    if (patch_bytes(g_base_libobj + OFF_LIBOBJ_ASTRA_MSG_ASP, patch_astra_msg, 4, "obj_astra_msg_asp") < 0) errors++;

    // 5d. libObj.so Astra Thumbnail Aspect Overrides (Prevents thumbnail stretch/crash)
    // 1280x720 (16:9) -> 1080x720 (3:2) (width 0x438)
    const unsigned char patch_thm_w[4] = { 0x4f, 0xf4, 0x87, 0x63 }; // mov.w r3, #0x438
    if (patch_bytes(g_base_libobj + OFF_LIBOBJ_ASTRA_THM_W, patch_thm_w, 4, "obj_astra_thm_w") < 0) errors++;
    // 160x120 -> 180x120 (3:2) (width 0xb4)
    const unsigned char patch_thm_ws[2] = { 0xb4, 0x23 }; // movs r3, #0xb4
    if (patch_bytes(g_base_libobj + OFF_LIBOBJ_ASTRA_THM_W_S, patch_thm_ws, 2, "obj_astra_thm_ws") < 0) errors++;

    // 5e. libObj.so Live View 4K Root Buffer Dimensions (3840 -> 3240 edge-to-edge on 3:2 LCD)
    // At 0x260916: movw r2, #0xca8 (3240)
    const unsigned char patch_canvas_w[4] = { 0x40, 0xf6, 0xa8, 0x42 }; // movw r2, #0xca8
    if (patch_bytes(g_base_libobj + OFF_LIBOBJ_LV_CANVAS_W, patch_canvas_w, 4, "obj_lv_canvas_w") < 0) errors++;
    // At 0x26095e (Case 2: 16:9 fallback -> 3:2 3240 width)
    const unsigned char patch_case2_w[4] = { 0x40, 0xf6, 0xa8, 0x43 }; // movw r3, #0xca8
    if (patch_bytes(g_base_libobj + OFF_LIBOBJ_LV_CASE2_W, patch_case2_w, 4, "obj_lv_case2_w") < 0) errors++;

    // 6. All 60 libmpr.so 4K profiles to 3240 width (0x0ca8)
    const unsigned char patch_width[2] = { 0xa8, 0x0c }; // 3240
    for (int i = 0; i < 60; i++) {
        if (patch_bytes(g_base_libmpr + g_mpr_profile_offsets[i], patch_width, 2, "mpr_profile_3240") < 0) {
            errors++;
        }
    }

    if (errors == 0) {
        log_msg("[opengate] SUCCESS: All Open Gate 3:2 Patches Applied & Verified in im.elf!\n");
    } else {
        snprintf(buf, sizeof(buf), "[opengate] Applied with %d errors.\n", errors);
        log_msg(buf);
    }
}

static int (*orig_Bkup_Read)(int, void*) = 0;
static int (*orig_Bkup_Read_Attr)(int, int, void*) = 0;
static int (*orig_Bkup_Write)(int, const void*) = 0;
static int (*orig_Bkup_Write_Attr)(int, int, const void*) = 0;

__attribute__((visibility("default")))
int _ZN13BackupManager9Bkup_ReadEiPv(int attr_id, void* out_val) {
    if (!orig_Bkup_Read) {
        if (g_base_libobj == 0) find_lib_base("libObj.so", &g_base_libobj);
        if (g_base_libobj == 0) g_base_libobj = 0x06592000;
        orig_Bkup_Read = (int (*)(int, void*))(g_base_libobj + 0x168320 + 1);
    }
    int ret = orig_Bkup_Read ? orig_Bkup_Read(attr_id, out_val) : -1;
    if (attr_id == 0x1070012 || attr_id == 0x10703b2) {
        if (out_val) *(unsigned char*)out_val = 2; // Force 3:2 Open Gate
    }
    return ret;
}

__attribute__((visibility("default")))
int _ZN13BackupManager22Bkup_Read_Setting_AttrEiiPv(int slot, int attr_id, void* out_val) {
    if (!orig_Bkup_Read_Attr) {
        if (g_base_libobj == 0) find_lib_base("libObj.so", &g_base_libobj);
        if (g_base_libobj == 0) g_base_libobj = 0x06592000;
        orig_Bkup_Read_Attr = (int (*)(int, int, void*))(g_base_libobj + 0x1681f0 + 1);
    }
    int ret = orig_Bkup_Read_Attr ? orig_Bkup_Read_Attr(slot, attr_id, out_val) : -1;
    if (attr_id == 0x1070012 || attr_id == 0x10703b2) {
        if (out_val) *(unsigned char*)out_val = 2; // Force 3:2 Open Gate
    }
    return ret;
}

__attribute__((visibility("default")))
int _ZN13BackupManager10Bkup_WriteEiPKv(int attr_id, const void* in_val) {
    if (!orig_Bkup_Write) {
        if (g_base_libobj == 0) find_lib_base("libObj.so", &g_base_libobj);
        if (g_base_libobj == 0) g_base_libobj = 0x06592000;
        orig_Bkup_Write = (int (*)(int, const void*))(g_base_libobj + 0x16827c + 1);
    }
    if (attr_id == 0x1070012 || attr_id == 0x10703b2) {
        unsigned char val = 2; // Prevent clamping to 16:9
        return orig_Bkup_Write ? orig_Bkup_Write(attr_id, &val) : 0;
    }
    return orig_Bkup_Write ? orig_Bkup_Write(attr_id, in_val) : -1;
}

__attribute__((visibility("default")))
int _ZN13BackupManager23Bkup_Write_Setting_AttrEiiPKv(int slot, int attr_id, const void* in_val) {
    if (!orig_Bkup_Write_Attr) {
        if (g_base_libobj == 0) find_lib_base("libObj.so", &g_base_libobj);
        if (g_base_libobj == 0) g_base_libobj = 0x06592000;
        orig_Bkup_Write_Attr = (int (*)(int, int, const void*))(g_base_libobj + 0x168144 + 1);
    }
    if (attr_id == 0x1070012 || attr_id == 0x10703b2) {
        unsigned char val = 2; // Prevent clamping to 16:9
        return orig_Bkup_Write_Attr ? orig_Bkup_Write_Attr(slot, attr_id, &val) : 0;
    }
    return orig_Bkup_Write_Attr ? orig_Bkup_Write_Attr(slot, attr_id, in_val) : -1;
}

__attribute__((constructor))
void opengate_init(void) {
    if (!is_target_process()) {
        return;
    }
    apply_all_patches();
}
