/* SPDX-License-Identifier: GPL-2.0 */
/* Animated 640x480 RGBA4444 procedural fire using a drained stock OSD0 slot. */
#include "rtos_abi.h"

.syntax unified
.cpu cortex-a5
.arm
.section .text,"ax",%progbits
.global os_entry
.type os_entry,%function

.equ VPH, 0xf3440000
.equ OSD0, 0xf3441300
.equ TIMER_READ, 0xf240310c
.equ LED_GPIO, 0xf2910000
.equ PL310_BASE, 0xf8002000
.equ WAIT_LIMIT, 16000000
.equ FRAME_BYTES, 614400
.equ PITCH, 1280
.equ HEIGHT, 480
.equ FIRE_W, 80
.equ FIRE_H, 60
.equ FIRE_PERIOD, 100000
.equ HEAT_OFF, 64
.equ SEED_OFF, 4864

.macro DEMO_STAGE number
    mov r0, #\number
    str r0, [r4,#ZVRT_H_RESULT]
.endm

os_entry:
    push {r4-r11,r12,lr}
    mov r4, r0
    DEMO_STAGE 1
    ldr r1, [r4,#ZVRT_H_MAGIC]
    ldr r2, =ZVRT_HANDOFF_MAGIC
    cmp r1, r2
    bne failed
    ldr r1, [r4,#ZVRT_H_VERSION]
    cmp r1, #ZVRT_ABI_VERSION
    bne failed
    ldr r1, [r4,#ZVRT_H_BYTES]
    cmp r1, #ZVRT_H_DISPLAY_SIZE
    cmpne r1, #ZVRT_H_CLIP_SIZE
    bne failed
    ldr r1, [r4,#ZVRT_H_FLAGS]
    bic r1, r1, #ZVRT_CLIP_LOADED
    cmp r1, #(ZVRT_OWNED_ARENA | ZVRT_DISPLAY_REUSE)
    bne failed
    ldr r5, [r4,#ZVRT_H_ARENA_VA]
    cmp r5, #0
    beq failed
    tst r5, #15
    bne failed
    ldr r1, [r4,#ZVRT_H_ARENA_BYTES]
    ldr r2, =65536
    cmp r1, r2
    blo failed
    adds r1, r5, r2
    bcs failed
    ldr r1, [r4,#ZVRT_H_FRAME_BYTES]
    ldr r2, =FRAME_BYTES
    cmp r1, r2
    bne failed

    DEMO_STAGE 2
    ldr r2, =OSD0
    ldr r9, [r2,#0x10]
    ldr r3, =0x6441b27c
    bl check_osd_slot
    cmp r0, #0
    beq slot_bound
    ldr r3, =0x644194d8
    bl check_osd_slot
    cmp r0, #0
    bne failed
slot_bound:
    str r1, [r5]
    str r3, [r5,#36]

    DEMO_STAGE 3
    ldr r8, =VPH
    add r3, r8, #0x5000
    ldr r1, [r3]
    ldr r2, =0x00010114
    cmp r1, r2
    bne failed
    add r3, r3, #0x1000
    ldr r1, [r3]
    cmp r1, #0
    bne failed
    ldr r1, [r8,#0x144]
    tst r1, #2
    beq failed
    ldr r1, [r8,#0x404]
    tst r1, #1
    bne failed

    DEMO_STAGE 4
    ldr r9, =TIMER_READ
    mov r0, #0
    str r0, [r5,#12]
    bl stop_display_aif
    cmp r0, #0
    bne failed
    bl quiesce_platform

    DEMO_STAGE 5
    ldr r10, =0xf3441200
    mov r11, #8
verify_idle:
    ldr r0, [r10]
    tst r0, #1
    bne failed
    ldr r0, [r10,#4]
    tst r0, #0x80000000
    bne failed
    ldr r0, [r10,#0x10]
    str r0, [r5,r11,lsl #2]
    add r10, r10, #0x80
    subs r11, r11, #1
    bne verify_idle

    ldr r10, [r9]
    ldr r11, =WAIT_LIMIT
wait_idle:
    ldr r0, [r9]
    sub r0, r0, r10
    ldr r1, =40000
    cmp r0, r1
    bhs idle_recheck
    subs r11, r11, #1
    bne wait_idle
    b failed

idle_recheck:
    ldr r10, =0xf3441200
    mov r11, #8
recheck_bank:
    ldr r0, [r10]
    tst r0, #1
    bne failed
    ldr r0, [r10,#4]
    tst r0, #0x80000000
    bne failed
    ldr r0, [r10,#0x10]
    ldr r1, [r5,r11,lsl #2]
    cmp r0, r1
    bne failed
    add r10, r10, #0x80
    subs r11, r11, #1
    bne recheck_bank

    ldr r7, [r5]
    ldr r0, [r5,#36]
    ldr r0, [r0]
    cmp r0, r7
    bne failed

    /* Relocate into arena and switch to self-owned 1 GiB DDR0 + MMIO L1 MMU table. */
    mov r10, r7
    adr r0, os_entry
    bl takeover_mmu
    mov r7, r10
    str r7, [r5]

    DEMO_STAGE 6
    /* Initialize fire PRNG seed and pre-warm 36 procedural steps. */
    ldr r0, =0x5ad0c0de
    ldr r1, =SEED_OFF
    str r0, [r5,r1]
    mov r10, #36
prewarm_loop:
    bl spread_fire
    subs r10, r10, #1
    bne prewarm_loop

    bl paint_fire
    bl clean_frame_cache

    DEMO_STAGE 7
    ldr r8, =VPH
    ldr r6, =OSD0
    mov r0, #0
    str r0, [r6,#0x0c]
    mov r1, #PITCH
    str r1, [r6,#0x24]
    str r7, [r6,#0x20]
    mov r1, #2
    str r1, [r6]
    mov r2, #0x28
clear_geometry:
    str r0, [r6,r2]
    add r2, r2, #4
    cmp r2, #0x44
    bls clear_geometry
    movw r1, #(HEIGHT - 1)
    str r1, [r6,#0x2c]
    mov r2, #0x50
clear_repeat:
    str r0, [r6,r2]
    add r2, r2, #4
    cmp r2, #0x5c
    bls clear_repeat
    str r0, [r6,#0x4c]
    str r0, [r6,#0x70]
    mov r1, #PITCH
    str r1, [r6,#0x48]
    ldr r1, [r8,#0x42c]
    bfc r1, #0, #11
    orr r1, r1, #HEIGHT
    str r1, [r8,#0x42c]
    ldr r1, [r8,#0x144]
    bic r1, r1, #1
    str r1, [r8,#0x144]
    dsb sy
    mov r1, #3
    str r1, [r6]
    dsb sy

    ldr r10, =FRAME_BYTES
    ldr r11, [r9]
    ldr r12, =WAIT_LIMIT
observe_frame:
    ldr r0, [r6,#0x10]
    subs r0, r0, r7
    cmp r0, r10
    blo first_frame
    ldr r0, [r9]
    sub r0, r0, r11
    ldr r1, =160000
    cmp r0, r1
    bhs failed_after_mmu
    subs r12, r12, #1
    bne observe_frame
    b failed_after_mmu

first_frame:
    ldr r0, =ZVRT_PROBE_OK
    str r0, [r4,#ZVRT_H_RESULT]
    mov r8, #0x48
    mov r4, #0

fire_loop:
    ldr r10, [r9]
    ldr r11, =FIRE_PERIOD
    ldr r12, =WAIT_LIMIT
sustain_tick:
    ldr r1, [r6]
    cmp r1, #2
    moveq r1, #3
    streq r1, [r6]
    ldr r1, [r9]
    sub r1, r1, r10
    cmp r1, r11
    bhs next_fire_frame
    subs r12, r12, #1
    bne sustain_tick
    b failed_after_mmu

next_fire_frame:
    bl spread_fire
    /* Sync to the natural frame-end (OSD0 == 2) instead of aborting mid-frame. */
    ldr r10, [r9]
    ldr r11, =30000
    ldr r12, =WAIT_LIMIT
wait_frame_end:
    ldr r1, [r6]
    cmp r1, #2
    beq frame_restart
    ldr r1, [r9]
    sub r1, r1, r10
    cmp r1, r11
    bhs frame_restart
    subs r12, r12, #1
    bne wait_frame_end
frame_restart:
    str r7, [r6,#0x20]
    dsb sy
    mov r1, #3
    str r1, [r6]
    dsb sy
    bl paint_fire
    bl clean_frame_cache

    add r4, r4, #1
    cmp r4, #5
    blo fire_loop
    mov r4, #0
    ldr r0, =LED_GPIO
    mov r1, #1
    str r1, [r0,r8]
    eor r8, r8, #0x0c
    b fire_loop

failed:
    mov r0, #1
    pop {r4-r11,r12,pc}

/* After takeover_mmu, os_runtime at 0x5fxxxxxx is unmapped; blink LED instead of returning. */
failed_after_mmu:
    mov r8, #0x48
    ldr r0, =LED_GPIO
    ldr r9, =TIMER_READ
fail_blink:
    mov r1, #1
    str r1, [r0,r8]
    eor r8, r8, #0x0c
    ldr r10, [r9]
fail_wait:
    ldr r1, [r9]
    sub r1, r1, r10
    ldr r2, =50000
    cmp r1, r2
    blo fail_wait
    b fail_blink

/* Advance fire_heat[60][80] in place at r5 + HEAT_OFF. Preserves r4-r9. */
spread_fire:
    push {r4-r9,lr}
    add r4, r5, #HEAT_OFF
    ldr r2, =SEED_OFF
    ldr r1, [r5,r2]
    mov r6, #0                 /* y = 0..58 */
spread_row:
    add r7, r4, #FIRE_W        /* src row y+1 */
    mov r8, #1                 /* x = 1..78 */
spread_col:
    ldrb r0, [r7,r8]
    lsl r0, r0, #1
    sub r3, r8, #1
    ldrb r3, [r7,r3]
    add r0, r0, r3
    add r3, r8, #1
    ldrb r3, [r7,r3]
    add r0, r0, r3
    lsr r0, r0, #2
    eor r1, r1, r1, lsl #13
    eor r1, r1, r1, lsr #17
    eor r1, r1, r1, lsl #5
    cmp r0, #0
    beq spread_store
    tst r1, #3
    subeq r0, r0, #1
spread_store:
    strb r0, [r4,r8]
    add r8, r8, #1
    cmp r8, #(FIRE_W - 1)
    blo spread_col
    add r4, r4, #FIRE_W
    add r6, r6, #1
    cmp r6, #(FIRE_H - 1)
    blo spread_row

    /* Bottom emitter row y = 59, x = 1..78 -> 11..15 */
    mov r8, #1
    ldr r3, =1664525
    ldr r12, =1013904223
bottom_col:
    mla r1, r1, r3, r12
    lsr r0, r1, #29
    cmp r0, #5
    subhs r0, r0, #5
    add r0, r0, #11
    strb r0, [r4,r8]
    add r8, r8, #1
    cmp r8, #(FIRE_W - 1)
    blo bottom_col

    ldr r2, =SEED_OFF
    str r1, [r5,r2]
    pop {r4-r9,pc}

/* Expand fire_heat[60][80] 8x8 into 640x480 RGBA4444 at r7 + 0x60000000. */
paint_fire:
    push {r4-r11,lr}
    add r0, r7, #0x60000000
    add r4, r5, #HEAT_OFF
    adr r11, fire_palette
    mov r6, #FIRE_H
paint_heat_row:
    mov r8, #8
paint_sub_row:
    mov r9, #0
paint_heat_col:
    ldrb r1, [r4,r9]
    add r1, r1, r1
    ldrh r1, [r11,r1]
    orr r1, r1, r1, lsl #16
    mov r2, r1
    mov r3, r1
    mov r12, r1
    stmia r0!, {r1,r2,r3,r12}
    add r9, r9, #1
    cmp r9, #FIRE_W
    blo paint_heat_col
    subs r8, r8, #1
    bne paint_sub_row
    add r4, r4, #FIRE_W
    subs r6, r6, #1
    bne paint_heat_row
    dsb sy
    pop {r4-r11,pc}

/* Clean L1 D-cache by MVA and PL310 L2 cache by PA for framebuffer at r7. */
clean_frame_cache:
    add r0, r7, #0x60000000
    ldr r1, =FRAME_BYTES
    add r1, r0, r1
clean_l1:
    mcr p15, 0, r0, c7, c10, 1
    add r0, r0, #32
    cmp r0, r1
    blo clean_l1
    dsb sy

    ldr r2, =PL310_BASE
    ldr r0, [r2,#0x100]
    tst r0, #1
    bxeq lr
    mov r0, r7
    ldr r1, =FRAME_BYTES
    add r1, r0, r1
clean_l2:
    str r0, [r2,#0x7b0]
    add r0, r0, #32
    cmp r0, r1
    blo clean_l2
    mov r0, #0
    str r0, [r2,#0x730]
wait_l2_sync:
    ldr r0, [r2,#0x730]
    tst r0, #1
    bne wait_l2_sync
    dsb sy
    bx lr

/* Drain OSD0 (r6) before rewriting the live framebuffer. */
pause_osd0:
    ldr r2, [r6,#4]
    bic r2, r2, #1
    str r2, [r6,#4]
    ldr r1, [r6]
    bic r1, r1, #1
    str r1, [r6]
    ldr r2, [r6,#4]
    orr r2, r2, #0x40000000
    str r2, [r6,#4]
    dsb sy

    ldr r10, [r9]
    ldr r11, =WAIT_LIMIT
    ldr r12, =160000
pause_wait:
    ldr r2, [r6,#4]
    tst r2, #0x80000000
    beq pause_drained
    ldr r2, [r9]
    sub r2, r2, r10
    cmp r2, r12
    bhs pause_timeout
    subs r11, r11, #1
    bne pause_wait
pause_timeout:
    mov r0, #1
    bx lr
pause_drained:
    ldr r2, [r6,#8]
    orr r2, r2, #0x80000000
    str r2, [r6,#8]
    dsb sy
    mov r0, #0
    bx lr

check_osd_slot:
    ldr r1, [r3,#4]
    ldr r2, =0x01e00280
    cmp r1, r2
    bne slot_bad
    ldr r1, [r3,#0x0c]
    cmp r1, r2
    bne slot_bad
    ldr r1, [r3,#8]
    ldr r2, [r3,#0x10]
    orrs r1, r1, r2
    bne slot_bad
    ldr r1, [r3,#0x1c]
    ldr r2, [r3,#0x20]
    orrs r1, r1, r2
    bne slot_bad
    ldr r1, [r3,#0x30]
    cmp r1, #0
    beq slot_bad
    ldr r1, [r3]
    tst r1, #7
    bne slot_bad
    ldr r2, =0x01000000
    cmp r1, r2
    blo slot_bad
    ldr r2, =(0x3f000000 - FRAME_BYTES)
    cmp r1, r2
    bhi slot_bad
    sub r0, r9, r1
    ldr r2, =FRAME_BYTES
    cmp r0, r2
    bhs slot_bad
    mov r0, #0
    bx lr
slot_bad:
    mov r0, #1
    bx lr

.balign 4
fire_palette:
    .hword 0x000f, 0x200f, 0x400f, 0x600f, 0x810f, 0xa10f, 0xc20f, 0xe30f
    .hword 0xf40f, 0xf50f, 0xf70f, 0xf90f, 0xfb1f, 0xfd4f, 0xff9f, 0xffff
#include "rtos_aif_stop.inc"
#include "rtos_quiesce.inc"
#include "rtos_mmu.inc"
.ltorg
.size os_entry, .-os_entry
