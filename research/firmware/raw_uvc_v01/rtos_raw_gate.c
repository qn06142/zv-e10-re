/* Guarded live helper for RTOS MemAreaMSDebug_RAW gate and /proc/self/mem slack stub setup.
 * Performs strict av-cam.bin "LIRO" header verification at PA 0x035c6000 before any RTOS read/write.
 */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

extern int open(const char *, int, ...), close(int), read(int, void *, unsigned), write(int, const void *, unsigned);
extern int printf(const char *, ...), strcmp(const char *, const char *), memcmp(const void *, const void *, unsigned);
extern int getpagesize(void), munmap(void *, unsigned);
extern void *mmap(void *, unsigned, int, int, int, long), *memcpy(void *, const void *, unsigned);
extern unsigned long strtoul(const char *, char **, int);
extern int *__errno_location(void);

#define O_RDONLY 0
#define O_RDWR 2
#define O_WRONLY 1
#define O_CREAT 64
#define O_TRUNC 512
#define O_SYNC 04010000

/* Verified addresses in av-cam.bin (base 0x635c6000 -> PA = VA - 0x60000000) */
#define PA_RTOS_BASE   0x035c6000u
#define PA_DBG_GLOBAL  0x044b8f11u  /* 0x6396e358(1): gate requires != 9 */
#define PA_RAW_CFG     0x0451d90du  /* GOT[0xa2f4] */
#define PA_RAW_PROFILE 0x0451d9fdu  /* +0xf0 */
#define PA_RAW_TAG1    0x0451d9feu  /* +0xf1 */
#define PA_RAW_DECOMP  0x0451da03u  /* +0xf6 */
#define PA_READEND_SW  0x043bf4a4u  /* 0x643bf438 + 0x6c */

static const u8 EXPECTED_RTOS_HDR[16] = {
    0x0a, 0x00, 0x00, 0xea, 0x4f, 0x52, 0x49, 0x4c,
    0x04, 0x00, 0x00, 0x00, 0x44, 0x60, 0x5c, 0x63
};

static int map_phys(u32 pa, u32 len, int rw, void **out_map, u32 *out_len, u8 **out_ptr) {
    int pg = getpagesize();
    if (pg <= 0 || (pg & (pg - 1))) return -1;
    u32 off = pa & (u32)(pg - 1);
    u32 mlen = (off + len + (u32)pg - 1u) & ~((u32)pg - 1u);
    int fd = open("/dev/mem", (rw ? O_RDWR : O_RDONLY) | O_SYNC);
    if (fd < 0) fd = open("/dev/mem", rw ? O_RDWR : O_RDONLY);
    if (fd < 0) return -2;
    void *m = mmap(0, mlen, rw ? 3 : 1, 1, fd, (long)(pa - off));
    close(fd);
    if (m == (void *)-1) return -3;
    *out_map = m;
    *out_len = mlen;
    *out_ptr = (u8 *)m + off;
    return 0;
}

static int verify_rtos_magic(void) {
    void *m = 0; u32 ml = 0; u8 *p = 0;
    int rc = map_phys(PA_RTOS_BASE, 16, 0, &m, &ml, &p);
    if (rc) return rc;
    int match = (memcmp(p, EXPECTED_RTOS_HDR, 16) == 0);
    munmap(m, ml);
    return match ? 0 : -4;
}

static int cmd_status(void) {
    int rc = verify_rtos_magic();
    if (rc) {
        printf("RTOS_FINGERPRINT_FAILED rc=%d\n", rc);
        return 1;
    }
    void *m1 = 0, *m2 = 0, *m3 = 0;
    u32 l1 = 0, l2 = 0, l3 = 0;
    u8 *p1 = 0, *p2 = 0, *p3 = 0;
    if (map_phys(PA_DBG_GLOBAL, 4, 0, &m1, &l1, &p1)) return 2;
    if (map_phys(PA_RAW_PROFILE, 8, 0, &m2, &l2, &p2)) { munmap(m1, l1); return 2; }
    if (map_phys(PA_READEND_SW, 4, 0, &m3, &l3, &p3)) { munmap(m2, l2); munmap(m1, l1); return 2; }
    printf("RTOS_HDR=OK (LIRO @ %08x)\n", PA_RTOS_BASE);
    printf("DBG_GLOBAL(%08x)=0x%02x (gate %s)\n", PA_DBG_GLOBAL, p1[0], (p1[0] != 9) ? "OPEN" : "CLOSED(9)");
    printf("RAW_CFG_F0_F6(%08x)=%02x %02x %02x %02x %02x %02x %02x\n",
           PA_RAW_PROFILE, p2[0], p2[1], p2[2], p2[3], p2[4], p2[5], p2[6]);
    printf("READEND_SW(%08x)=0x%02x\n", PA_READEND_SW, p3[0]);
    munmap(m3, l3);
    munmap(m2, l2);
    munmap(m1, l1);
    return 0;
}

static int cmd_set_raw(u8 dbg_val, u8 tag1_val, u8 decomp_val) {
    int rc = verify_rtos_magic();
    if (rc) {
        printf("RTOS_FINGERPRINT_FAILED rc=%d\n", rc);
        return 1;
    }
    void *m1 = 0, *m2 = 0;
    u32 l1 = 0, l2 = 0;
    u8 *p1 = 0, *p2 = 0;
    if (map_phys(PA_DBG_GLOBAL, 4, 1, &m1, &l1, &p1)) return 2;
    if (map_phys(PA_RAW_PROFILE, 8, 1, &m2, &l2, &p2)) { munmap(m1, l1); return 2; }

    u8 prev_dbg = p1[0];
    u8 prev_tag1 = p2[1];
    u8 prev_decomp = p2[6];
    p1[0] = dbg_val;
    p2[1] = tag1_val;
    p2[6] = decomp_val;
    __asm__ volatile("dmb sy" ::: "memory");
    u8 now_dbg = p1[0];
    u8 now_tag1 = p2[1];
    u8 now_decomp = p2[6];
    munmap(m2, l2);
    munmap(m1, l1);
    printf("RTOS_RAW_GATE_UPDATED dbg:%02x->%02x tag1:%02x->%02x decomp:%02x->%02x\n",
           prev_dbg, now_dbg, prev_tag1, now_tag1, prev_decomp, now_decomp);
    return (now_dbg == dbg_val && now_tag1 == tag1_val && now_decomp == decomp_val) ? 0 : 3;
}

static int cmd_dump(u32 pa, u32 len, const char *path) {
    if (!len || len > 64u * 1024u * 1024u || pa >= 0x40000000u || len > 0x40000000u - pa) return 1;
    void *m = 0; u32 ml = 0; u8 *p = 0;
    if (map_phys(pa, len, 0, &m, &ml, &p)) return 2;
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) { munmap(m, ml); return 3; }
    u32 off = 0;
    while (off < len) {
        u32 chunk = len - off;
        if (chunk > 65536u) chunk = 65536u;
        int w = write(fd, p + off, chunk);
        if (w <= 0) { close(fd); munmap(m, ml); return 4; }
        off += (u32)w;
    }
    close(fd);
    munmap(m, ml);
    printf("DUMPED pa=%08x len=%u -> %s\n", pa, len, path);
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        printf("usage: rtos_raw_gate status | enable | disable | dump PA_HEX LEN_HEX OUTFILE\n");
        return 1;
    }
    if (!strcmp(argv[1], "status")) return cmd_status();
    if (!strcmp(argv[1], "enable")) return cmd_set_raw(1, 1, 0);
    if (!strcmp(argv[1], "disable")) return cmd_set_raw(9, 0, 0);
    if (!strcmp(argv[1], "dump") && argc == 5) {
        return cmd_dump((u32)strtoul(argv[2], 0, 16), (u32)strtoul(argv[3], 0, 16), argv[4]);
    }
    printf("UNKNOWN_CMD\n");
    return 1;
}
