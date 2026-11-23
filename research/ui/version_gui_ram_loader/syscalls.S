.syntax unified
.cpu cortex-a5
.thumb
.section .text.syscalls,"ax",%progbits
.macro syscall name,number
.global \name
.type \name,%function
.thumb_func
\name:
    push {r7,lr}
    ldr r7, =\number
    svc #0
    pop {r7,pc}
.size \name, .-\name
.endm
syscall ram_open,5
syscall ram_read,3
syscall ram_close,6
syscall ram_mprotect,125
syscall ram_munmap,91
syscall ram_cacheflush,0x0f0002
.global ram_mmap2
.type ram_mmap2,%function
.thumb_func
ram_mmap2:
    push {r4,r5,r7,lr}
    ldr r4,[sp,#16]
    ldr r5,[sp,#20]
    movs r7,#192
    svc #0
    pop {r4,r5,r7,pc}
.size ram_mmap2, .-ram_mmap2
.ltorg
