/* SPDX-License-Identifier: GPL-2.0 */
#ifndef IMX284_SENSOR_H
#define IMX284_SENSOR_H

#include <stdint.h>
#include "cxd90057_hw.h"

/* IMX284 live readout Mode-1 geometry (sensor_mode 5 active crop in DFE) */
#define IMX284_MODE1_WIDTH         1996U
#define IMX284_MODE1_HEIGHT        1122U
#define IMX284_MODE1_STRIDE_PIXELS 2016U
#define IMX284_MODE1_FRAME_BYTES   (IMX284_MODE1_STRIDE_PIXELS * IMX284_MODE1_HEIGHT * 2U)

/* IMX284 timing parameters from native Mode-1 resource lookup (av-cam.bin) */
#define IMX284_MODE1_H_TOTAL       1940U
#define IMX284_MODE1_V_TOTAL       619U
#define IMX284_MODE1_NLR_DELTA     1U
#define IMX284_MODE1_NLR_NUM       17U
#define IMX284_MODE1_NLR_DEN       97U
#define IMX284_MODE1_LEAD_US       15621U

/*
 * Imager power/control GPIO pins (0xfc029000..0xfc02902c, FUN_63d23260/90/c0)
 * pin = bank * 8 + bit; banks 0..3 correspond to +0x00/+0x04/+0x08/+0x0c (EN),
 * +0x10..0x1c (DIR), +0x20..0x2c (LVL).
 */
enum imx284_gpio_pin {
    IMX284_PIN_PWR_SEQ0  = 5,  /* bank 0 bit 5 (0x20) */
    IMX284_PIN_PWR_SEQ3  = 6,  /* bank 0 bit 6 (0x40) */
    IMX284_PIN_PWR_SEQ2  = 7,  /* bank 0 bit 7 (0x80) */
    IMX284_PIN_PWR_KEEP  = 9,  /* bank 1 bit 1 (0x02) - preserved from cold boot */
    IMX284_PIN_PWR_SEQ5  = 12, /* bank 1 bit 4 (0x10) */
    IMX284_PIN_PWR_SEQ1  = 13, /* bank 1 bit 5 (0x20) */
    IMX284_PIN_PWR_SEQ4  = 14, /* bank 1 bit 6 (0x40) */
    IMX284_PIN_PWR_SEQ6  = 15, /* bank 1 bit 7 (0x80) */
    IMX284_PIN_RAIL_16   = 16, /* bank 2 bit 0 (0x01) */
    IMX284_PIN_WAKE_B1   = 17, /* bank 2 bit 1 (0x02) */
    IMX284_PIN_WAKE_B0   = 18, /* bank 2 bit 2 (0x04) */
    IMX284_PIN_WAKE_B2   = 19, /* bank 2 bit 3 (0x08) */
    IMX284_PIN_WAKE_A0   = 20, /* bank 2 bit 4 (0x10) */
    IMX284_PIN_WAKE_A1   = 21, /* bank 2 bit 5 (0x20) */
    IMX284_PIN_WAKE_A2   = 22  /* bank 2 bit 6 (0x40) */
};

struct imx284_reg_write {
    uint16_t reg;
    uint8_t val;
};

static inline void imx284_pin_enable(uint32_t pin) {
    uint32_t bank = pin >> 3;
    uint32_t bit = BIT(pin & 7U);
    w32(IMAGER_GPIO_EN(bank), r32(IMAGER_GPIO_EN(bank)) | bit);
}

static inline void imx284_pin_disable(uint32_t pin) {
    uint32_t bank = pin >> 3;
    uint32_t bit = BIT(pin & 7U);
    w32(IMAGER_GPIO_EN(bank), r32(IMAGER_GPIO_EN(bank)) & ~bit);
}

static inline void imx284_pin_set_level(uint32_t pin, int high) {
    uint32_t bank = pin >> 3;
    uint32_t bit = BIT(pin & 7U);
    uint32_t v = r32(IMAGER_GPIO_LVL(bank));
    w32(IMAGER_GPIO_LVL(bank), high ? (v | bit) : (v & ~bit));
}

/*
 * FUN_637ad800 + FUN_63d2ac1e: acquire PMIC SPI clock (ch 0xb = 0x4e),
 * configure imager GPIO bank directions, preserve cold bit 1 on bank 1,
 * set pad drive strength, and step up the IMX284 power rails with delays.
 */
static inline void imx284_pmic_spi_enable(void) {
    w32(SOC_CRG1_RST2_SET, BIT(27));
    w32(SOC_CRG1_CLK0_SET, BIT(11));
    (void)r32(SOC_CRG1_CLK0_STAT);
    dsb();
}

static inline void imx284_pmic_spi_disable(void) {
    w32(SOC_CRG1_CLK0_CLR, BIT(11));
    w32(SOC_CRG1_RST2_CLR, BIT(27));
    dsb();
}

static void imx284_power_on(void) {
    imx284_pmic_spi_enable();

    /* Initialize GPIO banks 0..3 (preserve cold IMX284_PIN_PWR_KEEP on bank 1). */
    w32(IMAGER_GPIO_EN(0U), 0x00U);
    w32(IMAGER_GPIO_EN(1U), BIT(IMX284_PIN_PWR_KEEP & 7U));
    w32(IMAGER_GPIO_EN(2U), 0x00U);
    w32(IMAGER_GPIO_EN(3U), 0x00U);

    w32(IMAGER_GPIO_DIR(0U), 0xf9U);
    w32(IMAGER_GPIO_DIR(1U), 0xf0U);
    w32(IMAGER_GPIO_DIR(2U), 0x7fU);
    w32(IMAGER_GPIO_DIR(3U), 0x00U);

    w32(IMAGER_GPIO_LVL(0U), 0x00U);
    w32(IMAGER_GPIO_LVL(1U), 0x00U);
    w32(IMAGER_GPIO_LVL(2U), 0x00U);
    w32(IMAGER_GPIO_LVL(3U), 0x00U);
    w32(IMAGER_PAD_DRIVE, 0x00aaaaaaU);
    dsb();

    /* Stepped rail bring-up matching FUN_637ad800 property 0xbc0014. */
    imx284_pin_enable(IMX284_PIN_PWR_SEQ0);
    dsb();
    delay_us(9400U);

    imx284_pin_enable(IMX284_PIN_PWR_SEQ1);
    dsb();
    delay_us(1000U);

    imx284_pin_enable(IMX284_PIN_PWR_SEQ2);
    imx284_pin_enable(IMX284_PIN_PWR_SEQ3);
    dsb();
    delay_us(9400U);

    imx284_pin_enable(IMX284_PIN_PWR_SEQ4);
    dsb();
    delay_us(12400U);

    imx284_pin_enable(IMX284_PIN_PWR_SEQ5);
    imx284_pin_enable(IMX284_PIN_PWR_SEQ6);
    dsb();

    imx284_pin_enable(IMX284_PIN_WAKE_B0);
    imx284_pin_enable(IMX284_PIN_WAKE_B1);
    imx284_pin_enable(IMX284_PIN_WAKE_B2);
    dsb();
    delay_us(12400U);

    imx284_pin_enable(IMX284_PIN_RAIL_16);
    dsb();
    delay_us(12400U);
    imx284_pmic_spi_disable();
}

/*
 * FUN_637ab9fc: reverse-sequenced imager power-down (preserves IMX284_PIN_PWR_KEEP).
 */
static void imx284_power_off(void) {
    imx284_pin_enable(IMX284_PIN_PWR_SEQ3);
    dsb();
    delay_us(1000U);
    imx284_pin_disable(IMX284_PIN_RAIL_16);
    dsb();
    delay_us(20000U);

    imx284_pin_disable(IMX284_PIN_WAKE_B0);
    imx284_pin_set_level(IMX284_PIN_WAKE_B0, 0);
    imx284_pin_disable(IMX284_PIN_WAKE_B1);
    imx284_pin_set_level(IMX284_PIN_WAKE_B1, 0);
    imx284_pin_disable(IMX284_PIN_WAKE_B2);
    imx284_pin_set_level(IMX284_PIN_WAKE_B2, 0);
    imx284_pin_disable(IMX284_PIN_WAKE_A0);
    imx284_pin_set_level(IMX284_PIN_WAKE_A0, 0);
    imx284_pin_disable(IMX284_PIN_WAKE_A2);
    imx284_pin_set_level(IMX284_PIN_WAKE_A2, 0);
    imx284_pin_disable(IMX284_PIN_WAKE_A1);
    imx284_pin_set_level(IMX284_PIN_WAKE_A1, 0);
    dsb();
    delay_us(20000U);

    imx284_pin_disable(IMX284_PIN_PWR_SEQ6);
    imx284_pin_disable(IMX284_PIN_PWR_SEQ5);
    dsb();
    delay_us(20000U);

    imx284_pin_disable(IMX284_PIN_PWR_SEQ4);
    dsb();
    delay_us(7400U);

    imx284_pin_disable(IMX284_PIN_PWR_SEQ3);
    dsb();
    delay_us(20000U);

    imx284_pin_disable(IMX284_PIN_PWR_SEQ2);
    imx284_pin_disable(IMX284_PIN_PWR_SEQ1);
    dsb();
    delay_us(82000U);

    imx284_pin_disable(IMX284_PIN_PWR_SEQ0);
    dsb();
    imx284_pmic_spi_disable();
}

enum imx284_p2s_field {
    IMX284_P2S_BLOCK_TAG = 0x81,
    IMX284_P2S_REGISTER_WRITE = 0x81,
    IMX284_P2S_WRITE_PREFIX_SIZE = 3, /* command and 16-bit register address */
    IMX284_P2S_BLOCK_HEADER_SIZE = 2, /* block tag and encoded length */
    IMX284_P2S_END = 0,
};

/*
 * FUN_63d2aa56 writes the block header and big-endian register address.
 * FUN_63d2aa8a extends a block only for adjacent registers within a page.
 * FUN_63d2a31e finalizes the last length and terminates the instruction list.
 */
static uint32_t imx284_spi_build_burst(const struct imx284_reg_write *ops, uint32_t count,
                                       uint8_t *out, uint32_t max_len) {
    uint32_t pos = 0U;
    uint32_t i = 0U;

    while (i < count) {
        uint16_t start_reg = ops[i].reg;
        uint32_t page_remaining = UINT8_MAX + 1U - (start_reg & UINT8_MAX);
        uint32_t run = 1U;
        while (i + run < count && run < page_remaining &&
               run < UINT8_MAX - IMX284_P2S_WRITE_PREFIX_SIZE &&
               ops[i + run].reg == (uint16_t)(start_reg + run)) {
            ++run;
        }

        uint32_t block_length = IMX284_P2S_WRITE_PREFIX_SIZE + run;
        if (pos + IMX284_P2S_BLOCK_HEADER_SIZE + block_length + 1U > max_len) {
            return 0U;
        }
        out[pos++] = IMX284_P2S_BLOCK_TAG;
        out[pos++] = (uint8_t)block_length;
        out[pos++] = IMX284_P2S_REGISTER_WRITE;
        out[pos++] = (uint8_t)(start_reg >> 8);
        out[pos++] = (uint8_t)(start_reg & 0xffU);
        for (uint32_t k = 0U; k < run; ++k) {
            out[pos++] = ops[i + k].val;
        }
        i += run;
    }
    if (pos + 1U > max_len) {
        return 0U;
    }
    out[pos++] = IMX284_P2S_END;
    return pos;
}

static int imx284_send_burst(const struct imx284_reg_write *ops, uint32_t count,
                             uint32_t run_mode, int wait_irq) {
    uint8_t buf[256];
    uint32_t len = imx284_spi_build_burst(ops, count, buf, (uint32_t)sizeof(buf));
    return len != 0U && run_seq_burst(buf, len, run_mode, wait_irq);
}

#define IMX284_SEND_REGS(tbl, mode, wait) \
    imx284_send_burst((tbl), (uint32_t)(sizeof(tbl) / sizeof((tbl)[0])), (mode), (wait))

/* Wake burst 0: PLL / clock reset pulse (sent twice after raising wake_A pins). */
static const struct imx284_reg_write imx284_wake_regs_0[] = {
    { 0x00d4U, 0xcaU }, { 0x00d8U, 0x30U }, { 0x0954U, 0x01U }, { 0x00d8U, 0x00U },
    { 0x0954U, 0x00U }, { 0x00d4U, 0xfaU },
};

/* Wake burst 1: exit standby & configure PLL lock (12 ms after wake_0). */
static const struct imx284_reg_write imx284_wake_regs_1[] = {
    { 0x094fU, 0x00U }, { 0x0936U, 0x00U }, { 0x0000U, 0x2cU }, { 0x00b3U, 0x90U },
};

/* Wake burst 2: analog / AFE / SLVS-EC baseline defaults (followed by 6 ms wait). */
static const struct imx284_reg_write imx284_wake_regs_2[] = {
    /* Timing & global bias (0x00xx - 0x01xx) */
    { 0x0007U, 0x02U }, { 0x0013U, 0x00U }, { 0x001cU, 0x21U }, { 0x0047U, 0x02U },
    { 0x005bU, 0x00U }, { 0x0068U, 0x10U }, { 0x0071U, 0x07U }, { 0x00b3U, 0x90U },
    { 0x00baU, 0x40U }, { 0x00daU, 0x20U }, { 0x014eU, 0x01U },
    /* Analog & CDS calibration (0x08xx) */
    { 0x0802U, 0x33U }, { 0x0842U, 0x60U }, { 0x084eU, 0x65U }, { 0x084fU, 0x11U },
    { 0x0850U, 0x33U }, { 0x0851U, 0x00U }, { 0x0852U, 0x00U }, { 0x0853U, 0x30U },
    { 0x0854U, 0x30U }, { 0x08d9U, 0x01U }, { 0x08daU, 0x00U }, { 0x08dbU, 0x3aU },
    { 0x08dcU, 0x76U }, { 0x08ddU, 0xbfU }, { 0x08deU, 0x38U }, { 0x08dfU, 0x78U },
    { 0x08e0U, 0x05U },
    /* SLVS-EC serializer & lane tuning (0x09xx - 0x0axx) */
    { 0x0907U, 0x00U }, { 0x0925U, 0x12U }, { 0x0926U, 0x50U }, { 0x0927U, 0x00U },
    { 0x0928U, 0x45U }, { 0x0960U, 0x1eU }, { 0x0961U, 0x22U }, { 0x0962U, 0x06U },
    { 0x0963U, 0x01U }, { 0x097aU, 0x05U }, { 0x097bU, 0x00U }, { 0x097cU, 0x05U },
    { 0x097dU, 0x00U }, { 0x097eU, 0x2cU }, { 0x097fU, 0x02U }, { 0x0980U, 0x05U },
    { 0x0981U, 0x00U }, { 0x0982U, 0x2cU }, { 0x0983U, 0x05U }, { 0x0984U, 0x00U },
    { 0x0985U, 0x07U }, { 0x0986U, 0x25U }, { 0x0987U, 0x00U }, { 0x0988U, 0x2cU },
    { 0x0989U, 0x00U }, { 0x098aU, 0x02U }, { 0x098bU, 0x20U }, { 0x098cU, 0x00U },
    { 0x098dU, 0x00U }, { 0x098eU, 0x2cU }, { 0x098fU, 0x02U }, { 0x0990U, 0x00U },
    { 0x0991U, 0x2cU }, { 0x099cU, 0x01U }, { 0x0a96U, 0x01U },
};

/* Mode-1 LiveView sensor configuration burst 0 (110 writes). */
static const struct imx284_reg_write imx284_mode1_regs_0[] = {
    /* Readout mode, windowing & frame timing (0x00xx) */
    { 0x0000U, 0x1cU }, { 0x0001U, 0x40U }, { 0x0001U, 0x40U }, { 0x0002U, 0x10U },
    { 0x0003U, 0x01U }, { 0x0004U, 0x00U }, { 0x0005U, 0x01U }, { 0x0006U, 0x00U },
    { 0x0007U, 0x02U }, { 0x0008U, 0x00U }, { 0x0009U, 0x00U }, { 0x000aU, 0x6aU },
    { 0x000bU, 0x00U }, { 0x000cU, 0x6cU }, { 0x000dU, 0x04U }, { 0x000eU, 0x08U },
    { 0x000fU, 0x18U }, { 0x0010U, 0x00U }, { 0x0011U, 0x00U }, { 0x0012U, 0x00U },
    { 0x0013U, 0x00U }, { 0x0014U, 0x00U }, { 0x0015U, 0x00U }, { 0x0016U, 0x00U },
    { 0x0017U, 0x04U }, { 0x001dU, 0x12U }, { 0x001eU, 0x0cU }, { 0x001fU, 0x12U },
    { 0x0020U, 0x0cU }, { 0x0024U, 0xceU }, { 0x0027U, 0x8dU }, { 0x002aU, 0x95U },
    { 0x002cU, 0x1cU }, { 0x002dU, 0x1cU }, { 0x0030U, 0x0bU }, { 0x0031U, 0x0bU },
    { 0x0036U, 0x00U }, { 0x0038U, 0x99U }, { 0x003aU, 0x99U }, { 0x003dU, 0x33U },
    { 0x003fU, 0x0fU }, { 0x0040U, 0x99U }, { 0x0042U, 0x11U }, { 0x0054U, 0x00U },
    { 0x0055U, 0x08U }, { 0x0056U, 0x10U }, { 0x0057U, 0x00U }, { 0x0058U, 0x0cU },
    { 0x0059U, 0x70U }, { 0x005aU, 0x08U }, { 0x005bU, 0x00U }, { 0x005cU, 0x00U },
    { 0x005dU, 0x02U }, { 0x005eU, 0x00U }, { 0x005fU, 0x00U }, { 0x0060U, 0x00U },
    { 0x0061U, 0x04U }, { 0x0062U, 0x11U }, { 0x0063U, 0x00U }, { 0x0064U, 0x00U },
    { 0x0065U, 0x00U }, { 0x0066U, 0x00U }, { 0x0067U, 0x13U }, { 0x0068U, 0x10U },
    { 0x0069U, 0xaaU }, { 0x006aU, 0x10U }, { 0x006bU, 0x00U }, { 0x006cU, 0x00U },
    { 0x006dU, 0x00U }, { 0x006eU, 0x00U }, { 0x006fU, 0x3eU }, { 0x0070U, 0x10U },
    { 0x0094U, 0x01U }, { 0x00b3U, 0x90U }, { 0x00b4U, 0x00U }, { 0x00b5U, 0x00U },
    { 0x00d4U, 0xfaU }, { 0x00d5U, 0xfdU }, { 0x00d6U, 0x1fU }, { 0x00d7U, 0x00U },
    { 0x00d8U, 0x00U },
    /* Control & analog readout blocks (0x04xx, 0x08xx) */
    { 0x0420U, 0x99U }, { 0x0421U, 0x00U }, { 0x0803U, 0x11U }, { 0x0804U, 0x00U },
    { 0x0805U, 0x11U }, { 0x0806U, 0x33U }, { 0x0807U, 0x02U }, { 0x0808U, 0x00U },
    { 0x0809U, 0x00U }, { 0x082aU, 0x85U }, { 0x082dU, 0xbcU }, { 0x082eU, 0x00U },
    { 0x082fU, 0x22U }, { 0x0830U, 0xbcU }, { 0x0841U, 0xa3U }, { 0x08dcU, 0x76U },
    { 0x08ddU, 0xbfU }, { 0x08deU, 0x38U }, { 0x08dfU, 0x78U }, { 0x08e0U, 0x05U },
    { 0x08e1U, 0x25U }, { 0x08e2U, 0x07U }, { 0x08e3U, 0x24U }, { 0x08f1U, 0xc0U },
    /* SLVS-EC link rate & PLL (0x09xx) */
    { 0x0911U, 0x9fU }, { 0x0924U, 0x30U }, { 0x0925U, 0x12U }, { 0x0926U, 0x5aU },
    { 0x0936U, 0x00U },
};

/* Mode-1 LiveView sensor configuration burst 1 (14 writes). */
static const struct imx284_reg_write imx284_mode1_regs_1[] = {
    { 0x094fU, 0x00U }, { 0x0950U, 0x50U }, { 0x0951U, 0x30U }, { 0x0952U, 0x10U },
    { 0x0953U, 0x30U }, { 0x0954U, 0x00U }, { 0x0984U, 0x00U }, { 0x0994U, 0x78U },
    { 0x0995U, 0x00U }, { 0x0996U, 0x22U }, { 0x0997U, 0x35U }, { 0x099cU, 0x07U },
    { 0x09acU, 0x00U }, { 0x0abaU, 0x10U },
};

enum {
    IMX284_REG_STREAM_LATCH = 0x0832U,
    IMX284_LINK_MODE_STREAM_LATCH = 3U,
    IMX284_SETTING_USE_PROFILE = UINT8_MAX,
};

struct imx284_mode1_profile {
    uint8_t link_mode;
    uint8_t stream_latch_setting;
};

/* Inputs implied by the two enabled latch writes in the live Mode-1 trace. */
static const struct imx284_mode1_profile imx284_live_mode1_profile = {
    .link_mode = IMX284_LINK_MODE_STREAM_LATCH,
    .stream_latch_setting = IMX284_SETTING_USE_PROFILE,
};

/* Mode-1 frame-synchronous streaming trigger, after the three latch writes. */
static const struct imx284_reg_write imx284_mode1_stream_commit[] = {
    /* Integration & frame-sync readout commit (0x00xx) */
    { 0x0025U, 0x03U }, { 0x0025U, 0x03U }, { 0x0019U, 0x0fU }, { 0x001aU, 0x00U },
    { 0x001bU, 0x05U }, { 0x0021U, 0x66U }, { 0x0022U, 0x0eU }, { 0x0023U, 0x66U },
    { 0x0024U, 0xceU }, { 0x0028U, 0x8dU }, { 0x002bU, 0x95U }, { 0x002cU, 0x1cU },
    { 0x002dU, 0x1cU }, { 0x002eU, 0x1cU }, { 0x002fU, 0x1cU }, { 0x0032U, 0x0bU },
    { 0x0033U, 0x0bU }, { 0x0037U, 0x00U }, { 0x0038U, 0x99U }, { 0x0039U, 0x99U },
    { 0x003aU, 0x99U }, { 0x003bU, 0x99U }, { 0x003cU, 0x00U }, { 0x003dU, 0x33U },
    { 0x003eU, 0x33U }, { 0x003fU, 0x0fU }, { 0x0040U, 0x99U }, { 0x0041U, 0x99U },
    { 0x0042U, 0x11U }, { 0x0043U, 0x11U }, { 0x0044U, 0x05U }, { 0x0045U, 0x01U },
    { 0x0046U, 0x00U }, { 0x0047U, 0x02U }, { 0x0048U, 0x00U }, { 0x0049U, 0x01U },
    { 0x004aU, 0x00U }, { 0x004bU, 0x11U }, { 0x004cU, 0x63U }, { 0x004dU, 0x01U },
    { 0x004eU, 0x11U }, { 0x007cU, 0x06U },
    /* Analog & SLVS-EC final commit (0x08xx - 0x09xx) */
    { 0x082bU, 0x85U }, { 0x0863U, 0x0cU }, { 0x099cU, 0x07U },
};

/* FUN_637ad06c sends configuration through the software trigger and
 * queues the stream commit on the vertical-sync trigger.
 */
static int imx284_prepare_mode1(void) {
    return IMX284_SEND_REGS(imx284_mode1_regs_0, 2U, 1) &&
           IMX284_SEND_REGS(imx284_mode1_regs_1, 2U, 1);
}

static int imx284_arm_mode1_stream(const struct imx284_mode1_profile *profile) {
    /* FUN_637abea4 updates the record referenced twice at the head of the list. */
    uint8_t latch = profile->link_mode == IMX284_LINK_MODE_STREAM_LATCH &&
                    profile->stream_latch_setting == IMX284_SETTING_USE_PROFILE
                    ? IMX284_LINK_MODE_STREAM_LATCH : 0U;
    struct imx284_reg_write ops[3U + sizeof(imx284_mode1_stream_commit) /
                                    sizeof(imx284_mode1_stream_commit[0])] = {
        { IMX284_REG_STREAM_LATCH, latch },
        { IMX284_REG_STREAM_LATCH, latch },
        { IMX284_REG_STREAM_LATCH, 0U },
    };
    for (uint32_t i = 0U; i < sizeof(imx284_mode1_stream_commit) /
                               sizeof(imx284_mode1_stream_commit[0]); ++i) {
        ops[3U + i] = imx284_mode1_stream_commit[i];
    }
    return IMX284_SEND_REGS(ops, 0U, 0);
}

static int imx284_wake_sequence(void) {
    imx284_pmic_spi_enable();
    imx284_pin_set_level(IMX284_PIN_WAKE_A0, 1);
    imx284_pin_set_level(IMX284_PIN_WAKE_A2, 1);
    imx284_pin_set_level(IMX284_PIN_WAKE_A1, 1);
    dsb();

    if (!IMX284_SEND_REGS(imx284_wake_regs_0, 2U, 1) ||
        !IMX284_SEND_REGS(imx284_wake_regs_0, 2U, 1) ||
        !sleep_us(12000U) ||
        !IMX284_SEND_REGS(imx284_wake_regs_1, 2U, 1) ||
        !IMX284_SEND_REGS(imx284_wake_regs_2, 2U, 1) ||
        !sleep_us(6000U)) {
        return 0;
    }

    imx284_pin_disable(IMX284_PIN_WAKE_B2);
    imx284_pin_set_level(IMX284_PIN_WAKE_B0, 1);
    imx284_pin_set_level(IMX284_PIN_WAKE_B1, 1);
    imx284_pin_set_level(IMX284_PIN_WAKE_B2, 1);
    dsb();
    return sleep_us(20000U);
}

#endif /* IMX284_SENSOR_H */
