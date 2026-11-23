#include "capture.h"
#include "guards.h"

extern void *dlopen(const char *, int), *dlsym(void *, const char *);
extern int mprotect(void *, unsigned, int), getpagesize(void), memcmp(const void *, const void *, unsigned);
extern int raw_v01_bind(void *), raw_v01_dispatch(void *, const raw_packet *), raw_v01_arm(void);

static void *self_pin, *native_pin;
static volatile unsigned lazy_init_lock;

__attribute__((visibility("default"))) int raw_v01_install(unsigned base) {
    if (!base || (base & 4095u) || base > 0xffffffffu - 0xa190u || raw_status()) return -1;
    if (memcmp((void *)(base + 0x1af4u), writer_guard, 16) ||
        memcmp((void *)(base + 0x1c8cu), thread_guard, 16))
        return -2;
    native_pin = dlopen("/usr/lib/CameraOnDemandSaver.so", 6);
    if (!native_pin) return -3;
    void *fn = dlsym(native_pin,
        "_ZN18CAM_ONDEMAND_SAVER18cam_ondemand_saver10fsys_writeEPN6Camera11UTIL_MS_MGR31cam_util_ms_mgr_snd_msg_payloadE");
    if ((unsigned)fn != base + 0x1af5u) return -4;
    unsigned *slot = (unsigned *)(base + 0xa18cu);
    unsigned old = __atomic_load_n(slot, __ATOMIC_ACQUIRE);
    if (old != (unsigned)fn && old != base + LAZY_OFFSET && old != (base + STUB_OFFSET + 1u))
        return -5;
    self_pin = dlopen("/log/raw_uvc_v01/raw_capture_v01.so", 6);
    if (!self_pin) self_pin = dlopen("/usr/lib/raw_capture_v01.so", 6);
    if (!self_pin) return -6;
    int pg = getpagesize();
    if (pg <= 0 || (pg & (pg - 1))) return -7;
    if (mprotect((void *)((unsigned)slot & ~((unsigned)pg - 1u)), (unsigned)pg, 3)) return -8;
    if (raw_v01_bind(fn)) return -9;
    __atomic_store_n(slot, (unsigned)raw_v01_dispatch, __ATOMIC_RELEASE);
    return 0;
}

/* Safe lazy entry invoked from CameraOnDemandSaver worker thread on first fsys_write call.
 * Installs hook once, arms tag=1, and immediately dispatches the triggering packet. */
__attribute__((visibility("default"))) int raw_v01_lazy_entry(unsigned base, void *self, const raw_packet *p) {
    if (!raw_status()) {
        if (__sync_bool_compare_and_swap(&lazy_init_lock, 0u, 1u)) {
            int rc = raw_v01_install(base);
            if (!rc) (void)raw_v01_arm();
        }
    }
    if (!raw_status()) {
        raw_original orig = (raw_original)(base + 0x1af5u);
        return orig(self, p);
    }
    return raw_v01_dispatch(self, p);
}
