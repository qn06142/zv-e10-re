#include "capture.h"
extern int open(const char *, int, ...), close(int), write(int, const void *, unsigned), fsync(int);
extern int mkdir(const char *, unsigned), getpagesize(void), munmap(void *, unsigned);
extern int unlink(const char *);
extern void *mmap(void *, unsigned, int, int, int, long);
extern int *__errno_location(void);

static const char bin[]  = "/log/raw_capture_v01/frame.bin";
static const char meta[] = "/log/raw_capture_v01/request.bin";
static const char done[] = "/log/raw_capture_v01/complete.bin";

static int full(int fd, const void *p, unsigned n) {
    const unsigned char *b = p;
    while (n) {
        int w = write(fd, b, n > 65536u ? 65536u : n);
        if (w < 0 && *__errno_location() == 4) continue;
        if (w <= 0 || (unsigned)w > n) return -1;
        b += w;
        n -= (unsigned)w;
    }
    return 0;
}

static int seal(int fd) {
    int e = fsync(fd);
    int c = close(fd);
    return (e || c) ? -1 : 0;
}

/* O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW = 1|64|128|131072 (ARM Linux) */
static int exclusive(const char *p) {
    return open(p, 1 | 64 | 128 | 131072, 0600);
}

static int save(const raw_packet *p) {
    int pg = getpagesize();
    if (pg <= 0 || (pg & (pg - 1))) return -1;
    unsigned delta = p->address & (unsigned)(pg - 1), n = p->bytes + delta;
    if (n < p->bytes) return -1;
    int mem = open("/dev/mem", 0);
    if (mem < 0) return -1;
    void *map = mmap(0, n, 1, 1, mem, (long)(p->address - delta));
    int mc = close(mem);
    if (map == (void *)-1) return -1;
    int ok = -1, fd = -1;
    if (mc) goto finish;
    if (mkdir("/log/raw_capture_v01", 0700) && *__errno_location() != 17) goto finish;
    fd = exclusive(meta);
    if (fd < 0) goto finish;
    int w = full(fd, p, sizeof(*p)), s = seal(fd);
    fd = -1;
    if (w || s) goto finish;
    fd = exclusive(bin);
    if (fd < 0) goto finish;
    w = full(fd, (const unsigned char *)map + delta, p->bytes);
    s = seal(fd);
    fd = -1;
    if (w || s) goto finish;
    fd = exclusive(done);
    if (fd < 0) goto finish;
    w = full(fd, p, sizeof(*p));
    s = seal(fd);
    fd = -1;
    if (!w && !s) ok = 0;
finish:
    if (fd >= 0) close(fd);
    if (munmap(map, n)) ok = -1;
    return ok;
}

__attribute__((visibility("default"))) int raw_v01_bind(void *original) {
    const raw_ops o = { save };
    return raw_bind((raw_original)original, &o);
}
__attribute__((visibility("default"))) int raw_v01_arm(void) { return raw_arm(1); }
__attribute__((visibility("default"))) int raw_v01_rearm(void) { return raw_rearm(1); }
__attribute__((visibility("default"))) unsigned raw_v01_status(void) { return raw_status(); }
__attribute__((visibility("default"))) int raw_v01_dispatch(void *self, const raw_packet *p) {
    return raw_dispatch(self, p);
}
