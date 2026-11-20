# Returning privileged entry probe

18 November 2026, Senser service session: the live Linux 3.0.27_nl-rt106+ kernel maps sys_kexec_load to sys_ni_syscall. A small GPL module was therefore built against the matching prepared Sony GPL kernel headers, with module structure size, init/exit offsets and vermagic checked against the camera's liro.ko.

The 2484-byte returning module (SHA-256 2a2bbe877970fae726a04a44ffda2006f29ab61e0899ad7a90877da450c9c6d1) logged:

    ZVBOOT_GATE_V1 mode=13 sctlr=10c5387d mpidr=80000003 RETURNED

It unloaded cleanly. This establishes privileged module entry and return in Senser; it does not establish a normal-shooting takeover. build.py reads the prepared GPL tree without changing it. The external zve10-qemu checkout supplied that existing tree; QEMU is not this project's work.

The next experiment is the [explicit RAM handoff](../zve10_ram_boot/README.md).
