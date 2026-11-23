/* SPDX-License-Identifier: GPL-2.0 */
#ifndef ZVOS_MODE_H
#define ZVOS_MODE_H

#include "zvrt_runtime.h"

#define ZVOS_KEY_UP    (1U << 0)
#define ZVOS_KEY_DOWN  (1U << 1)
#define ZVOS_KEY_LEFT  (1U << 2)
#define ZVOS_KEY_RIGHT (1U << 3)
#define ZVOS_KEY_OK    (1U << 4)
#define ZVOS_KEY_MENU  (1U << 5)
#define ZVOS_KEY_REC   (1U << 6)

enum os_tick_result {
    OS_TICK_DRAW,
    OS_TICK_EXIT,
    OS_TICK_HOLD,
};

struct os_mode {
    const char *name;
    int (*enter)(const struct zvrt_handoff *handoff);
    enum os_tick_result (*tick)(uint32_t keys_pressed, uint16_t *fb);
    void (*exit)(void);
};

#endif
