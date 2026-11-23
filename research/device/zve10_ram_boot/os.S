/* SPDX-License-Identifier: GPL-2.0 */
/* Minimal non-returning ARM image: private stack, inherited MMU, GPIO pulses, reset. */
.syntax unified
.cpu cortex-a5
.arm
.section .text,"ax",%progbits
.global os_entry
.type os_entry,%function
os_entry:
    cpsid if
    mov sp, r1
    ldr r4, [r0,#4]       /* mapped GPIO base */
    ldr r9, [r0,#8]       /* mapped MISC reset-set register */
    ldr r5, [r0,#12]      /* calibrated ~50 ms loop count */
    movw r2, #0x5452
    movt r2, #0x454e
    str r2, [r0,#16]      /* entry marker in owned boot-info RAM */
    mov r6, #1
    str r6, [r4,#0x44]    /* LED off (active low) */
    str r6, [r4,#0x28]    /* disable input on LED pin */
    add r7, r4, #0x2000
    str r6, [r7,#0x24]
    str r6, [r7,#0x34]
    str r6, [r7,#0x44]
    str r6, [r4,#4]       /* output direction, bit 0 only */
    mov r8, #3
1:  str r6, [r4,#0x48]    /* on */
    mov r3, r5
2:  subs r3, r3, #1
    bne 2b
    str r6, [r4,#0x44]    /* off */
    mov r3, r5
3:  subs r3, r3, #1
    bne 3b
    subs r8, r8, #1
    bne 1b
    mov r2, #0x11        /* Sony force reset: RSTREQ_EN | RSTREQ_ASSERT */
    str r2, [r9]
    dsb sy
4:  b 4b
.size os_entry, .-os_entry
