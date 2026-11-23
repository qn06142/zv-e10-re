/* SPDX-License-Identifier: GPL-2.0 */
/* Static RGBA4444 scanout from one drained, validated stock OSD0 slot. */
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
.equ WAIT_LIMIT, 16000000
.equ FRAME_BYTES, 614400
.equ PITCH, 1280
.equ HEIGHT, 480

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
    bne failed
    ldr r1, [r4,#ZVRT_H_FLAGS]
    cmp r1, #(ZVRT_OWNED_ARENA | ZVRT_DISPLAY_REUSE)
    bne failed
    ldr r5, [r4,#ZVRT_H_ARENA_VA]
    cmp r5, #0
    beq failed
    tst r5, #15
    bne failed
    ldr r1, [r4,#ZVRT_H_ARENA_BYTES]
    cmp r1, #64
    blo failed
    adds r1, r5, #64
    bcs failed
    ldr r1, [r4,#ZVRT_H_FRAME_BYTES]
    ldr r2, =FRAME_BYTES
    cmp r1, r2
    bne failed
    DEMO_STAGE 2
    /* Bind a live 640x480 Route 1 OSD0 descriptor whose buffer owns OSD0+0x10. */
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

    DEMO_STAGE 5
    /* Verify that no AIF channel rearmed before using the old OSD slot. */
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
    str r0, [r5,r11,lsl #2]  /* Snapshots at +4 through +32. */
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
    DEMO_STAGE 6
    add r0, r7, #0x60000000
    mov r10, #HEIGHT
paint_row:
    adr r2, palette
    mov r11, #8
paint_bar:
    ldrh r1, [r2],#2
    orr r1, r1, r1, lsl #16
    mov r12, #40
paint_pixels:
    str r1, [r0],#4
    subs r12, r12, #1
    bne paint_pixels
    subs r11, r11, #1
    bne paint_bar
    subs r10, r10, #1
    bne paint_row
    dsb sy

    /* Clean L1 D-cache by MVA across the painted framebuffer. */
    add r0, r7, #0x60000000
    ldr r1, =FRAME_BYTES
    add r1, r0, r1
clean_l1:
    mcr p15, 0, r0, c7, c10, 1
    add r0, r0, #32
    cmp r0, r1
    blo clean_l1
    dsb sy

    /* Clean PL310 L2 cache by PA if enabled at 0xf8002100. */
    ldr r2, =0xf8002000
    ldr r0, [r2,#0x100]
    tst r0, #1
    beq clean_done
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
clean_done:
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
    bic r1, r1, #1        /* Leave OSD0 over the background, without old YUV. */
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
    bhs failed
    subs r12, r12, #1
    bne observe_frame
    b failed

first_frame:
    ldr r0, =ZVRT_PROBE_OK
    str r0, [r4,#ZVRT_H_RESULT]
    ldr r7, =LED_GPIO
    mov r8, #0x48
heartbeat:
    mov r1, #1
    str r1, [r7,r8]
    eor r8, r8, #0x0c
    ldr r10, [r9]
    ldr r11, =1000000
    ldr r12, =WAIT_LIMIT
sustain:
    ldr r1, [r6]
    cmp r1, #2
    moveq r1, #3
    streq r1, [r6]
    ldr r1, [r9]
    sub r1, r1, r10
    cmp r1, r11
    bhs heartbeat
    subs r12, r12, #1
    bne sustain

failed:
    mov r0, #1
    pop {r4-r11,r12,pc}

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
palette:
    .hword 0xffff, 0xff0f, 0x0fff, 0x0f0f, 0xf0ff, 0xf00f, 0x00ff, 0x000f
#include "rtos_aif_stop.inc"
.ltorg
.size os_entry, .-os_entry
