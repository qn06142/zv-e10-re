/* Generates before/after blobs from live /proc/<pid>/maps for checked_mempatch.elf.
 * Usage: prep_saver_stub <pid> <out_dir>
 */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

extern int open(const char *, int, ...), close(int), read(int, void *, unsigned), write(int, const void *, unsigned);
extern long lseek(int, long, int);
extern int printf(const char *, ...), snprintf(char *, unsigned, const char *, ...), sscanf(const char *, const char *, ...);
extern int memcmp(const void *, const void *, unsigned);
extern void *memset(void *, int, unsigned), *memcpy(void *, const void *, unsigned);
extern char *strstr(const char *, const char *), *strchr(const char *, int);
extern unsigned long strtoul(const char *, char **, int);

#define STUB_OFF   0x2800u
#define SLOT_OFF   0xa18cu
#define LAZY_OFF   0x1108u
#define FN_OFF     0x1af5u
#define DLOPEN_OFF 0x0bb1u
#define DLSYM_OFF  0x0c49u

static const u8 WRITER_GUARD[16] = {
    45, 233, 240, 71, 168, 176, 2, 175, 5, 70, 12, 70, 255, 247, 4, 236
};
static const u8 THREAD_GUARD[16] = {
    45, 233, 240, 67, 131, 176, 5, 70, 0, 175, 137, 70, 57, 29, 79, 240
};

/* Compiled Thumb-2 PIC lazy stub (padded to 144 bytes by build.py via Keystone):
 * On entry: r0=self, r1=wire, lr=caller
 * Calls raw_v01_lazy_entry(saver_base, self, wire) if dlopen/dlsym succeed, else original_fn(self, wire).
 */
/* STUB_TEMPLATE_START */
static const u8 STUB_TEMPLATE[144] = {0};
/* STUB_TEMPLATE_END */

static int find_base(int pid, const char *needle, u32 *out) {
    char p[64];
    static char buf[131072];
    snprintf(p, sizeof(p), "/proc/%d/maps", pid);
    int fd = open(p, 0);
    if (fd < 0) return -1;
    int n = 0, r;
    while (n < (int)sizeof(buf) - 1 && (r = read(fd, buf + n, (unsigned)(sizeof(buf) - 1 - n))) > 0) n += r;
    close(fd);
    if (n <= 0) return -2;
    buf[n] = 0;
    char *line = buf;
    while (line && *line) {
        char *nl = strchr(line, '\n');
        if (nl) *nl = 0;
        if (strstr(line, needle) && strstr(line, "r-xp")) {
            u32 base = 0;
            if (sscanf(line, "%x", &base) == 1) { *out = base; return 0; }
        }
        if (!nl) break;
        line = nl + 1;
    }
    return -3;
}

static int write_bin(const char *dir, const char *name, const void *data, unsigned len) {
    char p[160];
    snprintf(p, sizeof(p), "%s/%s", dir, name);
    int fd = open(p, 1 | 64 | 512, 0644);
    if (fd < 0) return -1;
    int w = write(fd, data, len);
    close(fd);
    return (w == (int)len) ? 0 : -2;
}

static void w32(u8 *p, u32 v) {
    p[0] = (u8)v; p[1] = (u8)(v >> 8); p[2] = (u8)(v >> 16); p[3] = (u8)(v >> 24);
}

int main(int argc, char **argv) {
    if (argc != 3) {
        printf("usage: prep_saver_stub PID OUT_DIR\n");
        return 1;
    }
    int pid = (int)strtoul(argv[1], 0, 10);
    const char *out = argv[2];
    u32 sb = 0, dl = 0;
    if (find_base(pid, "/usr/lib/CameraOnDemandSaver.so", &sb) ||
        find_base(pid, "libdl-2.11.2.so", &dl)) {
        printf("FIND_BASE_FAILED sb=%08x dl=%08x\n", sb, dl);
        return 2;
    }
    char memp[64];
    snprintf(memp, sizeof(memp), "/proc/%d/mem", pid);
    int mfd = open(memp, 0);
    if (mfd < 0) { printf("OPEN_MEM_FAILED\n"); return 3; }

    u8 wg[16], tg[16], zeros[144], slot_buf[4];
    if (lseek(mfd, (long)(sb + 0x1af4u), 0) != (long)(sb + 0x1af4u) || read(mfd, wg, 16) != 16 || memcmp(wg, WRITER_GUARD, 16) ||
        lseek(mfd, (long)(sb + 0x1c8cu), 0) != (long)(sb + 0x1c8cu) || read(mfd, tg, 16) != 16 || memcmp(tg, THREAD_GUARD, 16)) {
        close(mfd);
        printf("GUARD_MISMATCH sb=%08x\n", sb);
        return 4;
    }
    if (lseek(mfd, (long)(sb + STUB_OFF), 0) != (long)(sb + STUB_OFF) || read(mfd, zeros, 144) != 144) {
        close(mfd);
        printf("SLACK_READ_FAILED\n");
        return 5;
    }
    for (int i = 0; i < 144; i++) {
        if (zeros[i] != 0) {
            close(mfd);
            printf("SLACK_NOT_ZERO at +%x\n", i);
            return 6;
        }
    }
    if (lseek(mfd, (long)(sb + SLOT_OFF), 0) != (long)(sb + SLOT_OFF) || read(mfd, slot_buf, 4) != 4) {
        close(mfd);
        printf("SLOT_READ_FAILED\n");
        return 7;
    }
    close(mfd);

    u32 cur_slot = (u32)slot_buf[0] | ((u32)slot_buf[1] << 8) | ((u32)slot_buf[2] << 16) | ((u32)slot_buf[3] << 24);
    if (cur_slot != sb + FN_OFF && cur_slot != sb + LAZY_OFF) {
        printf("UNEXPECTED_SLOT %08x (sb=%08x)\n", cur_slot, sb);
        return 8;
    }

    u8 stub[144];
    memset(stub, 0, sizeof(stub));
    memcpy(stub, STUB_TEMPLATE, 0x78u);
    w32(stub + 0x44, sb);
    w32(stub + 0x48, dl + DLOPEN_OFF);
    w32(stub + 0x4c, dl + DLSYM_OFF);
    w32(stub + 0x50, sb + FN_OFF);
    memcpy(stub + 0x78, "raw_v01_lazy_entry\0", 19);

    u8 new_slot[4];
    w32(new_slot, sb + STUB_OFF + 1u);

    if (write_bin(out, "stub-before.bin", zeros, 144) ||
        write_bin(out, "stub-after.bin", stub, 144) ||
        write_bin(out, "slot-before.bin", slot_buf, 4) ||
        write_bin(out, "slot-after.bin", new_slot, 4)) {
        printf("WRITE_BLOB_FAILED\n");
        return 9;
    }
    printf("SAVER_BASE=%08x DL_BASE=%08x STUB_AT=%08x SLOT_AT=%08x CUR_SLOT=%08x NEW_SLOT=%08x\n",
           sb, dl, sb + STUB_OFF, sb + SLOT_OFF, cur_slot, sb + STUB_OFF + 1u);
    return 0;
}
