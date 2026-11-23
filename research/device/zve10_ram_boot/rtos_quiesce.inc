/* SPDX-License-Identifier: GPL-2.0 */
/* Quiesce non-display platform IRQ, timer, and DMA engines after handoff. */

.equ GICC_BASE, 0xf8000100
.equ GICD_BASE, 0xf8001000
.equ LOCAL_TMR, 0xf8000600
.equ XDMAC0_BASE, 0xf0000000
.equ XDMAC1_BASE, 0xf0010000
.equ DMA330_BASE, 0xf0030000

quiesce_platform:
    push {r4-r7,lr}

    /* 1. Mask and disable GIC CPU interface, distributor, and local timer. */
    ldr r0, =GICC_BASE
    mov r1, #0
    str r1, [r0]
    ldr r0, =GICD_BASE
    str r1, [r0]
    mov r2, #0xffffffff
    add r3, r0, #0x180         /* GICD_ICENABLER0..7 */
    add r4, r0, #0x280         /* GICD_ICPENDR0..7 */
    mov r5, #8
1:
    str r2, [r3],#4
    str r2, [r4],#4
    subs r5, r5, #1
    bne 1b

    ldr r0, =LOCAL_TMR
    str r1, [r0,#8]            /* PTWD_CTRL = 0 */
    mov r2, #1
    str r2, [r0,#12]           /* PTWD_INTSTAT = 1 */

    /* 2. Disable both XDMAC units via verified XDDES (+0x18) = 0. */
    ldr r0, =XDMAC0_BASE
    str r1, [r0,#0x18]
    ldr r0, =XDMAC1_BASE
    str r1, [r0,#0x18]

    /* 3. Mask/clear DMA330 interrupts and DMAKILL any active threads. */
    ldr r0, =DMA330_BASE
    str r1, [r0,#0x20]         /* INTEN = 0 */
    mov r2, #0xffffffff
    str r2, [r0,#0x2c]         /* INTCLR = 0xffffffff */

    mov r4, #0                 /* ch = 0..3 */
2:
    add r3, r0, #0x100
    ldr r2, [r3,r4,lsl #3]     /* csr[ch] */
    tst r2, #0xf
    beq 3f
    mov r5, r4, lsl #8
    orr r5, r5, #0x010000
    orr r5, r5, #1             /* DMAKILL thread ch */
    bl dma330_dbg_cmd
3:
    add r4, r4, #1
    cmp r4, #4
    blo 2b

    ldr r2, [r0]               /* dsr */
    tst r2, #0xf
    beq 4f
    mov r5, #1                 /* DMAKILL manager */
    bl dma330_dbg_cmd
4:
    /* 4. Ensure Output 1 control and mixer are disabled. */
    ldr r0, =0xf3440184
    mov r1, #0
    str r1, [r0]
    ldr r0, =0xf3446000
    str r1, [r0]

    dsb sy
    isb sy
    pop {r4-r7,pc}

/* Issue DBGINST0=r5, DBGCMD=0 on DMA330 (r0) once DBGSTATUS bit 0 is clear. */
dma330_dbg_cmd:
    mov r6, #4096
5:
    ldr r7, [r0,#0xd00]        /* DBGSTATUS */
    tst r7, #1
    beq 6f
    subs r6, r6, #1
    bne 5b
    bx lr
6:
    str r5, [r0,#0xd08]        /* DBGINST0 */
    mov r7, #0
    str r7, [r0,#0xd04]        /* DBGCMD */
    bx lr
