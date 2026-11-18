# ZV-E10 diagnostic tools

These source files were copied byte for byte from the 17 November session into the repository on 18 November 2026.

- [zve10-regs.c](zve10-regs.c) implements a small ARM Linux register snapshot using ptrace.
- [zve10-trace](zve10-trace) reads the existing LiRo trace buffer through /tmp/busybox.

The installed paths were /tmp/zve10-tools/zve10-regs and /tmp/zve10-tools/zve10-trace. Their availability on a later boot must be checked. The existing full BusyBox stays at /tmp/busybox.

The historical Windows build used Zig 0.15.2.

```powershell
$zig = 'PATH_TO_ZIG/zig.exe'
& $zig cc -target arm-linux-musleabi -mcpu=cortex_a9 -static -Oz -Wall -Wextra -Werror -s -o zve10-regs zve10-regs.c
```

The resulting tested file was 25,908 bytes, SHA-256 c53c7fc7f76c0dda2d7fd88dafea799c7f47238eb9f945f95062c579de01d568. The hardware inventory identifies Cortex-A5. The historical cortex_a9 build option is retained here as provenance. Check generated instructions against the camera architecture when rebuilding or extending it.

The hardware smoke test attached to a disposable sleep process, printed registers, detached and confirmed State S and TracerPid 0. No attach to im.elf was tested. Register capture pauses the selected thread and does not implement stack unwinding, breakpoints or a GDB server.

The trace reader alone can return a repeated or empty window. The [access guide](../../../docs/ACCESS_AND_TOOLS.md) documents the explicit rearm sequence verified on hardware. The last capture left tmonitor stopped.
