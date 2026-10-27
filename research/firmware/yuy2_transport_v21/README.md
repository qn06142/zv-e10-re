# YUY2 RAM transport revision 2.1

This source-only recipe produces synthetic 640×480 YUY2/10 fps. Live test: USB enumeration and source allocation succeeded; FFmpeg captured zero frames. See [the live report](../../../docs/uvc_yuy2_patch_v21.md).

Revision 2.1 removes the premature staging requirement from Ready connect preflight. Driver staging is checked before each submission, with a maximum of 30 nominal 100 ms missing-staging polls. Source capacity, overflow, staging capacity and non-overlap remain guarded. Source ownership, main-thread error recovery, DMA pinning and lifecycle hooks are retained from revision 2.

Use the project Python environment with Capstone, Keystone, Unicorn and pyelftools, ARM GCC, the inspected camera sysroot/dump, and checked-startup streaming image MD5 `19461091c07aa6900829defb0060fcd6`. Run `build.py` then `verify.py` with explicit `--repo`, `--output`, `--streaming-image` and actual `--stream-base`; run `verify_bootstrap.py --output ... --stream-base ...`, then `package.py --repo ... --output ...`. Expected: 35 compiled ARM cases and four Thumb loader cases. Hardware services are mocked in these checks.

Generated binaries stay outside the repository. Installation artifacts arm two guarded RAM writes only, then the module loads on normal video prepare. Check live maps and all firmware/config guards; never bypass them. Current tested bases: streaming `0x0a73a000`, common `0x04834000`, libdl `0x040ba000`. A new map requires rebuild and verification. Never unload or replace a module with active hooks. Uncertain DMA pins the owned source until completion or genuine reboot. Power-switch hibernation can preserve the entire RAM patch.
