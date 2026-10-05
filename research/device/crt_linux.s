.syntax unified
.text
.align 2
.global _start
.type _start, %function

_start:
    mov fp, #0
    mov lr, #0
    pop {r1}        /* argc */
    mov r2, sp      /* argv */
    push {r2}       /* stack_end */
    push {r0}       /* rtld_fini */
    ldr ip, =0      /* fini */
    push {ip}
    ldr r0, =main   /* main */
    ldr r3, =0      /* init */
    bl __libc_start_main
    b abort

.size _start, . - _start
