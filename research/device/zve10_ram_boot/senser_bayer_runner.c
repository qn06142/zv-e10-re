/* SPDX-License-Identifier: GPL-2.0 */
#include <stdint.h>
#include "bayer_sensor_tables.h"

#define BAYER_DST_PA       0x25200000U
#define BAYER_DST_MAP_SIZE 0x00500000U
#define BAYER_M37_WIDTH    6048U
#define BAYER_M37_HEIGHT   360U
#define BAYER_M37_BYTES    (BAYER_M37_WIDTH * BAYER_M37_HEIGHT * 2U)

_Static_assert(BAYER_M37_BYTES <= BAYER_DST_MAP_SIZE, "still strip does not fit the DMA mapping");

#define SEQ_PORT           0xfc088300U
#define SEQ_RUN            0xfc088e00U
#define SEQ_IRQ            0xfc088f00U
#define RDCW0_BASE         0xfc0a9200U
#define ISP0_AIF3_BASE     0xf3002380U
#define TIMER_READ_PA      0xf240310cU
#define BAYER_PSAVE_DDRC_B 0xf0105000U
#define PMU_BASE_PA        0xf290e000U

#define SYS_exit           1U
#define SYS_write          4U
#define SYS_open           5U
#define SYS_close          6U
#define SYS_nanosleep      162U
#define SYS_mmap2          192U

#define O_RDWR_SYNC        (2U | 0x101000U)
#define O_WR_CREATE_TRUNC  (1U | 0x40U | 0x200U)
#define PROT_RW            3U
#define MAP_SHARED         1U

struct linux_timespec {
    long tv_sec;
    long tv_nsec;
};

struct mmio_region {
    uint32_t pa_base;
    uint32_t size;
    volatile uint8_t *va;
};

static struct mmio_region regions[8];
static uint32_t seq_irqs = 0U;
static uint32_t seq_timeouts = 0U;

void *memset(void *dst, int c, unsigned int n) {
    volatile uint8_t *p = (volatile uint8_t *)dst;
    uint8_t b = (uint8_t)c;
    for (unsigned int i = 0U; i < n; ++i) {
        p[i] = b;
    }
    return dst;
}

static inline int32_t sys_call1(uint32_t nr, uint32_t a0) {
    register uint32_t r0 __asm__("r0") = a0;
    register uint32_t r7 __asm__("r7") = nr;
    __asm__ volatile("svc #0" : "+r"(r0) : "r"(r7) : "memory");
    return (int32_t)r0;
}

static inline int32_t sys_call2(uint32_t nr, uint32_t a0, uint32_t a1) {
    register uint32_t r0 __asm__("r0") = a0;
    register uint32_t r1 __asm__("r1") = a1;
    register uint32_t r7 __asm__("r7") = nr;
    __asm__ volatile("svc #0" : "+r"(r0) : "r"(r1), "r"(r7) : "memory");
    return (int32_t)r0;
}

static inline int32_t sys_call3(uint32_t nr, uint32_t a0, uint32_t a1, uint32_t a2) {
    register uint32_t r0 __asm__("r0") = a0;
    register uint32_t r1 __asm__("r1") = a1;
    register uint32_t r2 __asm__("r2") = a2;
    register uint32_t r7 __asm__("r7") = nr;
    __asm__ volatile("svc #0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory");
    return (int32_t)r0;
}

static inline int32_t sys_call6(uint32_t nr, uint32_t a0, uint32_t a1, uint32_t a2,
                                uint32_t a3, uint32_t a4, uint32_t a5) {
    register uint32_t r0 __asm__("r0") = a0;
    register uint32_t r1 __asm__("r1") = a1;
    register uint32_t r2 __asm__("r2") = a2;
    register uint32_t r3 __asm__("r3") = a3;
    register uint32_t r4 __asm__("r4") = a4;
    register uint32_t r5 __asm__("r5") = a5;
    register uint32_t r7 __asm__("r7") = nr;
    __asm__ volatile("svc #0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r3), "r"(r4), "r"(r5), "r"(r7) : "memory");
    return (int32_t)r0;
}

static uint32_t write_all(int32_t fd, const void *buf, uint32_t len) {
    const uint8_t *p = (const uint8_t *)buf;
    uint32_t sent = 0U;
    while (sent < len) {
        int32_t n = sys_call3(SYS_write, (uint32_t)fd, (uint32_t)(uintptr_t)(p + sent), len - sent);
        if (n <= 0) {
            break;
        }
        sent += (uint32_t)n;
    }
    return sent;
}

static void prints(const char *s) {
    uint32_t n = 0U;
    while (s[n]) {
        ++n;
    }
    write_all(1, s, n);
}

static void print_hex8(uint32_t v) {
    static const char hex[] = "0123456789abcdef";
    char buf[8];
    for (uint32_t i = 0U; i < 8U; ++i) {
        buf[i] = hex[(v >> (28U - i * 4U)) & 15U];
    }
    write_all(1, buf, 8U);
}

static void print_dec(uint32_t v) {
    char buf[12];
    uint32_t pos = 0U;
    if (v == 0U) {
        prints("0");
        return;
    }
    while (v > 0U) {
        buf[pos++] = (char)('0' + (v % 10U));
        v /= 10U;
    }
    for (uint32_t i = 0U; i < pos / 2U; ++i) {
        char tmp = buf[i];
        buf[i] = buf[pos - 1U - i];
        buf[pos - 1U - i] = tmp;
    }
    write_all(1, buf, pos);
}

static uint32_t udiv64_32(uint64_t num, uint32_t den) {
    uint64_t rem = 0ULL;
    uint32_t quot = 0U;
    if (den == 0U) {
        return 0U;
    }
    for (int i = 63; i >= 0; --i) {
        rem = (rem << 1) | ((num >> i) & 1ULL);
        if (rem >= den) {
            rem -= den;
            if (i < 32) {
                quot |= (1U << i);
            }
        }
    }
    return quot;
}

static void die(const char *msg, int32_t err) {
    prints("ERR: ");
    prints(msg);
    prints(" rc=0x");
    print_hex8((uint32_t)err);
    prints("\n");
    sys_call1(SYS_exit, 1U);
}

static int str_eq(const char *a, const char *b) {
    while (*a && *b && *a == *b) {
        ++a;
        ++b;
    }
    return *a == '\0' && *b == '\0';
}

static inline void dsb(void) {
    __asm__ volatile("dsb sy" ::: "memory");
}

static void delay_us(uint32_t us) {
    struct linux_timespec req;
    req.tv_sec = (long)(us / 1000000U);
    req.tv_nsec = (long)((us % 1000000U) * 1000U);
    sys_call2(SYS_nanosleep, (uint32_t)(uintptr_t)&req, 0U);
}

static void init_regions(int32_t fd) {
    static const uint32_t cfg[8][2] = {
        { 0xf2403000U, 0x00001000U },
        { 0xf2900000U, 0x00040000U },
        { 0xf2a00000U, 0x00040000U },
        { 0xf3122000U, 0x00002000U },
        { 0xfc000000U, 0x00100000U },
        { BAYER_DST_PA, BAYER_DST_MAP_SIZE },
        { BAYER_PSAVE_DDRC_B, 0x00001000U },
        { 0xf3000000U, 0x00040000U },
    };
    for (uint32_t i = 0U; i < 8U; ++i) {
        uint32_t pa = cfg[i][0];
        uint32_t sz = cfg[i][1];
        int32_t va = sys_call6(SYS_mmap2, 0U, sz, PROT_RW, MAP_SHARED, (uint32_t)fd, pa >> 12);
        if (va < 0 && va >= -4095) {
            prints("mmap fail pa=0x");
            print_hex8(pa);
            prints(" ");
            die("mmap2", va);
        }
        regions[i].pa_base = pa;
        regions[i].size = sz;
        regions[i].va = (volatile uint8_t *)(uintptr_t)(uint32_t)va;
    }
}

static volatile uint32_t *reg_ptr(uint32_t pa) {
    for (uint32_t i = 0U; i < 8U; ++i) {
        if (i == 5U) {
            continue;
        }
        if (pa >= regions[i].pa_base && (pa - regions[i].pa_base) <= (regions[i].size - 4U)) {
            return (volatile uint32_t *)(regions[i].va + (pa - regions[i].pa_base));
        }
    }
    prints("unmapped pa=0x");
    print_hex8(pa);
    prints("\n");
    sys_call1(SYS_exit, 2U);
    return (volatile uint32_t *)0;
}

static inline uint32_t r32(uint32_t pa) {
    return *reg_ptr(pa);
}

static inline void w32(uint32_t pa, uint32_t val) {
    *reg_ptr(pa) = val;
}

static void write_table(const struct bayer_reg_op *ops, uint32_t count, uint32_t patch_dst_pa) {
    for (uint32_t i = 0U; i < count; ++i) {
        uint32_t addr = ops[i].addr;
        uint32_t val = (addr == BAYER_RDCW0_BASE_REG && patch_dst_pa) ? patch_dst_pa : ops[i].value;
        w32(addr, val);
    }
    dsb();
}

#define WRITE_TABLE(tbl, dst) write_table((tbl), (uint32_t)(sizeof(tbl) / sizeof((tbl)[0])), (dst))

static void seq_ack(void) {
    w32(SEQ_IRQ + 4U, 1U);
    dsb();
}

static void seq_irq_enable(uint32_t enable) {
    seq_ack();
    uint32_t mask = r32(SEQ_IRQ + 8U);
    w32(SEQ_IRQ + 8U, enable ? (mask | 1U) : (mask & ~1U));
    dsb();
}

static void seq_run(uint32_t mode) {
    w32(SEQ_RUN, mode);
    dsb();
    if (mode == 2U) {
        delay_us(10U);
        w32(SEQ_RUN + 8U, 1U);
        dsb();
        delay_us(10U);
        w32(SEQ_RUN + 8U, 0U);
        dsb();
        delay_us(10U);
        w32(SEQ_RUN + 8U, 1U);
        dsb();
    }
}

static void seq_wait_irq(uint32_t timeout_us) {
    uint32_t t0 = r32(TIMER_READ_PA);
    uint32_t limit_ticks = timeout_us * 2U;
    for (uint32_t spin = 0U; spin < 20000000U; ++spin) {
        if ((r32(SEQ_IRQ) | r32(SEQ_IRQ + 4U)) & 1U) {
            seq_ack();
            w32(SEQ_RUN, 2U);
            dsb();
            seq_irqs++;
            return;
        }
        if ((uint32_t)(r32(TIMER_READ_PA) - t0) >= limit_ticks) {
            break;
        }
    }
    seq_timeouts++;
}

static void run_seq_burst(const uint8_t *bytes, uint32_t count, uint32_t run_mode, int wait_irq) {
    uint32_t prev = seq_irqs;
    w32(SEQ_PORT + 4U, r32(SEQ_PORT + 4U) & ~1U);
    w32(SEQ_PORT + 8U, (r32(SEQ_PORT + 8U) & ~7U) | 3U);
    w32(SEQ_RUN, 2U);
    w32(SEQ_PORT, r32(SEQ_PORT) | 1U);
    dsb();

    w32(SEQ_PORT + 12U, r32(SEQ_PORT + 12U) & ~255U);
    for (uint32_t i = 0U; i < count; ++i) {
        w32(SEQ_PORT + 0x40U + i * 4U, bytes[i]);
    }
    dsb();

    seq_run(run_mode);
    if (wait_irq) {
        seq_wait_irq(100000U);
        if (run_mode == 2U && seq_irqs == prev) {
            seq_run(0U);
            seq_wait_irq(100000U);
        }
    }
}

static void print_poll_sample(uint32_t idx) {
    prints("S");
    print_dec(idx);
    prints(" W0=");
    print_hex8(r32(RDCW0_BASE + 4U));
    prints(" C=");
    print_hex8(r32(RDCW0_BASE + 0x10U));
    prints(" ERR=");
    print_hex8(r32(RDCW0_BASE + 8U));
    prints(" I=");
    print_dec(seq_irqs);
    prints(" T=");
    print_dec(seq_timeouts);
    prints(" SQ=");
    print_hex8(r32(SEQ_PORT));
    prints(":");
    print_hex8(r32(SEQ_RUN));
    prints(":");
    print_hex8(r32(SEQ_IRQ + 4U));
    prints(" SL=");
    print_hex8(r32(0xfc0f0000U));
    prints(":");
    print_hex8(r32(0xfc0f0050U));
    prints(":");
    print_hex8(r32(0xfc029028U));
    prints(" DF=");
    print_hex8(r32(0xfc0a0014U));
    prints(":");
    print_hex8(r32(0xfc0a002cU));
    prints(" ST=");
    print_hex8(r32(0xfc02a040U));
    prints(":");
    print_hex8(r32(0xfc0a1110U));
    prints(":");
    print_hex8(r32(0xfc0a1210U));
    prints(":");
    print_hex8(r32(0xfc098808U));
    prints(" R=");
    print_hex8(r32(SEQ_IRQ));
    prints("\n");
}

static void dump_reg_list(const char *tag, const char *label, const uint32_t *addrs, uint32_t count) {
    prints(tag);
    prints(" ");
    prints(label);
    for (uint32_t i = 0U; i < count; ++i) {
        prints(" ");
        print_hex8(r32(addrs[i]));
    }
    prints("\n");
}

static uint32_t slv_p0[0xc0U];

static void dump_nonzero_range(const char *tag, const char *label, uint32_t start, uint32_t end) {
    prints(tag);
    prints(" ");
    prints(label);
    for (uint32_t a = start; a <= end; a += 4U) {
        uint32_t v = r32(a);
        if (v != 0U) {
            prints(" ");
            print_hex8(a);
            prints("=");
            print_hex8(v);
        }
    }
    prints("\n");
}

static void dump_regs_bin(const char *path) {
    static const uint32_t ranges[][2] = {
        {0xf2900000U, 0x0100U}, {0xf290e000U, 0x0040U}, {0xf2910000U, 0x0080U},
        {0xf2910a00U, 0x0050U}, {0xf2911200U, 0x0060U}, {0xf2912000U, 0x0080U},
        {0xf2912a00U, 0x0080U}, {0xf2913200U, 0x0060U}, {0xf2914000U, 0x0040U},
        {0xf2915100U, 0x0060U}, {0xf292a000U, 0x0100U}, {0xf292b000U, 0x0040U},
        {0xf292e000U, 0x0050U}, {0xf2931000U, 0x0180U}, {0xf2932000U, 0x0100U},
        {0xf2932400U, 0x0020U}, {0xf2a00000U, 0x0100U}, {0xf2a01000U, 0x01a0U},
        {0xf2a10000U, 0x0040U}, {0xf2a11000U, 0x0180U}, {0xf2a12000U, 0x0180U},
        {0xf2a20000U, 0x0040U}, {0xf2a21000U, 0x0140U}, {0xf2a22000U, 0x0120U},
        {0xf2a30000U, 0x0100U}, {0xf2a31000U, 0x01c0U}, {0xf2a32000U, 0x01c0U},
        {0xfc01c000U, 0x0200U}, {0xfc01e000U, 0x0040U}, {0xfc01e100U, 0x0080U},
        {0xfc01f000U, 0x0200U}, {0xfc020000U, 0x0200U}, {0xfc021000U, 0x0100U},
        {0xfc029000U, 0x0080U}, {0xfc02a000U, 0x0100U}, {0xfc02b000U, 0x0040U},
        {0xfc02bc00U, 0x0040U}, {0xfc02c000U, 0x0220U}, {0xfc02c800U, 0x0060U},
        {0xfc02cf00U, 0x0060U}, {0xfc02d000U, 0x0080U}, {0xfc030000U, 0x0040U},
        {0xfc080000U, 0x0140U}, {0xfc098000U, 0x0040U}, {0xfc098200U, 0x0100U},
        {0xfc098800U, 0x0040U}, {0xfc098900U, 0x0040U}, {0xfc099100U, 0x0060U},
        {0xfc0a0000U, 0x0220U}, {0xfc0a0220U, 0x01e0U}, {0xfc0a0400U, 0x0200U},
        {0xfc0a1100U, 0x0100U}, {0xfc0a1200U, 0x0100U}, {0xfc0a1300U, 0x0100U},
        {0xfc0a1400U, 0x0100U}, {0xfc0a1500U, 0x0080U},
        {0xfc010000U, 0x0040U}, {0xfc01f200U, 0x0200U},
        {0xfc088e00U, 0x0040U}, {0xfc099a00U, 0x0040U},
        {0xfc0a3000U, 0x0040U},
        {0xfc0a3200U, 0x0040U}, {0xfc0a3900U, 0x0200U}, {0xfc0a4200U, 0x0040U},
        {0xfc0a4900U, 0x0200U}, {0xfc0a8000U, 0x0200U}, {0xfc0a9000U, 0x0200U},
        {0xfc0a9200U, 0x0100U}, {0xfc0ad600U, 0x0080U}, {0xfc0f0000U, 0x0200U},
    };
    int32_t fd = sys_call3(SYS_open, (uint32_t)(uintptr_t)path, O_WR_CREATE_TRUNC, 0644U);
    if (fd < 0) {
        return;
    }
    uint32_t rec[512];
    for (uint32_t i = 0U; i < (uint32_t)(sizeof(ranges) / sizeof(ranges[0])); ++i) {
        uint32_t cnt = ranges[i][1] >> 2;
        for (uint32_t k = 0U; k < cnt; ++k) {
            uint32_t a = ranges[i][0] + (k << 2);
            rec[2U * k] = a;
            rec[2U * k + 1U] = r32(a);
        }
        write_all(fd, rec, cnt * 8U);
    }
    sys_call1(SYS_close, (uint32_t)fd);
}

static void dump_pipeline(const char *tag) {
    static const uint32_t dfe_addrs[] = {
        0xfc0a0000U, 0xfc0a0010U, 0xfc0a0014U, 0xfc0a0028U, 0xfc0a002cU,
        0xfc0a0500U, 0xfc0a0504U, 0xfc0a0560U, 0xfc0a0564U,
    };
    static const uint32_t sgc_addrs[] = {
        0xfc0a1100U, 0xfc0a1110U, 0xfc0a1200U, 0xfc0a1210U,
        0xfc0a1300U, 0xfc0a1310U, 0xfc0a1400U, 0xfc0a1410U,
    };
    static const uint32_t w0_addrs[] = {
        0xfc0a9200U, 0xfc0a9204U, 0xfc0a9208U, 0xfc0a9210U,
        0xfc0a9220U, 0xfc0a9224U, 0xfc0a9228U, 0xfc0a922cU,
    };
    static const uint32_t fmt_addrs[] = {
        0xfc0a8900U, 0xfc0a8904U, 0xfc0a8908U, 0xfc0a890cU,
        0xfc0a8910U, 0xfc0a8914U, 0xfc0a8918U, 0xfc0a891cU,
        0xfc0a9000U, 0xfc0a9280U, 0xfc0a9284U, 0xfc0a9290U,
    };
    dump_reg_list(tag, "DFE:", dfe_addrs, (uint32_t)(sizeof(dfe_addrs) / sizeof(dfe_addrs[0])));
    dump_reg_list(tag, "SGC:", sgc_addrs, (uint32_t)(sizeof(sgc_addrs) / sizeof(sgc_addrs[0])));
    dump_reg_list(tag, "W0R:", w0_addrs, (uint32_t)(sizeof(w0_addrs) / sizeof(w0_addrs[0])));
    dump_reg_list(tag, "FMT:", fmt_addrs, (uint32_t)(sizeof(fmt_addrs) / sizeof(fmt_addrs[0])));
    if (tag[1] == '0') {
        prints(tag);
        prints(" SLV:");
        for (uint32_t i = 0U; i < 0xc0U; ++i) {
            uint32_t a = 0xfc0f0000U + i * 4U;
            uint32_t v = r32(a);
            slv_p0[i] = v;
            if (a >= 0xfc0f0070U && v != 0U) {
                prints(" ");
                print_hex8(a);
                prints("=");
                print_hex8(v);
            }
        }
        prints("\n");
        dump_nonzero_range(tag, "SL0:", 0xfc0f0000U, 0xfc0f006cU);
        dump_nonzero_range(tag, "TOP:", 0xfc0a0040U, 0xfc0a05fcU);
        dump_nonzero_range(tag, "SIF:", 0xfc0a3000U, 0xfc0a3340U);
        dump_nonzero_range(tag, "W0P:", 0xfc0a8000U, 0xfc0a8930U);
        dump_nonzero_range(tag, "RDC:", 0xfc0a9000U, 0xfc0a91fcU);
        dump_nonzero_range(tag, "AIF:", 0xfc0a9200U, 0xfc0a95fcU);
        dump_nonzero_range(tag, "FOP:", 0xfc0ad600U, 0xfc0ad65cU);
        dump_nonzero_range(tag, "WIN:", 0xfc0a1c00U, 0xfc0a1c7cU);
        dump_nonzero_range(tag, "SG1:", 0xfc0a1200U, 0xfc0a12ccU);
        dump_nonzero_range(tag, "SG2:", 0xfc0a1300U, 0xfc0a13ecU);
        prints(tag);
        prints(" MON:");
        for (uint32_t k = 0U; k < 5U; ++k) {
            if (k > 0U) {
                delay_us(10000U);
            }
            prints(" [");
            print_hex8(r32(0xfc0f00b0U));
            prints("/");
            print_hex8(r32(0xfc0f00b4U));
            prints("/");
            print_hex8(r32(0xfc0f00b8U));
            prints("|");
            print_hex8(r32(0xfc0f01b0U));
            prints("/");
            print_hex8(r32(0xfc0f01b4U));
            prints("/");
            print_hex8(r32(0xfc0f01b8U));
            prints("|");
            print_hex8(r32(0xfc0a0010U));
            prints("]");
        }
        prints("\n");
    } else if (tag[1] == '4') {
        uint32_t chg = 0U;
        prints(tag);
        prints(" SLV_CHG:");
        for (uint32_t i = 0U; i < 0xc0U; ++i) {
            uint32_t a = 0xfc0f0000U + i * 4U;
            uint32_t v = r32(a);
            if (v != slv_p0[i]) {
                prints(" ");
                print_hex8(a);
                prints("=");
                print_hex8(slv_p0[i]);
                prints("->");
                print_hex8(v);
                chg++;
            }
        }
        if (chg == 0U) {
            prints(" (none)");
        }
        prints("\n");
    }
}

static void dump_file(const char *path, const uint8_t *buf, uint32_t len) {
    int32_t fd = sys_call3(SYS_open, (uint32_t)(uintptr_t)path, O_WR_CREATE_TRUNC, 0x1a4U);
    if (fd < 0) {
        prints("WARN: open dump failed rc=0x");
        print_hex8((uint32_t)fd);
        prints("\n");
        return;
    }
    uint32_t written = write_all(fd, buf, len);
    int32_t close_status = sys_call1(SYS_close, (uint32_t)fd);
    if (written != len || close_status != 0) {
        prints("WARN: incomplete RAW dump bytes=");
        print_dec(written);
        prints("\n");
        return;
    }
    prints("SAVED ");
    prints(path);
    prints(" bytes=");
    print_dec(len);
    prints("\n");
}

static uint32_t analyze_and_maybe_dump(const char *dump_path, uint32_t width,
                                      uint32_t height, uint32_t stride) {
    const volatile uint16_t *pix = (const volatile uint16_t *)regions[5].va;
    uint32_t nonzero = 0U;
    uint16_t pmin[4];
    uint16_t pmax[4];
    uint64_t psum[4];
    uint32_t pcnt[4];

    for (uint32_t k = 0U; k < 4U; ++k) {
        pmin[k] = 0xFFFFU;
        pmax[k] = 0U;
        psum[k] = 0ULL;
        pcnt[k] = 0U;
    }

    for (uint32_t y = 0U; y < height; ++y) {
        uint32_t row = y * stride;
        uint32_t ybit = (y & 1U) << 1;
        for (uint32_t x = 0U; x < width; ++x) {
            uint16_t v = pix[row + x];
            uint32_t ph = ybit | (x & 1U);
            if (v != 0U) {
                nonzero++;
            }
            if (v < pmin[ph]) {
                pmin[ph] = v;
            }
            if (v > pmax[ph]) {
                pmax[ph] = v;
            }
            psum[ph] += v;
            pcnt[ph]++;
        }
    }

    prints("PIX nonzero=");
    print_dec(nonzero);
    for (uint32_t k = 0U; k < 4U; ++k) {
        prints(" p");
        print_dec(k);
        prints("=");
        print_dec(pmin[k]);
        prints("/");
        print_dec(udiv64_32(psum[k], pcnt[k]));
        prints("/");
        print_dec(pmax[k]);
    }
    prints("\n");

    if (nonzero > 0U && dump_path) {
        dump_file(dump_path, (const uint8_t *)(uintptr_t)regions[5].va, stride * height * 2U);
    }
    return nonzero;
}

static void clear_dst_buf(void) {
    volatile uint32_t *p = (volatile uint32_t *)regions[5].va;
    uint32_t words = BAYER_LIVE_FRAME_BYTES / 4U;
    for (uint32_t i = 0U; i < words; ++i) {
        p[i] = 0U;
    }
    dsb();
}

static int stop_rdcw0(void) {
    w32(RDCW0_BASE + 4U, r32(RDCW0_BASE + 4U) & ~1U);
    w32(RDCW0_BASE, r32(RDCW0_BASE) & ~1U);
    w32(RDCW0_BASE + 4U, r32(RDCW0_BASE + 4U) | (1U << 30));
    dsb();
    for (uint32_t i = 0U; i < 10000U; ++i) {
        if ((r32(RDCW0_BASE + 4U) & (1U << 31)) == 0U) {
            break;
        }
    }
    if ((r32(RDCW0_BASE + 4U) & (1U << 31)) != 0U) {
        w32(0xfc0a9000U, 4U);
        dsb();
        w32(0xfc0a9000U, 2U);
        dsb();
    }
    return (r32(RDCW0_BASE + 4U) & (1U << 31)) == 0U;
}

static int is_ptr_like(uint32_t v) {
    return (v >= 0xc0000000U && v <= 0xcfffffffU) || (v >= 0x63000000U && v <= 0x64ffffffU);
}

static int run_check(void) {
    const volatile uint32_t *mem = (const volatile uint32_t *)regions[5].va;
    uint32_t nz = 0U;
    uint32_t snap[64];
    uint32_t changed = 0U;
    uint32_t ptr_like = 0U;
    prints("CHECK 25200000:");
    for (uint32_t i = 0U; i < 16U; ++i) {
        uint32_t v = mem[i];
        if (v != 0U) {
            nz++;
        }
        prints(" ");
        print_hex8(v);
    }
    prints("\nREGS");
    static const uint32_t addrs[] = {
        0xf290e004U, 0xf290e008U, 0xfc020028U, 0xfc021024U,
        0xfc029008U, 0xfc029028U, 0xfc088e00U,
        0xfc0a9200U, 0xfc0a9204U, 0xfc0a9210U,
    };
    for (uint32_t i = 0U; i < (uint32_t)(sizeof(addrs) / sizeof(addrs[0])); ++i) {
        prints(" ");
        print_hex8(addrs[i]);
        prints("=");
        print_hex8(r32(addrs[i]));
    }
    for (uint32_t i = 0U; i < 64U; ++i) {
        snap[i] = mem[i * 0x5000U];
    }
    delay_us(50000U);
    for (uint32_t i = 0U; i < 64U; ++i) {
        uint32_t v2 = mem[i * 0x5000U];
        if (v2 != snap[i]) {
            changed++;
        }
        if (is_ptr_like(snap[i]) || is_ptr_like(v2)) {
            ptr_like++;
        }
    }
    prints("\nCHECK_NZ=");
    print_dec(nz);
    prints(" CHECK_CHANGED=");
    print_dec(changed);
    prints(" CHECK_PTR=");
    print_dec(ptr_like);
    prints("\n");
    return (changed > 0U || ptr_like > 0U) ? 2 : 0;
}

static void psave_imager_wake(void) {
    prints("PSAVE_PRE dd68=");
    print_hex8(r32(BAYER_PSAVE_DDRC_B + 0x68U));
    prints(" dd90=");
    print_hex8(r32(BAYER_PSAVE_DDRC_B + 0x90U));
    prints(" dd138=");
    print_hex8(r32(BAYER_PSAVE_DDRC_B + 0x138U));
    prints(" dd148=");
    print_hex8(r32(BAYER_PSAVE_DDRC_B + 0x148U));
    prints("\n");

    for (uint32_t i = 0U; i < 100000U; ++i) {
        if ((r32(BAYER_PSAVE_DDRC_B + 0xa0U) & 0x01000000U) != 0U &&
            (r32(BAYER_PSAVE_DDRC_B + 0xa4U) & 1U) != 0U) {
            break;
        }
    }
    w32(BAYER_PSAVE_DDRC_B + 0x138U, r32(BAYER_PSAVE_DDRC_B + 0x138U) | 0x300U);
    dsb();

    for (uint32_t i = 0U; i < 100000U; ++i) {
        uint32_t st = r32(BAYER_PSAVE_DDRC_B + 0x148U);
        if ((st & 0x20000000U) != 0U && (st & 0x00200000U) != 0U) {
            break;
        }
    }
    w32(BAYER_PSAVE_DDRC_B + 0x14cU, 0x1fffffffU);
    w32(BAYER_PSAVE_DDRC_B + 0x68U, r32(BAYER_PSAVE_DDRC_B + 0x68U) & ~0x10000U);
    dsb();

    w32(BAYER_PSAVE_DDRC_B + 0x218U, 0U);
    w32(BAYER_PSAVE_DDRC_B + 0x118U, 0U);
    dsb();

    w32(BAYER_PSAVE_DDRC_B + 0x90U, 0x26U);
    dsb();
    for (uint32_t i = 0U; i < 100000U; ++i) {
        uint32_t st = r32(BAYER_PSAVE_DDRC_B + 0x148U);
        if ((st & 0x20000000U) != 0U && (st & 0x10U) != 0U) {
            break;
        }
    }
    w32(BAYER_PSAVE_DDRC_B + 0x14cU, 0x1fffffffU);

    uint32_t cfg = r32(BAYER_PSAVE_DDRC_B + 0x138U);
    uint32_t mask = (cfg & 0x20000U) ? 0x3f3f0000U : 0x003f0000U;
    uint32_t want = (cfg & 0x20000U) ? 0x24240000U : 0x00240000U;
    for (uint32_t i = 0U; i < 100000U; ++i) {
        if ((r32(BAYER_PSAVE_DDRC_B + 0x90U) & mask) == want) {
            break;
        }
    }
    dsb();

    w32(PMU_BASE_PA + 0x210U, 0U);
    dsb();
    w32(PMU_BASE_PA + 0x008U, 0U);
    dsb();
    w32(PMU_BASE_PA + 0x004U, 0U);
    dsb();

    prints("PSAVE_POST dd68=");
    print_hex8(r32(BAYER_PSAVE_DDRC_B + 0x68U));
    prints(" dd90=");
    print_hex8(r32(BAYER_PSAVE_DDRC_B + 0x90U));
    prints(" dd138=");
    print_hex8(r32(BAYER_PSAVE_DDRC_B + 0x138U));
    prints(" dd148=");
    print_hex8(r32(BAYER_PSAVE_DDRC_B + 0x148U));
    prints("\n");
}

static int dst_has_nonzero(void) {
    const volatile uint32_t *p = (const volatile uint32_t *)regions[5].va;
    uint32_t words = BAYER_LIVE_FRAME_BYTES / 4U;
    for (uint32_t i = 0U; i < words; ++i) {
        if (p[i] != 0U) {
            return 1;
        }
    }
    return 0;
}

static void print_still_poll_sample(uint32_t idx) {
    prints("M37_S");
    print_dec(idx);
    prints(" AIF=");
    print_hex8(r32(ISP0_AIF3_BASE + 0x00U));
    prints(":");
    print_hex8(r32(ISP0_AIF3_BASE + 0x04U));
    prints(":");
    print_hex8(r32(ISP0_AIF3_BASE + 0x08U));
    prints(" C=");
    print_hex8(r32(ISP0_AIF3_BASE + 0x10U));
    prints(" B=");
    print_hex8(r32(ISP0_AIF3_BASE + 0x20U));
    prints(" SGC=");
    print_hex8(r32(0xfc0a1110U));
    prints(":");
    print_hex8(r32(0xfc0a1210U));
    prints(":");
    print_hex8(r32(0xfc0a1310U));
    prints(":");
    print_hex8(r32(0xfc0a1410U));
    prints(" FOPD=");
    print_hex8(r32(0xfc0ad610U));
    prints(" SL=");
    print_hex8(r32(0xfc0f00b0U));
    prints("/");
    print_hex8(r32(0xfc0f00b4U));
    prints("/");
    print_hex8(r32(0xfc0f00b8U));
    prints(":");
    print_hex8(r32(0xfc0f01b0U));
    prints(" ISP0=");
    print_hex8(r32(0xf3002000U));
    prints(":");
    print_hex8(r32(0xf3002008U));
    prints(" SQ=");
    print_hex8(r32(SEQ_RUN));
    prints(":");
    print_hex8(r32(SEQ_IRQ + 4U));
    prints("\n");
}

static int stop_isp0_aif3(void) {
    w32(ISP0_AIF3_BASE + 0x00U, r32(ISP0_AIF3_BASE + 0x00U) & ~1U);
    if (r32(ISP0_AIF3_BASE + 0x04U) & (1U << 31)) {
        w32(ISP0_AIF3_BASE + 0x04U, r32(ISP0_AIF3_BASE + 0x04U) | (1U << 30));
    }
    dsb();
    for (uint32_t i = 0U; i < 10000U; ++i) {
        if ((r32(ISP0_AIF3_BASE + 0x04U) & (1U << 31)) == 0U) {
            return 1;
        }
    }
    return 0;
}

static void observe_isp0_aif3(void) {
    uint32_t began = r32(TIMER_READ_PA), last = began, samples = 0U;
    uint32_t busy_seen = 0U, idle_after_busy = 0U, peak = 0U, errors = 0U;
    for (uint32_t i = 0U; i < 4000000U; ++i) {
        uint32_t status = r32(ISP0_AIF3_BASE + 4U);
        uint32_t cursor = r32(ISP0_AIF3_BASE + 0x10U);
        uint32_t offset = cursor - BAYER_DST_PA;
        uint32_t busy = status >> 31;
        idle_after_busy |= busy_seen & (busy ^ 1U);
        busy_seen |= busy;
        errors |= r32(ISP0_AIF3_BASE + 8U);
        if (offset <= BAYER_M37_BYTES && offset > peak) {
            peak = offset;
        }
        uint32_t now = r32(TIMER_READ_PA);
        if (now - last >= 200000U) {
            print_still_poll_sample(samples++);
            last = now;
        }
        if (now - began >= 1200000U) {
            break;
        }
    }
    prints("M37 DMA busy_seen="); print_dec(busy_seen);
    prints(" idle_after_busy="); print_dec(idle_after_busy);
    prints(" peak_offset="); print_dec(peak);
    prints(" errors="); print_hex8(errors);
    prints("\n");
}

static void slvsec_relock_mode5(void) {
    /* Replay indices 98..140 of imx284_wake_pre_writes (0x637AEBD0 43-write SLVS-EC relock). */
    write_table(&imx284_wake_pre_writes[98U], 43U, 0U);
}

static void run_still_capture(void) {
    prints("M37 DFE clocks and route\n");
    WRITE_TABLE(dfe_still_clock_writes, 0U);
    WRITE_TABLE(dfe_still_setup_writes, 0U);
    WRITE_TABLE(imx284_still_pre_writes, 0U);
    run_seq_burst(imx284_still_upload_0, sizeof(imx284_still_upload_0), 2U, 1);
    run_seq_burst(imx284_still_upload_1, sizeof(imx284_still_upload_1), 2U, 1);

    w32(ISP0_AIF3_BASE + 0x00U, 2U);
    w32(ISP0_AIF3_BASE + 0x0cU, 0U);
    w32(ISP0_AIF3_BASE + 0x20U, BAYER_DST_PA);
    w32(ISP0_AIF3_BASE + 0x24U, BAYER_M37_WIDTH * 2U);
    w32(ISP0_AIF3_BASE + 0x28U, 0U);
    w32(ISP0_AIF3_BASE + 0x2cU, BAYER_M37_HEIGHT - 1U);
    dsb();
    w32(ISP0_AIF3_BASE + 0x00U, 3U);
    dsb();

    run_seq_burst(imx284_still_upload_2, sizeof(imx284_still_upload_2), 0U, 0);
    WRITE_TABLE(dfe_still_start_writes, 0U);

    observe_isp0_aif3();
    if (stop_isp0_aif3()) {
        (void)analyze_and_maybe_dump("/tmp/bayer_m37.raw", BAYER_M37_WIDTH,
                                     BAYER_M37_HEIGHT, BAYER_M37_WIDTH);
    } else {
        prints("M37 ISP0 writer still busy after stop; skipping readback\n");
    }
    w32(0xfc099110U, 0U);
    w32(0xfc098280U, 0U);
    w32(0xfc0ad610U, 0U);
    w32(0xfc0ad600U, 0U);
    w32(0xfc0a1110U, 0U);
    w32(0xfc0a1210U, 0U);
    w32(0xfc0a1310U, 0U);
    w32(0xfc0a0004U, 0x10U);
    w32(0xfc0f0050U, 0U);
    w32(0xfc0f0150U, 0U);
    w32(0xfc0f0000U, 0U);
    dsb();
}

static int run_full(int still_only) {
    prints("FULL check RdcW0\n");
    uint32_t initial_status = r32(RDCW0_BASE + 4U);
    prints("FULL check ISP0 AIF3\n");
    uint32_t isp0_status = r32(ISP0_AIF3_BASE + 4U);
    if ((initial_status & 0xc0000000U) || (r32(ISP0_AIF3_BASE) & 1U) || (isp0_status & 0xc0000000U)) {
        prints("RAW writer busy or stopping at entry: rdc=");
        print_hex8(initial_status);
        prints(" isp0=");
        print_hex8(isp0_status);
        prints("\n");
        return 3;
    }
    prints("FULL power-save wake\n");
    psave_imager_wake();

    clear_dst_buf();

    uint32_t pwr_cnt = (uint32_t)(sizeof(imx284_power_on_ops) / sizeof(imx284_power_on_ops[0]));
    for (uint32_t i = 0U; i < pwr_cnt; ++i) {
        if (imx284_power_on_ops[i].addr == 0U) {
            delay_us(imx284_power_on_ops[i].value);
        } else {
            w32(imx284_power_on_ops[i].addr, imx284_power_on_ops[i].value);
            dsb();
        }
    }
    w32(0xfc029004U, 0x000000f2U);
    w32(0xfc029008U, 0x00000077U);
    dsb();
    delay_us(5000U);

    /* clk_id 0x3b (0x63a26438): SoC CRG reset/clock/enable for SLVS-EC/imager */
    w32(0xf2a30044U, 0x00000200U);
    w32(0xf2a30064U, 0x01000000U);
    w32(0xf2a300a4U, 0x00000400U);
    /* 0x639df964(1): pins 17/26 mux/OE + DFE clock bridge enable */
    w32(0xfc01f168U, 0x00000009U);
    w32(0xfc01f01cU, 0x04000000U);
    w32(0xfc01f010U, 0x04000000U);
    w32(0xfc01f144U, 0x0000000eU);
    w32(0xfc01f310U, 0x0000000eU);
    w32(0xfc01f010U, 0x00020000U);
    w32(0xfc01e010U, r32(0xfc01e010U) | 0x00200000U);
    w32(0xfc080114U, 0x00000001U);
    w32(0xfc02a040U, 0x00000000U);
    dsb();
    delay_us(1000U);
    prints("CLK1e="); print_hex8(r32(0xfc01e010U));
    prints(" 1f="); print_hex8(r32(0xfc01f010U));
    prints(" a360="); print_hex8(r32(0xf2a30060U));
    prints("\n");

    prints("FULL DFE PLL and PHY\n");
    WRITE_TABLE(dfe_mode5_pll_phy_writes, 0U);
    w32(0xfc02a06cU, 0x0012007cU);
    delay_us(1000U);

    if (!still_only) {
        prints("FULL DFE mode-5 clocks\n");
        w32(0xfc0a0200U, 0x00000001U);
        w32(0xfc0a0200U, 0x00000010U);
        WRITE_TABLE(dfe_mode5_clock_sgc_writes, 0U);
        WRITE_TABLE(dfe_mode5_zpdctl_setup, 0U);
        w32(0xfc098808U, 0x003e0007U);
        WRITE_TABLE(dfe_mode5_setup_writes, BAYER_DST_PA);
        WRITE_TABLE(dfe_mode5_sgc3_setup, 0U);
        dsb();
        WRITE_TABLE(imx284_mode5_pre_writes, 0U);
    }
    dsb();
    delay_us(1000U);
    WRITE_TABLE(imx284_wake_pre_writes, 0U);

    seq_irq_enable(0U);
    run_seq_burst(imx284_wake_upload_0, sizeof(imx284_wake_upload_0), 2U, 1);
    prints("B0 raw=");
    print_hex8(r32(SEQ_IRQ));
    prints(" st=");
    print_hex8(r32(SEQ_IRQ + 4U));
    prints(" I=");
    print_dec(seq_irqs);
    prints(" T=");
    print_dec(seq_timeouts);
    prints("\n");
    run_seq_burst(imx284_wake_upload_0, sizeof(imx284_wake_upload_0), 2U, 1);
    delay_us(12000U);
    run_seq_burst(imx284_wake_upload_1, sizeof(imx284_wake_upload_1), 2U, 1);
    run_seq_burst(imx284_wake_upload_2, sizeof(imx284_wake_upload_2), 2U, 1);
    delay_us(6000U);

    WRITE_TABLE(imx284_wake_post_writes, 0U);
    w32(0xf2a30038U, 0x08000000U);
    delay_us(20000U);

    if (still_only) {
        prints("MODE37 direct cold start\n");
        run_still_capture();
        w32(0xfc0a1410U, 0U);
    } else {
        run_seq_burst(imx284_mode5_upload_0, sizeof(imx284_mode5_upload_0), 2U, 1);
        run_seq_burst(imx284_mode5_upload_1, sizeof(imx284_mode5_upload_1), 2U, 1);
        delay_us(1000U);
        run_seq_burst(imx284_mode5_upload_2, sizeof(imx284_mode5_upload_2), 0U, 0);

        w32(0xfc0a114cU, 0x00000004U);
        w32(0xfc0a1150U, 0x00250005U);
        /* Apply the active EE timing before the selector-1 SGC0 start. */
        w32(0xfc0a1120U, 0x026a0793U);
        w32(0xfc0a1124U, 0x00000206U);
        w32(0xfc0a11a8U, 0x026b0001U);
        w32(0xfc0a112cU, 0U);
        w32(0xfc0a1130U, r32(0xfc0a1130U) & ~0x00010000U);
        w32(0xfc0a1108U, r32(0xfc0a1108U) & ~1U);
        w32(0xfc0a1110U, r32(0xfc0a1110U) | 1U);
        dsb();

        WRITE_TABLE(dfe_mode5_sgc3_start, 0U);
        uint32_t st_cnt = (uint32_t)(sizeof(dfe_mode5_start_writes) / sizeof(dfe_mode5_start_writes[0]));
        for (uint32_t i = 0U; i < st_cnt; ++i) {
            uint32_t addr = dfe_mode5_start_writes[i].addr;
            if (addr == 0xfc0a0018U || addr == 0xfc0a0030U) {
                continue;
            }
            w32(addr, dfe_mode5_start_writes[i].value);
        }
        w32(0xfc0a0018U, 0U);
        w32(0xfc0a0030U, 0U);
        dsb();
        WRITE_TABLE(dfe_mode5_zpdctl_trigger, 0U);

        uint32_t sgc0_a = r32(0xfc0a1110U);
        delay_us(10000U);
        uint32_t sgc0_c = r32(0xfc0a1110U);
        prints("SGC0 a="); print_hex8(sgc0_a);
        prints(" c="); print_hex8(sgc0_c);
        prints(" m="); print_hex8(r32(0xfc0a1108U));
        prints(" r2c="); print_hex8(r32(0xfc0a112cU));
        prints(" timing="); print_hex8(r32(0xfc0a1120U));
        prints(":"); print_hex8(r32(0xfc0a1124U));
        prints(":"); print_hex8(r32(0xfc0a11a8U));
        prints(" zpd="); print_hex8(r32(0xfc099110U));
        prints(":"); print_hex8(r32(0xfc098280U));
        prints("\n");
        if ((sgc0_c & 0x00010000U) == 0U) {
            w32(0xfc0a0004U, 0x0000b088U);
            dsb();
            delay_us(5000U);
            prints("SGC0_172="); print_hex8(r32(0xfc0a1110U));
            prints(" 1f310="); print_hex8(r32(0xfc01f310U));
            prints("\n");
        }
        seq_wait_irq(100000U);

        w32(0xfc0a0014U, 0xffffffffU);
        w32(0xfc0a002cU, 0xffffffffU);
        dsb();
        prints("CLR dfe10="); print_hex8(r32(0xfc0a0010U));
        prints(" dfe14="); print_hex8(r32(0xfc0a0014U));
        prints(" dfe28="); print_hex8(r32(0xfc0a0028U));
        prints(" dfe2c="); print_hex8(r32(0xfc0a002cU));
        prints("\n");

        for (uint32_t s = 0U; s < 3U; ++s) {
            delay_us(100000U);
            if (s == 1U && r32(RDCW0_BASE + 0x10U) == 0U) {
                w32(RDCW0_BASE + 0x20U, BAYER_DST_PA);
                w32(RDCW0_BASE, 3U);
                dsb();
                prints("REARM\n");
            }
            print_poll_sample(s);
            if (s == 0U) {
                dump_pipeline("P0");
                prints("P0_CLK 1e="); print_hex8(r32(0xfc01e010U));
                prints(" 8030="); print_hex8(r32(0xfc080030U));
                prints(" 80f4="); print_hex8(r32(0xfc0800f4U));
                prints(" a0200="); print_hex8(r32(0xfc0a0200U));
                prints(" a0204="); print_hex8(r32(0xfc0a0204U));
                prints(" a330="); print_hex8(r32(0xf2a30030U));
                prints(" a000="); print_hex8(r32(0xfc0a0000U));
                prints("\n");
                dump_regs_bin("/tmp/regs_bayer.bin");
            }
        }

        int rdc_idle = stop_rdcw0();
        if (!rdc_idle) {
            prints("MODE5 RdcW0 still busy after stop; skipping readback and ISP0 fallback\n");
        } else if (dst_has_nonzero()) {
            (void)analyze_and_maybe_dump("/tmp/bayer_full.raw", BAYER_LIVE_WIDTH,
                                         BAYER_LIVE_HEIGHT, BAYER_LIVE_STRIDE_PIXELS);
        } else {
            prints("MODE5 PIX nonzero=0 -> trying MODE37 ISP0_AIF3\n");
            w32(0xfc0a1210U, 0U);
            w32(0xfc0a1310U, 0U);
            w32(0xfc0a1410U, 0U);
            w32(0xfc0ad610U, 0U);
            dsb();

            print_still_poll_sample(99U);

            run_still_capture();
        }

        if (!rdc_idle) {
            stop_rdcw0();
        }
        w32(0xfc099110U, 0U);
        w32(0xfc098280U, 0U);
        w32(0xfc0a1410U, 0U);
        w32(0xfc0a1400U, 0U);
        w32(0xfc0a0004U, 0x18U);
        dsb();
    }
    w32(SEQ_PORT, r32(SEQ_PORT) & ~1U);
    seq_irq_enable(0U);
    w32(0xfc080114U, 0U);
    w32(0xfc01e010U, r32(0xfc01e010U) & ~0x00200000U);
    w32(0xfc01f014U, 0x04020000U);
    w32(0xfc01f168U, 0U);
    w32(0xfc01f144U, 0U);
    w32(0xf2a30068U, 0x01000000U);
    w32(0xfc029028U, 0U);
    w32(0xfc029008U, 0U);
    w32(0xfc029000U, 0U);
    w32(PMU_BASE_PA + 0x004U, 1U);
    w32(PMU_BASE_PA + 0x008U, 1U);
    dsb();
    prints("CLEANED_IDLE\n");
    return 0;
}

static int run_rdcw0(void) {
    clear_dst_buf();
    uint32_t orig_a0154 = r32(0xfc0a0154U);
    uint32_t orig_a0180 = r32(0xfc0a0180U);
    uint32_t orig_a8700 = r32(0xfc0a8700U);
    uint32_t orig_a1200 = r32(0xfc0a1200U);
    uint32_t orig_a1300 = r32(0xfc0a1300U);
    uint32_t orig_a1354 = r32(0xfc0a1354U);
    uint32_t orig_a13d0 = r32(0xfc0a13d0U);
    w32(0xfc0a0000U, 0x00000002U);
    w32(0xfc0a0000U, 0x00000080U);
    w32(0xfc0a0000U, 0x00008000U);
    dsb();
    w32(0xfc0a0154U, 0x40000000U);
    w32(0xfc0a0180U, 0x00010000U);
    w32(0xfc0a1300U, 0x00000001U);
    w32(0xfc0a1200U, 0x00000001U);
    dsb();
    uint32_t su_cnt = (uint32_t)(sizeof(dfe_mode5_setup_writes) / sizeof(dfe_mode5_setup_writes[0]));
    for (uint32_t i = 0U; i < su_cnt; ++i) {
        uint32_t a = dfe_mode5_setup_writes[i].addr;
        if (a >= 0xfc0a1200U && a <= 0xfc0a13ecU) {
            w32(a, dfe_mode5_setup_writes[i].value);
        }
    }
    w32(0xfc0a1350U, 0x00000000U);
    w32(0xfc0a1354U, 0x01fb0263U);
    w32(0xfc0a1358U, 0x3ffe3ffeU);
    w32(0xfc0a135cU, 0x3ffe3ffeU);
    w32(0xfc0a132cU, 0x00000000U);
    w32(0xfc0a13d0U, 0x08c00000U);
    w32(0xfc0a8700U, 0x00000100U);
    w32(0xfc0a8704U, 0x00000001U);
    w32(0xfc0a8804U, 0x00000001U);
    w32(0xfc0a8900U, 0x00000001U);
    w32(0xfc0a0504U, 0x000001c0U);
    w32(0xfc0a0564U, 0x000001c0U);
    w32(0xfc0a8014U, 0x00000000U);
    w32(0xfc0a9000U, 0x00000004U);
    w32(0xfc0a9000U, 0x00000002U);
    w32(0xfc0a9204U, 0x00000000U);
    w32(0xfc0a9274U, 0x00000000U);
    w32(0xfc0a9278U, 0x00000000U);
    dsb();
    w32(RDCW0_BASE + 0x20U, BAYER_DST_PA);
    w32(RDCW0_BASE + 0x24U, 0xf98U);
    w32(RDCW0_BASE + 0x28U, 0x28U);
    w32(RDCW0_BASE + 0x2cU, 0x240U);
    dsb();
    w32(RDCW0_BASE, 3U);
    dsb();
    w32(0xfc0a1310U, 1U);
    w32(0xfc0a1210U, 1U);
    dsb();

    for (uint32_t s = 0U; s < 3U; ++s) {
        delay_us(100000U);
        print_poll_sample(s);
        if (s == 0U) {
            dump_pipeline("P0");
        }
    }

    (void)analyze_and_maybe_dump("/tmp/bayer_rdcw0.raw", BAYER_LIVE_WIDTH,
                                 BAYER_LIVE_HEIGHT, BAYER_LIVE_STRIDE_PIXELS);
    stop_rdcw0();
    w32(0xfc0a1310U, 0U);
    w32(0xfc0a1210U, 0U);
    w32(0xfc0a13d0U, orig_a13d0);
    w32(0xfc0a1354U, orig_a1354);
    w32(0xfc0a1300U, orig_a1300);
    w32(0xfc0a1200U, orig_a1200);
    w32(0xfc0a0154U, orig_a0154);
    w32(0xfc0a0180U, orig_a0180);
    w32(0xfc0a8700U, orig_a8700);
    w32(0xfc0a8014U, 0x00010000U);
    dsb();
    return 0;
}

/* Passive native-still recorder. These reads follow the original DFE/AIF,
 * ISP, FOPD and XDMAC getter layouts. The timer is the 2 MHz board counter. */
#define STOCK_TRACE_MAX_WORDS 272U
#define STOCK_TRACE_MAX_EVENTS 32768U

struct stock_word {
    volatile const uint32_t *reg;
    uint32_t address, previous;
};

struct stock_event {
    uint32_t tick, address, value;
};

static struct stock_word stock_words[STOCK_TRACE_MAX_WORDS];
static struct stock_event stock_events[STOCK_TRACE_MAX_EVENTS];
static uint32_t stock_word_count;
static int32_t stock_mem_fd;
static uint32_t page_address;
static volatile const uint8_t *page_pointer;

static void stock_trace_word(uint32_t address) {
    uint32_t page = address & ~4095U;
    if (stock_word_count == STOCK_TRACE_MAX_WORDS) {
        die("trace register list", -1);
    }
    if (!page_pointer || page_address != page) {
        int32_t result = sys_call6(SYS_mmap2, 0U, 4096U, 1U, MAP_SHARED,
                                   (uint32_t)stock_mem_fd, page >> 12);
        if (result < 0 && result >= -4095) {
            die("read-only trace mmap", result);
        }
        page_address = page;
        page_pointer = (volatile const uint8_t *)(uintptr_t)(uint32_t)result;
    }
    stock_words[stock_word_count++] = (struct stock_word){
        (volatile const uint32_t *)(page_pointer + (address & 4095U)), address, 0U
    };
}

static void stock_trace_ports(uint32_t first, uint32_t count) {
    /* Programmed destination and cursor are distinct registers. */
    static const uint8_t offsets[] = {0, 4, 0x0c, 0x10, 0x20};
    for (uint32_t i = 0; i < count; ++i) {
        for (uint32_t j = 0; j < sizeof(offsets); ++j) {
            stock_trace_word(first + i * 0x80U + offsets[j]);
        }
    }
}

static int run_stock_trace(const char *path) {
    stock_mem_fd = sys_call2(SYS_open, (uint32_t)(uintptr_t)"/dev/mem", 0x101000U);
    if (stock_mem_fd < 0) {
        die("trace open /dev/mem", stock_mem_fd);
    }
    stock_trace_word(TIMER_READ_PA);
    static const uint16_t imager_offsets[] = {
        0x11c, 0x120, 0x124, 0x128, 0x134, 0x138, 0x13c, 0x258, 0x25c,
        0x260, 0x264, 0x268, 0x26c, 0x270, 0x274, 0x278, 0x424,
    };
    for (uint32_t i = 0; i < sizeof(imager_offsets) / sizeof(imager_offsets[0]); ++i) {
        stock_trace_word(0x0426b384U + imager_offsets[i]);
    }
    stock_trace_word(0x043d7320U); /* retained DMM handle */
    stock_trace_word(0x043bbc80U); /* published DMM handle */
    stock_trace_word(0x043bbc8cU); /* published buffer address */
    stock_trace_word(0x043bbc90U); /* published buffer length */
    stock_trace_word(SEQ_PORT);
    stock_trace_word(SEQ_PORT + 4U);
    stock_trace_word(SEQ_PORT + 8U);
    stock_trace_word(SEQ_PORT + 12U);
    stock_trace_word(SEQ_RUN);
    stock_trace_word(SEQ_RUN + 8U);
    stock_trace_word(SEQ_IRQ + 4U);
    stock_trace_word(SEQ_IRQ + 8U);
    stock_trace_word(0xfc0a0000U); /* DFE core control */
    stock_trace_word(0xfc0a0010U); /* DFE event status, getter */
    stock_trace_word(0xfc0a0028U);
    for (uint32_t i = 0; i < 4U; ++i) {
        uint32_t sgc = 0xfc0a1100U + i * 0x100U;
        stock_trace_word(sgc);
        stock_trace_word(sgc + 0x10U);
        stock_trace_word(sgc + 0x2cU);
        stock_trace_word(sgc + 0x54U);
        stock_trace_word(sgc + 0xd0U);
    }
    stock_trace_word(0xfc0f00acU); /* SLVS-EC monitor */
    stock_trace_word(0xfc0f00b0U);
    stock_trace_ports(0xfc0a9200U, 2);
    stock_trace_ports(0xfc0ac200U, 8);
    for (uint32_t bank = 0xf3002000U; bank <= 0xf3102000U; bank += 0x100000U) {
        stock_trace_word(bank);
        stock_trace_word(bank + 8U);
    }
    stock_trace_ports(0xf3002200U, 6);
    stock_trace_ports(0xf3102200U, 6);
    stock_trace_ports(0xf3020200U, 6);
    stock_trace_ports(0xf3041200U, 2);
    stock_trace_ports(0xf3881200U, 4);
    /* Geometry and format of the two ISP AIF ports observed in stock still capture. */
    for (uint32_t offset = 0x24U; offset <= 0x40U; offset += 4U) {
        stock_trace_word(0xf3002380U + offset);
        stock_trace_word(0xf3102200U + offset);
    }
    for (uint32_t channel = 0; channel < 8; ++channel) {
        uint32_t port = 0xf0000010U + (channel / 4U) * 0x10000U + (channel % 4U) * 0x30U;
        stock_trace_word(port + 4U);
        stock_trace_word(port + 8U);
        stock_trace_word(port + 0x20U);
    }
    sys_call1(SYS_close, (uint32_t)stock_mem_fd);

    int32_t fd = sys_call3(SYS_open, (uint32_t)(uintptr_t)path,
                           O_WR_CREATE_TRUNC | 0x80U, 0600U); /* O_EXCL */
    if (fd < 0) {
        die("trace open output", fd);
    }
    uint32_t start = *stock_words[0].reg;
    uint32_t captured = 0U, polls = 0U;
    uint32_t ticks;
    do {
        ticks = *stock_words[0].reg - start;
        for (uint32_t i = 1; i < stock_word_count; ++i) {
            uint32_t current = *stock_words[i].reg;
            if (!polls || current != stock_words[i].previous) {
                if (captured == STOCK_TRACE_MAX_EVENTS) {
                    break;
                }
                stock_events[captured++] = (struct stock_event){ticks, stock_words[i].address, current};
                stock_words[i].previous = current;
            }
        }
        ++polls;
        delay_us(600U);
    } while (ticks < 12000000U && polls < 10000U && captured < STOCK_TRACE_MAX_EVENTS);

    const uint32_t header[] = {0x31545342U, captured, polls, ticks};
    write_all(fd, header, sizeof(header));
    write_all(fd, stock_events, captured * sizeof(stock_events[0]));
    sys_call1(SYS_close, (uint32_t)fd);
    return captured == STOCK_TRACE_MAX_EVENTS ? 4 : 0;
}

int c_main(int argc, char **argv) {
    if (argc < 2) {
        prints("usage: bayer_test check|full|still|rdcw0|stock-trace PATH\n");
        return 1;
    }
    if (str_eq(argv[1], "stock-trace")) {
        return argc == 3 ? run_stock_trace(argv[2]) : 1;
    }
    int32_t fd = sys_call2(SYS_open, (uint32_t)(uintptr_t)"/dev/mem", O_RDWR_SYNC);
    if (fd < 0) {
        die("open /dev/mem", fd);
    }
    init_regions(fd);
    sys_call1(SYS_close, (uint32_t)fd);

    if (str_eq(argv[1], "check")) {
        return run_check();
    }
    if (str_eq(argv[1], "full")) {
        return run_full(0);
    }
    if (str_eq(argv[1], "full-sgc3")) {
        return run_full(0);
    }
    if (str_eq(argv[1], "still")) {
        return run_full(1);
    }
    if (str_eq(argv[1], "rdcw0")) {
        return run_rdcw0();
    }
    if (str_eq(argv[1], "dump") && argc >= 3) {
        dump_regs_bin(argv[2]);
        return 0;
    }
    prints("unknown mode\n");
    return 1;
}

__attribute__((naked)) void _start(void) {
    __asm__ volatile(
        "ldr r0, [sp]\n"
        "add r1, sp, #4\n"
        "bic sp, sp, #7\n"
        "bl c_main\n"
        "mov r7, #1\n"
        "svc #0\n"
    );
}
