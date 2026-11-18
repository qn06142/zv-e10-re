## Deployment update — 28 October 2026

INSTALLED AND REBOOT-VERIFIED on camera by user request. Module/wrapper readbacks and postboot hashes match the manifest; streaming code absent from cold maps and /usr read-only. Guarded scripts now exist under deployment/ and passed10 local fixtures; rollback preserves exact3.0 and existing2.4p recovery. Service session closed. No3.1 stream/frame test yet. The following original offline-build/package description is historical; its NOT_INSTALLED/no-installer statements describe build time only. See evidence/install-20261028/deployment-summary.json and current handoff for deployment status.

# Revision 3.1: procfs maps initialization fix

Built 28 October 2026. NOT INSTALLED; no camera actions during this build. Current camera installation remains 3.0, whose user OBS test produced no image.

## Fix

3.0 load_calls() made one read of /proc/self/maps and treated the returned prefix as the entire file. A valid short procfs read can omit libObj.so, so initialization reports GUARD_FAILED and quarantines. The recovered camera maps are 47,338 bytes; the first libObj pathname is at byte 14,704. The 3.0 compiled ARM worker fails with the original Sony files and these captured maps when reads are limited to 2 KiB, but passes if the same maps arrive in one read. This is a reproduced code defect consistent with the hardware failure. The old log has no per-branch reason, so it does not establish which exact target return branch fired.

3.1 reads maps until EOF, retains the 128 KiB bound and terminating NUL, rejects read errors or input exceeding capacity, and accepts an exactly fitting file only after checking EOF. SDK symbol and 16-byte prologue checks, libObj mapping/range/prologue checks and queue validation remain enabled. Distinct failure tags now identify library load, missing SDK symbol, SDK mismatch, maps open/read/empty/overflow, absent libObj mapping, invalid libObj address/range/prologue, or queue initialization. No guards were skipped or weakened. One extra arithmetic overflow check protects private addresses.

## Package

Matched files must be installed together:
- yuy2_640_v31vga.so: MD5 72f800fd8f5e6d943b1d33d173bedeb1, 31,900 bytes.
- libInfraStreamingUsb.so: MD5 24bc5972c11f953ad1408f477376a877, 72,796 bytes; DT_NEEDED names yuy2_640_v31vga.so.

Manifest records SHA256s. This local package contains the patched proprietary wrapper for authorized local deployment; do not commit or publish these binaries. Source and textual evidence belong in Git. No automatic installer is supplied; do not run the 3.0 installer unchanged. A later deployment must guard current 3.0 hashes, preserve its wrapper/producer and existing 2.4p recovery, install the new dependency before the new wrapper, verify readback and read-only mount, and reboot before activating. Never overwrite a mapped producer or reuse a streaming session.

Log directory changes to /log/yuy2_640_v31vga/ and must exist before activation. Capture remains unframed 614,400-byte payloads; use capture_vga.py. No 2.9 packet reassembly, synthetic fallback or proven YUY2 packing. Existing owned metadata, one-session-per-cold-boot rule and quarantine behavior remain.

## Verification

17 compiled ARM initialization cases pass against real Sony ELF prologues and captured target maps, including the old failure/new success differential; reads of 1, 127, 2048, 4096, 8192 and 131071 bytes; missing/empty/oversized maps; exact-capacity EOF; read failure; missing symbol; modified SDK/libObj prologues; zero queues. libc, procfs, dynamic loader and constructor service boundaries are mocked. The script stops at QUEUES or GUARD_FAILED before frame acquisition.

9 inherited host worker scenarios pass; 11 PIC/dynamic-table/no-constructor checks pass; 3 compiled ARM stop/rebind checks pass. Text audit: 4668 instructions, no NEON. Sony constructors and hardware remain mocked; these results do not prove live SSYC discovery, SDF acceptance or pixels. Next hardware test is a fresh-boot guarded installation followed by one bounded capture and log collection. Do not claim a working live webcam until it captures frames.

## Reproduction

Build from source/recipe/build.py with --repo pointing to the repository (matching ignored Sony dumps required), --output outputs/vga-v31/build, and --streaming-image outputs/uvc-startup-fix/candidate-1080p/libInfraStreamingUsb.so. Use the repository venv Python with pyelftools, Keystone, Capstone and Unicorn and the existing ARM compiler/sysroot. verify_loader.py --repo REPO --workspace WORKSPACE reads the prior 3.0 build and saved OBS maps in the workspace. Tests use original firmware for verification; firmware is not bundled in the source publication.
