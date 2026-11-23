/* SPDX-License-Identifier: GPL-2.0 */
/* These are VPH channel IDs, in MMIO bank order. */
.equ AIF_MODE_TABLE, 0x643eb19c
.equ AIF_STOP_TIMEOUT, 160000

stop_display_aif:
    push {r3,lr}
    adr r6, aif_channels
guard_next:
    ldmia r6!, {r0,r12}
    cmp r0, #0
    beq stop_begin
    ldr r1, [r0]
    ldr r2, [r0,#4]
    tst r1, #1
    tsteq r2, #0x80000000
    beq guard_next
    bl check_primary_path
    cmp r3, #0
    bne stop_failed
    b guard_next

stop_begin:
    adr r6, aif_channels
    mov r7, #1
stop_next:
    ldmia r6!, {r0,r12}
    cmp r0, #0
    beq stop_done
    ldr r1, [r0]
    ldr r2, [r0,#4]
    tst r1, #1
    tsteq r2, #0x80000000
    beq next_bank
    bl check_primary_path
    cmp r3, #0
    bne stop_failed

    /* Clear active latches, then request native drain. */
    bic r2, r2, #1
    str r2, [r0,#4]
    bic r1, r1, #1
    str r1, [r0]
    ldr r2, [r0,#4]
    orr r2, r2, #0x40000000
    str r2, [r0,#4]
    dsb sy

    ldr r10, [r9]
    ldr r11, =WAIT_LIMIT
    ldr r12, =AIF_STOP_TIMEOUT
drain:
    ldr r2, [r0,#4]
    tst r2, #0x80000000
    beq drained
    ldr r2, [r9]
    sub r2, r2, r10
    cmp r2, r12
    bhs stop_failed
    subs r11, r11, #1
    bne drain
    b stop_failed
drained:
    ldr r2, [r0,#8]
    orr r2, r2, #0x80000000
    str r2, [r0,#8]
    dsb sy
    ldr r2, [r5,#12]
    orr r2, r2, r7
    str r2, [r5,#12]
next_bank:
    lsl r7, r7, #1
    b stop_next
stop_done:
    mov r0, #0
    b stop_return
stop_failed:
    mov r0, #1
stop_return:
    pop {r3,pc}

check_primary_path:
    /* Fill mode or a different software sentinel requires a second handshake. */
    tst r1, #0x800
    bne wrong_path
    ldr r3, =AIF_MODE_TABLE
    ldr r3, [r3,r12,lsl #2]
    movw r12, #0x22b
    cmp r3, r12
    moveq r3, #0
    bxeq lr
wrong_path:
    mov r3, #1
    bx lr

.balign 4
aif_channels:
    .word 0xf3441200, 0x39
    .word 0xf3441280, 0x3a
    .word 0xf3441300, 0x3b
    .word 0xf3441380, 0x3c
    .word 0xf3441400, 0x3d
    .word 0xf3441480, 0x40
    .word 0xf3441500, 0x3e
    .word 0xf3441580, 0x3f
    .word 0, 0
