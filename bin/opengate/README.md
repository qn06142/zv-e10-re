# Sony ZV-E10 Open Gate staging recipes

This directory retains historical staging scripts, configuration and binary identities. Generated opengate.so and mem_patch.elf are local build artifacts and are ignored by Git. Their earlier compilation used Cortex-A7 softfp. Hardware compatibility and the installed state need the matching experiment evidence. See the [current checkpoint](../../docs/CURRENT_STATUS.md) before using a deployment recipe.

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
