# YUY2 RAM transport revision 2.2

This revision fixes the manager-lifetime restart defect while retaining one exclusively allocated source for the module lifetime. See [candidate report](../../../docs/uvc_yuy2_patch_v22.md) for behavior, tradeoff and hardware status.

Use project Python with Capstone/Keystone/Unicorn/pyelftools, ARM GCC, camera sysroot/dump and checked-startup streaming image MD5 `19461091c07aa6900829defb0060fcd6`. Run `build.py` and `verify.py` with explicit `--repo`, `--output`, `--streaming-image`, `--stream-base`; then `verify_bootstrap.py --output ... --stream-base ...` and `package.py --repo ... --output ...`. Expected: 42 ARM cases plus four bootstrap cases. All hardware services are mocked offline. Generated files belong outside the repo.

The package installs only guarded process-memory bootstrap writes; the module loads on normal video prepare. Confirm required firmware/config hashes, actual maps and old-module absence. Never bypass guards or hot-swap a loaded patch. A genuine reboot removes hooks and the retained buffer; power-switch hibernation may preserve them. Hardware frame delivery remains unproven.
