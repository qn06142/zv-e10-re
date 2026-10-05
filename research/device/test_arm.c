void _start(void) {
    const char msg[] = "Sidecar OSD Harness OK!\n";
    register int r0 __asm__("r0") = 1;
    register const char* r1 __asm__("r1") = msg;
    register int r2 __asm__("r2") = sizeof(msg) - 1;
    register int r7 __asm__("r7") = 4; // sys_write
    __asm__ volatile("svc #0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory");

    register int exit_code __asm__("r0") = 0;
    register int sys_exit __asm__("r7") = 1; // sys_exit
    __asm__ volatile("svc #0" : : "r"(exit_code), "r"(sys_exit));
}
