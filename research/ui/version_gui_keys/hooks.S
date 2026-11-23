.syntax unified
.cpu cortex-a5
.thumb
.section .text.hooks,"ax",%progbits
.global ctor_hook, trigger_hook, format_hook
.type ctor_hook,%function
.thumb_func
ctor_hook:
    push {r4-r6,lr}
    ldr r3, .Lctor_delta
.Lctor_pc:
    add r3, pc
    blx r3
    ldr r2, .Lstate_ctor_delta
.Lstate_ctor_pc:
    add r2, pc
    str r0, [r2]
    movs r3, #0
    str r3, [r2,#4]
    str r3, [r2,#8]
    str r3, [r2,#12]
    pop {r4-r6,pc}
.balign 4
.Lctor_delta: .word original_ctor - (.Lctor_pc + 4)
.Lstate_ctor_delta: .word state_address - (.Lstate_ctor_pc + 4)
.size ctor_hook, .-ctor_hook
.type trigger_hook,%function
.thumb_func
trigger_hook:
    push {r4-r7,lr}
    sub sp, #4
    mov r4, r0
    ldr r3, .Ltrigger_delta
.Ltrigger_pc:
    add r3, pc
    blx r3
    mov r5, r0
    lsrs r3, r4, #16
    movw r2, #0x1501
    cmp r3, r2
    beq .Lcapture
    adds r2, #1
    cmp r3, r2
    bne .Ldone
.Lcapture:
    ldr r2, .Lstate_trigger_delta
.Lstate_trigger_pc:
    add r2, pc
    ldr r6, [r2]
    cbz r6, .Ldone
    ldr r3, [r6,#4]
    cmp r3, #1
    bne .Ldone
    ldr.w r3, [r6,#0x174]
    cmp r3, #1
    bne .Ldone
    str r4, [r2,#4]
    ldr r3, [r2,#8]
    adds r3, #1
    str r3, [r2,#8]
    mov r0, r6
    movs r1, #3
    ldr r3, .Llayout_delta
.Llayout_pc:
    add r3, pc
    blx r3
.Ldone:
    mov r0, r5
    add sp, #4
    pop {r4-r7,pc}
.balign 4
.Ltrigger_delta: .word original_transform - (.Ltrigger_pc + 4)
.Lstate_trigger_delta: .word state_address - (.Lstate_trigger_pc + 4)
.Llayout_delta: .word original_layout - (.Llayout_pc + 4)
.size trigger_hook, .-trigger_hook
.type format_hook,%function
.thumb_func
format_hook:
    ldr r2, .Lstate_format_delta
.Lstate_format_pc:
    add r2, pc
    b.w format_keys
.balign 4
.Lstate_format_delta: .word state_address - (.Lstate_format_pc + 4)
.size format_hook, .-format_hook
