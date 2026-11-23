/* SPDX-License-Identifier: GPL-2.0 */
/* C runtime startup: quiesce platform, build 1 GiB DDR0 L1 MMU table, relocate to 0x81000000, enter rtos_main(). */

#include "zvrt_runtime.h"

.syntax unified
.arm

.equ ZVRT_H_MAGIC,        0
.equ ZVRT_H_VERSION,      4
.equ ZVRT_H_BYTES,        8
.equ ZVRT_H_FLAGS,        12
.equ ZVRT_H_ARENA_VA,     16
.equ ZVRT_H_ARENA_PA,     20
.equ ZVRT_H_ARENA_BYTES,  24
.equ ZVRT_H_RESULT,       28
.equ ZVRT_H_CLEAN_FRAME,  32
.equ ZVRT_H_FRAME_BYTES,  36
.equ ZVRT_H_CLIP_VA,      40
.equ ZVRT_H_CLIP_BYTES,   44
.equ ZVRT_H_SIZE,         32
.equ ZVRT_H_CLIP_SIZE,    48

.equ ZVRT_HANDOFF_MAGIC,  0x4852565a
.equ ZVRT_ABI_VERSION,    1
.equ ZVRT_ARENA_MIN,      0x10000
.equ ZVRT_PROBE_FAIL,     0x4641494c

.equ CLIP_DDR0_VA,        0x84000000
.equ IMAGE_DDR0_VA,       0x81000000
.equ IMAGE_DDR0_PA,       0x21000000
.equ C_STACK_TOP,         0x82000000
.equ L1_DRAM_FLAGS,       0x0001140e
.equ L1_DRAM_NC_FLAGS,    0x00011402  /* Shared Normal, Inner and Outer Non-cacheable. */
.equ L1_DEV_FLAGS,        0x00000406

.equ PL310_BASE,          0xf8002000
.equ LED_GPIO,            0xf2910000
.equ TIMER_READ,          0xf240310c

.section .text.boot, "ax"
.global _start
.type _start, %function
_start:
    /* Running PIC at load_base (0x5fxxxxxx) with r0 = &zvrt_handoff. */
    push {r4-r11,r12,lr}
    mov r4, r0
    adr r11, _start

    /* Validate handoff header before touching hardware. */
    ldr r0, [r4,#ZVRT_H_MAGIC]
    ldr r1, =ZVRT_HANDOFF_MAGIC
    cmp r0, r1
    bne pre_mmu_fail
    ldr r0, [r4,#ZVRT_H_VERSION]
    cmp r0, #ZVRT_ABI_VERSION
    bne pre_mmu_fail
    ldr r0, [r4,#ZVRT_H_BYTES]
    cmp r0, #ZVRT_H_SIZE
    blo pre_mmu_fail
    ldr r0, [r4,#ZVRT_H_ARENA_BYTES]
    cmp r0, #ZVRT_ARENA_MIN
    blo pre_mmu_fail
    ldr r5, [r4,#ZVRT_H_ARENA_VA]
    cmp r5, #0
    beq pre_mmu_fail

    /* Quiesce GIC, local timer, XDMAC0/1, DMA330, and Output 1. */
    bl quiesce_platform

    /* 1. Zero 16 KiB L1 table at arena_va + 0x0000. */
    mov r1, r5
    add r2, r5, #0x4000
    mov r3, #0
1:
    str r3, [r1],#4
    cmp r1, r2
    blo 1b

    /* 2. Map 1 GiB DDR0 1:1 (0x000..0x3ff) and +0x60000000 (0x600..0x9ff). */
    ldr r3, =L1_DRAM_FLAGS
    mov r6, #0
    add r7, r5, #(0x600 * 4)
2:
    orr r1, r3, r6, lsl #20
    str r1, [r5,r6,lsl #2]
    str r1, [r7,r6,lsl #2]
    add r6, r6, #1
    cmp r6, #0x400
    blo 2b

    /* Use identical attributes in both aliases of the display and DMA ranges. */
    ldr r3, =L1_DRAM_NC_FLAGS
    ldr r6, =(ZVRT_DISPLAY_PA >> 20)
    ldr r2, =(ZVRT_NC_TOTAL_END >> 20)
21:
    orr r1, r3, r6, lsl #20
    str r1, [r5,r6,lsl #2]
    str r1, [r7,r6,lsl #2]
    add r6, r6, #1
    cmp r6, r2
    blo 21b

    ldr r6, =(ZVRT_STILL_RAW_PA >> 20)
    ldr r2, =(ZVRT_STILL_RAW_END >> 20)
22:
    orr r1, r3, r6, lsl #20
    str r1, [r5,r6,lsl #2]
    str r1, [r7,r6,lsl #2]
    add r6, r6, #1
    cmp r6, r2
    blo 22b

    /* 3. Map Device MMIO 0xf0000000..0xffffffff (0xf00..0xfff). */
    ldr r3, =L1_DEV_FLAGS
    mov r6, #0xf00
3:
    orr r1, r3, r6, lsl #20
    str r1, [r5,r6,lsl #2]
    add r6, r6, #1
    cmp r6, #0x1000
    blo 3b

    /* 3b. Temporarily copy active TTBR0[0x5f0..0x5ff] (module_alloc) and
     * TTBR0[0xa00..0xeff] (vmalloc clip.bin) if TTBR0 is set, so we can switch
     * TTBR0 before touching 0x81000000 or 0x84000000. */
    mrc p15, 0, r1, c2, c0, 0
    ldr r2, =0xffffc000
    and r1, r1, r2
    cmp r1, #0
    beq 31f
    add r1, r1, #0x60000000
    add r2, r1, #(0x5f0 * 4)
    add r3, r5, #(0x5f0 * 4)
    mov r6, #16
30:
    ldr r8, [r2],#4
    str r8, [r3],#4
    subs r6, r6, #1
    bne 30b
    add r2, r1, #(0xa00 * 4)
    add r3, r5, #(0xa00 * 4)
    mov r6, #1280
301:
    ldr r8, [r2],#4
    str r8, [r3],#4
    subs r6, r6, #1
    bne 301b
31:

    /* 4. Copy zvrt_handoff (48 bytes) to arena_va + 0x7000. */
    add r7, r5, #0x7000
    mov r1, r4
    mov r2, r7
    mov r6, #12
4:
    ldr r3, [r1],#4
    str r3, [r2],#4
    subs r6, r6, #1
    bne 4b

    /* Clean L1 table (arena_va + 0x0000..0x4000) and handoff (+0x7000..+0x7040) before TTBR0 switch. */
    mov r1, r5
    add r6, r5, #0x7100
40:
    mcr p15, 0, r1, c7, c10, 1
    add r1, r1, #32
    cmp r1, r6
    blo 40b
    dsb sy

    ldr r2, =PL310_BASE
    ldr r1, [r2,#0x100]
    tst r1, #1
    beq 43f
    ldr r1, [r7,#ZVRT_H_ARENA_PA]
    add r6, r1, #0x7100
41:
    str r1, [r2,#0x7b0]
    add r1, r1, #32
    cmp r1, r6
    blo 41b
    mov r1, #0
    str r1, [r2,#0x730]
42:
    ldr r1, [r2,#0x730]
    tst r1, #1
    bne 42b
    dsb sy
43:
    /* Switch TTBR0/TTBCR=0 now so full 1 GiB DDR0 (0x81000000, 0x84000000) is mapped. */
    ldr r6, [r7,#ZVRT_H_ARENA_PA]
    ldr r0, =0x55555555
    mcr p15, 0, r0, c3, c0, 0
    mov r0, #0
    mcr p15, 0, r0, c2, c0, 2
    orr r0, r6, #0x4a
    mcr p15, 0, r0, c2, c0, 0
    mov r0, #0
    mcr p15, 0, r0, c8, c7, 0
    mcr p15, 0, r0, c7, c5, 6
    dsb sy
    isb sy

    /* 5. If clip.bin was staged, copy it to CLIP_DDR0_VA (0x84000000). */
    ldr r1, [r7,#ZVRT_H_BYTES]
    cmp r1, #ZVRT_H_CLIP_SIZE
    blo 6f
    ldr r1, [r7,#ZVRT_H_CLIP_VA]
    ldr r2, [r7,#ZVRT_H_CLIP_BYTES]
    cmp r1, #0
    cmpeq r2, #0
    beq 6f
    ldr r3, =CLIP_DDR0_VA
    str r3, [r7,#ZVRT_H_CLIP_VA]
    add r6, r2, #3
    bic r6, r6, #3
5:
    ldr r8, [r1],#4
    str r8, [r3],#4
    subs r6, r6, #4
    bhi 5b
    ldr r1, =CLIP_DDR0_VA
    add r6, r1, r2
51:
    mcr p15, 0, r1, c7, c10, 1
    add r1, r1, #32
    cmp r1, r6
    blo 51b
    dsb sy
6:
    /* 6. Copy full image [ _start .. __image_end ) to IMAGE_DDR0_VA (0x81000000). */
    mov r1, r11
    ldr r2, =IMAGE_DDR0_VA
    ldr r8, =__image_end
    sub r8, r8, r2
    add r8, r8, #3
    bic r8, r8, #3
    add r6, r2, r8
7:
    ldr r3, [r1],#4
    str r3, [r2],#4
    cmp r2, r6
    blo 7b

    /* Clean L1 D-cache for arena_va..+0x8000 and IMAGE_DDR0_VA..+image_bytes. */
    mov r1, r5
    add r6, r5, #0x8000
8:
    mcr p15, 0, r1, c7, c10, 1
    add r1, r1, #32
    cmp r1, r6
    blo 8b
    ldr r1, =IMAGE_DDR0_VA
    add r6, r1, r8
80:
    mcr p15, 0, r1, c7, c10, 1
    add r1, r1, #32
    cmp r1, r6
    blo 80b
    dsb sy

    /* Clean PL310 L2 if enabled for arena_pa..+0x8000 and IMAGE_DDR0_PA..+image_bytes. */
    ldr r2, =PL310_BASE
    ldr r1, [r2,#0x100]
    tst r1, #1
    beq 9f
    ldr r1, [r7,#ZVRT_H_ARENA_PA]
    add r6, r1, #0x8000
81:
    str r1, [r2,#0x7b0]
    add r1, r1, #32
    cmp r1, r6
    blo 81b
    ldr r1, =IMAGE_DDR0_PA
    add r6, r1, r8
82:
    str r1, [r2,#0x7b0]
    add r1, r1, #32
    cmp r1, r6
    blo 82b
    mov r1, #0
    str r1, [r2,#0x730]
83:
    ldr r1, [r2,#0x730]
    tst r1, #1
    bne 83b
    dsb sy
9:
    mov r1, #0
    mcr p15, 0, r1, c7, c5, 0   /* ICIALLU */
    dsb sy
    isb sy

    /* Jump into relocated 0x81000000 image before switching TTBR0. */
    ldr r1, =c_mmu_relocated
    bx r1

pre_mmu_fail:
    ldr r1, =ZVRT_PROBE_FAIL
    str r1, [r4,#ZVRT_H_RESULT]
    mov r0, #1
    pop {r4-r11,r12,pc}

c_mmu_relocated:
    add r4, r5, #0x7000

    /* Remove temporary 0x5f0..0x5ff and 0xa00..0xeff mappings and install real VBAR. */
    add r1, r5, #(0x5f0 * 4)
    mov r2, #0
    mov r6, #16
90:
    str r2, [r1],#4
    subs r6, r6, #1
    bne 90b
    add r1, r5, #(0xa00 * 4)
    mov r6, #1280
91:
    str r2, [r1],#4
    subs r6, r6, #1
    bne 91b
    dsb sy

    ldr r0, =_vectors
    mcr p15, 0, r0, c12, c0, 0
    mov r0, #0
    mcr p15, 0, r0, c8, c7, 0
    mcr p15, 0, r0, c7, c5, 6
    dsb sy
    isb sy

    /* Zero .bss [ __bss_start .. __bss_end ). */
    ldr r1, =__bss_start
    ldr r2, =__bss_end
    mov r3, #0
bss_loop:
    cmp r1, r2
    bhs bss_done
    str r3, [r1],#4
    b bss_loop
bss_done:

    /* Set IRQ stack (0x81FF0000) and SVC stack (0x82000000), then call rtos_main(). */
    cps #0x12
    ldr sp, =(C_STACK_TOP - 0x10000)
    cps #0x13
    ldr sp, =C_STACK_TOP
    mov r0, r4
    bl rtos_main

    /* If rtos_main returns, report code 6 via LED blink. */
    mov r0, #6
    b zvrt_report_error

fault_undef:
    mov r0, #1
    b zvrt_report_error
fault_svc:
    mov r0, #2
    b zvrt_report_error
fault_pabt:
    mov r0, #3
    b zvrt_report_error
fault_dabt:
    mov r0, #4
    b zvrt_report_error
fault_irq:
    sub lr, lr, #4
    stmfd sp!, {r0-r3,r12,lr}
    bl zvrt_irq_dispatch
    ldmfd sp!, {r0-r3,r12,pc}^

fault_fiq:
    mov r0, #5
    b zvrt_report_error

/* Blink LED_GPIO r0 times (150 ms on/off), pause 1 s, repeat forever. */
.global zvrt_report_error
.type zvrt_report_error, %function
zvrt_report_error:
    cpsid if
    mov r4, r0
    cmp r4, #0
    moveq r4, #1
    ldr r5, =LED_GPIO
    ldr r6, =TIMER_READ
err_cycle:
    mov r7, r4
err_blink:
    mov r1, #1
    str r1, [r5,#0x44]
    ldr r8, [r6]
1:
    ldr r1, [r6]
    sub r1, r1, r8
    ldr r2, =150000
    cmp r1, r2
    blo 1b

    mov r1, #1
    str r1, [r5,#0x48]
    ldr r8, [r6]
2:
    ldr r1, [r6]
    sub r1, r1, r8
    ldr r2, =150000
    cmp r1, r2
    blo 2b

    subs r7, r7, #1
    bne err_blink

    ldr r8, [r6]
3:
    ldr r1, [r6]
    sub r1, r1, r8
    ldr r2, =1000000
    cmp r1, r2
    blo 3b
    b err_cycle

.align 5
.global _vectors
_vectors:
    b zvrt_report_error  /* Reset */
    b fault_undef        /* Undefined Instruction (code 1) */
    b fault_svc          /* SVC (code 2) */
    b fault_pabt         /* Prefetch Abort (code 3) */
    b fault_dabt         /* Data Abort (code 4) */
    b fault_undef        /* Unused */
    b fault_irq          /* IRQ (dispatched via GIC) */
    b fault_fiq          /* FIQ (code 5) */

.include "rtos_quiesce.inc"
