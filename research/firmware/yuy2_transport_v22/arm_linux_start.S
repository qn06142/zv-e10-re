.syntax unified
.arm
.global _start
.type _start,%function
_start:
    mov fp,#0
    mov lr,#0
    pop {r1}
    mov r2,sp
    push {r2}
    push {r0}
    push {lr}
    ldr r0,=main
    mov r3,#0
    bl __libc_start_main
    mov r7,#1
    svc #0
