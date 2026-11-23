/* SPDX-License-Identifier: GPL-2.0 */
/* Self-owned 16 KiB ARMv7 L1 MMU table (1 GiB DDR0 + MMIO) and relocation. */

.equ CLIP_DDR0_PA, 0x24000000
.equ CLIP_DDR0_VA, 0x84000000
.equ L1_DRAM_FLAGS, 0x0001140e   /* Section, AP=RW, TEX=1, C=1, B=1, S=1 */
.equ L1_DEV_FLAGS, 0x00000406    /* Section, AP=RW, Shared Device (B=1) */

/* Called after quiesce_platform with r0 = runtime os_entry, r4 = &zvrt_handoff,
 * r5 = arena_va (64 KiB). Relocates os_entry (<= 4 KiB) to arena_va + 0x4000,
 * builds L1 table at arena_va, switches TTBR0/TTBCR/VBAR, and returns to caller
 * in relocated arena with r5 = arena_va + 0x8000 and r4 = arena_va + 0x7000.
 */
takeover_mmu:
    /* Preserve os_entry in r11 and return offset relative to os_entry in r12. */
    mov r11, r0
    sub r12, lr, r11

    /* 1. Zero 16 KiB L1 table at r5 (arena_va + 0x0000). */
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

    /* 3. Map Device MMIO 0xf0000000..0xffffffff (0xf00..0xfff). */
    ldr r3, =L1_DEV_FLAGS
    mov r6, #0xf00
3:
    orr r1, r3, r6, lsl #20
    str r1, [r5,r6,lsl #2]
    add r6, r6, #1
    cmp r6, #0x1000
    blo 3b

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

    /* 5. If clip.bin was staged via vmalloc, copy it to CLIP_DDR0_VA (0x84000000). */
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
    /* Clean clip range from L1 D-cache. */
    ldr r1, =CLIP_DDR0_VA
    add r6, r1, r2
51:
    mcr p15, 0, r1, c7, c10, 1
    add r1, r1, #32
    cmp r1, r6
    blo 51b
    dsb sy
6:
    /* 6. Copy os_entry (4 KiB) to arena_va + 0x4000. */
    mov r1, r11
    add r2, r5, #0x4000
    add r6, r2, #0x1000
7:
    ldr r3, [r1],#4
    str r3, [r2],#4
    cmp r2, r6
    blo 7b

    /* 7. Clean L1 D-cache + PL310 L2 for arena_va + 0x0000..0x8000, invalidate I-cache. */
    mov r1, r5
    add r6, r5, #0x8000
8:
    mcr p15, 0, r1, c7, c10, 1
    add r1, r1, #32
    cmp r1, r6
    blo 8b
    dsb sy

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
    mov r1, #0
    str r1, [r2,#0x730]
82:
    ldr r1, [r2,#0x730]
    tst r1, #1
    bne 82b
    dsb sy
9:
    mov r1, #0
    mcr p15, 0, r1, c7, c5, 0   /* ICIALLU */
    dsb sy
    isb sy

    /* Jump into relocated arena_va + 0x4000 before switching TTBR0. */
    add r2, r5, #0x4000
    adr r1, mmu_relocated
    sub r1, r1, r11
    add r1, r2, r1
    bx r1

mmu_relocated:
    add sp, r5, #0x8000
    sub sp, sp, #16
    add r4, r5, #0x7000
    ldr r6, [r4,#ZVRT_H_ARENA_PA]

    /* Point VBAR to relocated image, set client DACR, switch TTBR0/TTBCR=0. */
    add r0, r5, #0x4000
    mcr p15, 0, r0, c12, c0, 0
    ldr r0, =0x55555555
    mcr p15, 0, r0, c3, c0, 0
    mov r0, #0
    mcr p15, 0, r0, c2, c0, 2   /* TTBCR = 0 */
    orr r0, r6, #0x4a           /* Inner/Outer WBWA + Shareable */
    mcr p15, 0, r0, c2, c0, 0   /* TTBR0 */
    mov r0, #0
    mcr p15, 0, r0, c8, c7, 0   /* TLBIALL */
    mcr p15, 0, r0, c7, c5, 6   /* BPIALL */
    dsb sy
    isb sy

    /* Upper 32 KiB of arena is scratch (r5 = arena_va + 0x8000). */
    add r5, r5, #0x8000
    sub r0, r5, #0x4000        /* relocated os_entry base */
    add pc, r0, r12
