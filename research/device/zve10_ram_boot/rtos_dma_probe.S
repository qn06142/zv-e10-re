/* SPDX-License-Identifier: GPL-2.0 */
/* Read-only post-GO DMA observation. Runs under the v1 trampoline mappings. */
#include "rtos_abi.h"

.syntax unified
.cpu cortex-a5
.arm
.section .text,"ax",%progbits
.global os_entry
.type os_entry,%function

/* Board scheduler timer runs at 2 MHz. */
.equ TIMER_READ, 0xf240310c
.equ LED_GPIO, 0xf2910000
.equ SAMPLE_TICKS, 4000
.equ PULSE_TICKS, 700000
.equ GROUP_GAP_PULSES, 8
.equ SAMPLE_COUNT, 80
.equ WAIT_LIMIT, 16000000

os_entry:
    push {r4-r11,r12,lr}
    mov r4, r0
    ldr r1, [r4,#ZVRT_H_MAGIC]
    ldr r2, =ZVRT_HANDOFF_MAGIC
    cmp r1, r2
    bne invalid
    ldr r1, [r4,#ZVRT_H_VERSION]
    cmp r1, #ZVRT_ABI_VERSION
    bne invalid
    ldr r1, [r4,#ZVRT_H_BYTES]
    cmp r1, #ZVRT_H_SIZE
    bne invalid
    ldr r1, [r4,#ZVRT_H_FLAGS]
    cmp r1, #ZVRT_OWNED_ARENA
    bne invalid
    ldr r5, [r4,#ZVRT_H_ARENA_VA]
    cmp r5, #0
    beq invalid
    tst r5, #15
    bne invalid
    ldr r1, [r4,#ZVRT_H_ARENA_BYTES]
    cmp r1, #256
    blo invalid
    adds r1, r5, #256
    bcs invalid

    ldr r9, =TIMER_READ
#ifdef ZVRT_AIF_STOP
    mov r0, #0
    str r0, [r5,#12]
    bl stop_display_aif
    cmp r0, #0
    bne invalid
#endif
    adr r6, sample_words
    mov r8, #0
    mov r10, #0
    mov r11, #0
    bl sample
    mov r11, #1
    mov r7, #SAMPLE_COUNT
observe:
    mov r0, #SAMPLE_TICKS
    bl wait_ticks
    cmp r0, #0
    bne invalid
    bl sample
    subs r7, r7, #1
    bne observe

    str r8, [r5,#4]
    str r10, [r5,#8]
    orr r8, r8, r10
    str r8, [r5]
    str r8, [r4,#ZVRT_H_RESULT]
    cmp r8, #0
    beq quiet

    /* One long pulse per mask value, with a long dark gap between groups. */
    ldr r10, =LED_GPIO
group:
    mov r7, r8
pulse:
    mov r0, #1
    str r0, [r10,#0x48]
    ldr r0, =PULSE_TICKS
    bl wait_ticks
    cmp r0, #0
    bne invalid
    mov r0, #1
    str r0, [r10,#0x44]
    subs r7, r7, #1
    beq gap_begin
    ldr r0, =PULSE_TICKS
    bl wait_ticks
    cmp r0, #0
    beq pulse
    b invalid
gap_begin:
    mov r7, #GROUP_GAP_PULSES
gap:
    ldr r0, =PULSE_TICKS
    bl wait_ticks
    cmp r0, #0
    bne invalid
    subs r7, r7, #1
    bne gap
    b group
invalid:
    mov r0, #1
    pop {r4-r11,r12,pc}
quiet:
    mov r0, #0
    pop {r4-r11,r12,pc}

/* r8 records changed words, r10 records busy fields. Both use engine masks. */
sample:
    mov r0, r6
    add r1, r5, #16
1:  ldmia r0!, {r2,r3,r12}
    cmp r2, #0
    bxeq lr
    ldr r2, [r2]
    tst r2, r3
    orrne r10, r10, r12
    cmp r11, #0
    ldrne r3, [r1]
    cmpne r2, r3
    orrne r8, r8, r12
    str r2, [r1],#4
    b 1b

/* Unsigned difference handles wrap. Limit a stalled timer independently. */
wait_ticks:
    ldr r1, [r9]
    ldr r2, =WAIT_LIMIT
2:  ldr r3, [r9]
    sub r3, r3, r1
    cmp r3, r0
    bhs quiet_tick
    subs r2, r2, #1
    bne 2b
    mov r0, #1
    bx lr
quiet_tick:
    mov r0, #0
    bx lr

#ifdef ZVRT_AIF_STOP
#include "rtos_aif_stop.inc"
#endif

.balign 4
sample_words:
    /* XDMAC XDDSD. Read-form only and change detection only. */
    .set ch, 0
    .rept 4
    .word 0xf0000030 + ch * 0x30, 0, 1
    .word 0xf0010030 + ch * 0x30, 0, 1
    .set ch, ch + 1
    .endr
    /* DMA330 manager and four thread states. */
    .word 0xf0030000, 0xf, 2
    .set ch, 0
    .rept 4
    .word 0xf0030100 + ch * 8, 0xf, 2
    .set ch, ch + 1
    .endr
    /* VPH AIF channel status and current address. */
    .set ch, 0
    .rept 8
    .word 0xf3441204 + ch * 0x80, 0x80000000, 4
    .word 0xf3441210 + ch * 0x80, 0, 4
    .set ch, ch + 1
    .endr
    .word 0, 0, 0
.ltorg
.size os_entry, .-os_entry
