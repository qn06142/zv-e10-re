.syntax unified
.cpu cortex-a5
.thumb
.section .text.hooks,"ax",%progbits
.global ctor_hook, trigger_hook, format_hook, exit_hook
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
    mov r1, r2
    adr r2, .Lexit_code
    adds r2, #1
    bl init_state
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
    mov r0, r2
    mov r1, r4
    bl process_event
    tst r0, #2
    it ne
    movne r5, #0
    tst r0, #1
    beq .Ldone
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

.type exit_hook,%function
.thumb_func
exit_hook:
.Lexit_code:
    push {r4-r6,lr}
    mov r4, r0
    ldr r0, .Lstate_exit_delta
.Lstate_exit_pc:
    add r0, pc
    ldr r6, [r0,#16]
    bl reset_state
    mov r0, r4
    blx r6
    pop {r4-r6,pc}
.balign 4
.Lstate_exit_delta: .word state_address - (.Lstate_exit_pc + 4)
.size exit_hook, .-exit_hook
