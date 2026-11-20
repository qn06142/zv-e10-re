# Version-screen RAM payload loader

18 November 2026: installed and fully read back through Senser. The owner confirmed HELLO on the physical Version screen after restarting and entering Up → Down → Left → Right → Up. This verifies a returning user-space payload, not an OS handoff.

Installed viewUnified6.so: 656918 bytes, SHA-256 c993e1be8ca352de663c4f66bd6df227262fe4697b7c793c9561ef3e8b3e6f70. The GUI loads /log/zve10-ram-loader/payload.bin anew on each confirmed sequence. Center retains the original exit result in source/offline checks.

The ZVRAM001 header contains version 1, header size 32, body length (2–2048 bytes), even Thumb entry offset, CRC32 and ABI 1. The loader checks the header and bounds, maps RW, reads and validates the body, changes it to RX, flushes the instruction cache, calls the Thumb entry with the API in payload.h, then unmaps it. CRC detects corruption; it provides no authentication or sandbox. Payloads run with im.elf's privileges.

build.py builds the GUI library; build_payload.py builds replacement payloads without rebuilding the GUI. offline-verification.json records original-instruction tests, two load biases, replacement payloads and failure cases. The hardware HELLO observation is separate from those offline checks.

The active payload has subsequently been replaced by the [RAM boot launcher](../../device/zve10_ram_boot/README.md). The previous HELLO bytes are retained on-camera at /log/zve10-ram-boot/previous-hello.payload.bin. Existing /usr library backups remain intact; no boot selection or av-cam.bin replacement was made.
