/* SPDX-License-Identifier: GPL-2.0 */
#include "rtos_abi.h"

.syntax unified
.cpu cortex-a5
.arm
.section .text,"ax",%progbits
.global os_entry
.type os_entry,%function
os_entry:
    push {r4-r8,lr}
    mov r4, r0
    ldr r1, [r4,#ZVRT_H_MAGIC]
    ldr r2, =ZVRT_HANDOFF_MAGIC
    cmp r1, r2
    bne bad
    ldr r1, [r4,#ZVRT_H_VERSION]
    cmp r1, #ZVRT_ABI_VERSION
    bne bad
    ldr r1, [r4,#ZVRT_H_BYTES]
    cmp r1, #ZVRT_H_SIZE
    bne bad
    ldr r1, [r4,#ZVRT_H_FLAGS]
    cmp r1, #ZVRT_OWNED_ARENA
    bne bad
    ldr r5, [r4,#ZVRT_H_ARENA_VA]
    ldr r6, [r4,#ZVRT_H_ARENA_BYTES]
    cmp r5, #0
    beq bad
    tst r5, #15
    bne bad
    cmp r6, #128
    blo bad
    tst r6, #15
    bne bad
    adds r2, r5, r6
    bcs bad
    mov r1, r5
    mov r0, #64
    bl arena_alloc
    cmp r0, r5
    bne bad
    mov r7, r0
    sub r0, r6, #64
    bl arena_alloc
    add r8, r5, #64
    cmp r0, r8
    bne bad
    cmp r1, r2
    bne bad
    mov r0, #1
    bl arena_alloc
    cmp r0, #0
    bne bad
    ldr r3, =ZVRT_PROBE_OK
    str r3, [r7]
    str r3, [r2,#-4]
    str r3, [r4,#ZVRT_H_RESULT]
    mov r0, #0
    pop {r4-r8,pc}
bad:
    mov r0, #1
    pop {r4-r8,pc}

/* r1 is the 16-byte-aligned cursor, r2 the exclusive end. */
arena_alloc:
    cmp r0, #0
    beq exhausted
    adds r3, r0, #15
    bcs exhausted
    bic r3, r3, #15
    adds r3, r1, r3
    bcs exhausted
    cmp r3, r2
    bhi exhausted
    mov r0, r1
    mov r1, r3
    bx lr
exhausted:
    mov r0, #0
    bx lr
.ltorg
.size os_entry, .-os_entry
