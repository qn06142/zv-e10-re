# Original-menu adapter provenance

The optional menu profile builds from a read-only snapshot of `zve10-qemu`
commit `42554a639e005455a1cc492744bd77341e7c41d2`. Its original menu adapter
is copyright (c) 2026 chocotan, licensed under the MIT License. The full
license is included in the pinned inputs and copied to the local build tree.
`menu_reference.json` records the SHA-256 of every imported build input.
No imported firmware, kernel image, shared library, or CPIO is tracked here.

`build_menu.py` copies those inputs into ignored local storage and compiles
there. `menu_osd.h` connects the guest's completed RGBA4444 present operation
to the standalone OSD0 device. Host code displays and verifies those pixels;
it does not draw menu rows, labels, or icons.

This is an explicit adapted application profile: the reference UI kernel,
AP-only service selection, DMA330 stub, and CPU replacements for supported
GPU/LDEC operations are used. It is separate from unmodified stock normal
boot. The menu uses original Sony resources and native direction events;
physical panel input, Enter/Menu business actions, capture, and recording
are not validated by this profile.

The generated init script replaces the inherited process/thread dump with a
persistent application wait to avoid exhausting the UI kernel's ASID pool.
English is the default: original English text banks are routed at the bank
paths selected by the captured locale. The source banks and captured camera
settings remain unchanged; `--language captured` restores the original bank.
