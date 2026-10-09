# Sony ZV-E10 Open Gate 3:2 Pre-Compiled Binaries & Staging Kit

This directory contains verified, production-ready ARM binaries compiled for the Sony ZV-E10 (Cortex-A7 softfp).

## Binary Manifest

| File | Size (Bytes) | MD5 | Description |
|---|---|---|---|
| `opengate.so` | 8,592 | `88bf6c6c8d1f3099081f8cc9a730fd82` | Unified `LD_PRELOAD` in-memory patch library (v2.1 dynamic aspect + OSD) |
| `mem_patch.elf` | 6,124 | `1fdf3b050d2427a7c5b6bc6b9f1d06b5` | Standalone volatile memory patching utility |
| `opengate.conf` | 375 | - | Runtime configuration file for `/setting/opengate.conf` |
| `install_opengate.sh` | 1,845 | - | Staging script (installs to `/setting/` & configures `/etc/ld.so.preload`) |
| `uninstall_opengate.sh` | 1,046 | - | Clean removal script (reverts all in-memory hooks) |

## Quick Deployment onto Hardware

1. Push all files into `/setting/` via Senser USB Shell:
   ```bash
   python research/device/push_opengate.py
   ```
2. On camera shell:
   ```sh
   sh /setting/install_opengate.sh
   reboot
   ```
3. Verification:
   ```sh
   cat /setting/opengate.log
   ```
