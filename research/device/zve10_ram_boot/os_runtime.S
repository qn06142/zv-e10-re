/* SPDX-License-Identifier: GPL-2.0 */
/* CPU0 resident runtime; inherited MMU/DRAM. No Linux calls or flash writes.
 * Watchdog sequence follows Sony mach-cxd900x0/wdt.c WDT_SET_STOP.
 * A battery restart is required to exit this image. */
.syntax unified
.cpu cortex-a5
.arm
.section .text,"ax",%progbits
.balign 32
.global os_entry
.type os_entry,%function
os_entry:
    b runtime_entry
    b runtime_fault
    b runtime_fault
    b runtime_fault
    b runtime_fault
    b runtime_fault
    b runtime_fault
    b runtime_fault
runtime_entry:
    cpsid if
    mov sp, r1
    mov r10, r0
#ifdef ZVE10_RTOS_LOADER
    adr r2, runtime_info_slot
    str r10, [r2]
#endif
    ldr r4, [r10,#4]
    ldr r9, [r10,#8]
    ldr r5, [r10,#12]
    /* Disable watchdog reset gate, then stop/clear board watchdog timer.
       Other stopped CPUs can no longer feed their banked watchdogs. */
    mov r2, #0x10
    str r2, [r9,#4]       /* MISC_RSTREQ_CLR, EN only */
    movw r7, #0x2000
    movt r7, #0xf240
    mov r2, #0
    str r2, [r7]          /* TIMERCTL=0 */
    mov r2, #0x11
    str r2, [r7,#4]       /* TIMERCLR=TMCLR|TMINTCLR */
    dsb sy
    /* Private ARM vectors replace Linux exception dispatch. MMU retained. */
    adr r2, os_entry
    mcr p15, 0, r2, c12, c0, 0
    mrc p15, 0, r3, c1, c0, 0
    bic r3, r3, #0x2000   /* SCTLR.V=0: use VBAR */
    mcr p15, 0, r3, c1, c0, 0
    isb sy
    movw r2, #0x4e32
    movt r2, #0x5255
    str r2, [r10,#16]     /* RUN2 */
    mov r6, #1
    str r6, [r4,#0x44]
    str r6, [r4,#0x28]
    add r7, r4, #0x2000
    str r6, [r7,#0x24]
    str r6, [r7,#0x34]
    str r6, [r7,#0x44]
    str r6, [r4,#4]
#ifdef ZVE10_OSD_COMPARE
    ldr r2, [r10,#28]
    cmp r2, #0
    bne runtime_fault
#endif
#ifdef ZVE10_OSD_FIRE
    ldr r3, [r10,#36]
    cmp r3, #0
    beq 4f
    mov r0, r10
    blx r3
    b runtime_fault
4:
#endif
#ifdef ZVE10_RTOS_LOADER
    ldr r3, [r10,#40]
    ldr r0, [r10,#44]
    blx r3
    cmp r0, #0
    bne runtime_fault
#endif
    mov r8, #0
runtime_loop:
#ifdef ZVE10_DISPLAY_TEST
    bl runtime_display_white
#endif
    str r6, [r4,#0x48]    /* on */
    bl runtime_delay
#ifdef ZVE10_DISPLAY_TEST
    bl runtime_display_black
#endif
    str r6, [r4,#0x44]    /* off */
    bl runtime_delay
    add r8, r8, #1
    str r8, [r10,#20]     /* owned-RAM heartbeat counter */
    b runtime_loop
runtime_delay:
#ifdef ZVE10_OSD_COMPARE
    ldr r0, [r10,#32]     /* OSD0 AIF control, after first in-range sample */
    cmp r0, #0
    beq runtime_idle_delay
    mov r12, #640
    movs r1, r5, lsr #6
    moveq r1, #1
1:  ldr r2, [r0]
    cmp r2, #2             /* known OSD0 control state with start clear */
    bne 2f
    mov r2, #3
    str r2, [r0]           /* same owned buffer and channel configuration */
    dsb sy
2:  mov r3, r1
3:  subs r3, r3, #1
    bne 3b
    subs r12, r12, #1
    bne 1b
    bx lr
runtime_idle_delay:
#endif
    mov r12, #10
1:  mov r3, r5
2:  subs r3, r3, #1
    bne 2b
    subs r12, r12, #1
    bne 1b
    bx lr
#ifdef ZVE10_DISPLAY_TEST
/* Native VPH output colour fields: Y/Cb/Cr in bits 23:16/15:8/7:0.
 * Control bits 25/24 are the same pair used by the native mute path.
 * Preserve every other upper control bit and all panel timing registers. */
runtime_display_white:
    movw r2, #0x8080
    movt r2, #0x00eb
    b runtime_display_write
runtime_display_black:
    movw r2, #0x8080
    movt r2, #0x0010
runtime_display_write:
    movw r11, #0x5108
    movt r11, #0xf344
    ldr r3, [r11]
    and r3, r3, #0xff000000
    orr r3, r3, #0x03000000
    orr r2, r2, r3
    str r2, [r11]
    dsb sy
    bx lr
#endif
runtime_fault:
#ifdef ZVE10_RTOS_LOADER
    adr r10, runtime_info_slot
    ldr r10, [r10]
    ldr r4, [r10,#4]
#endif
#ifdef ZVE10_OSD_FIRE
    ldr r4, [r10,#4]
#endif
    /* No banked exception stack required. Solid LED; no stock handler calls. */
    mov r6, #1
    str r6, [r4,#0x48]
    movw r2, #0x4c54
    movt r2, #0x4641
    str r2, [r10,#24]     /* FALT */
#ifdef ZVE10_RTOS_LOADER
/* Failure code already stored in the loader-owned handoff result word.
 * Avoid a stack and Linux calls so this also works from a fault vector. */
rtos_report_fault:
    ldr r7, [r10,#44]
    cmp r7, #0
    beq rtos_solid
    ldr r2, [r7,#8]
    cmp r2, #40
    bne rtos_solid
    ldr r8, [r7,#28]
    subs r2, r8, #1
    cmp r2, #6
    bhi rtos_solid
    ldr r9, =0xf240310c
    str r6, [r4,#0x44]
rtos_fault_group:
    mov r7, r8
rtos_fault_pulse:
    str r6, [r4,#0x48]
    bl rtos_fault_delay
    str r6, [r4,#0x44]
    bl rtos_fault_delay
    subs r7, r7, #1
    bne rtos_fault_pulse
    mov r7, #7
rtos_fault_gap:
    bl rtos_fault_delay
    subs r7, r7, #1
    bne rtos_fault_gap
    b rtos_fault_group
rtos_fault_delay:
    ldr r0, [r9]
    ldr r1, =700000
    ldr r2, =16000000
1:  ldr r3, [r9]
    sub r3, r3, r0
    cmp r3, r1
    bxhs lr
    subs r2, r2, #1
    bne 1b
rtos_solid:
    str r6, [r4,#0x48]
2:  b 2b
.balign 4
runtime_info_slot:
    .word 0
#else
3:  b 3b
#endif
.ltorg
.size os_entry, .-os_entry
