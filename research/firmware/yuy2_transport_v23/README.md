# YUY2 revision 2.3 — paired kernel/userspace candidate

This candidate retains revision 2.2's synthetic 640×480 YUY2 producer and manager-lifetime restart correction. It adds a kernel module patch that makes actual probe responses match the 614,400-byte frame, one-header 614,412-byte transfer, and 10 fps interval. The PAL/NTSC override is skipped. EOF is asserted for the complete frame; this is an interoperability improvement, not a claim that EOF was the proven original cause.

Run with project Python (Capstone, Keystone, Unicorn and pyelftools), the ARM compiler and existing camera sysroot:

```powershell
python -B kernel_patch.py --input <repo>/dumps/camera_2025/usr/usr/kmod/usbg_video.ko --output <output>/usbg_video.ko
python -B verify_kernel.py --stock <repo>/dumps/camera_2025/usr/usr/kmod/usbg_video.ko --candidate <output>/usbg_video.ko
python -B build.py --repo <repo> --output <output> --streaming-image <checked-startup-image> --stream-base <actual-base>
python -B verify.py --repo <repo> --output <output> --streaming-image <checked-startup-image> --stream-base <actual-base>
python -B verify_bootstrap.py --output <output> --stream-base <actual-base>
python -B package.py --repo <repo> --output <output>
```

The checked startup image must have MD5 `19461091c07aa6900829defb0060fcd6`. The stock kernel module must have MD5 `5b59c2e62c80683d754955ab5de0467d`. Kernel patching checks whole-file identity, all six sites, and absence of loader relocations at modified sites. It refuses existing output files and already-patched or otherwise modified input. `kernel_patch.py --reverse` restores the exact stock bytes, after validating the candidate. Keep generated binaries outside the source repository.

Expected verification: 42 compiled ARM producer/lifecycle cases, four Thumb bootstrap cases, and 14 kernel checks. Kernel tests execute actual probe construction for stock/patched modes 0–3, and both FID/EOF byte variants, and verify reversibility, guards and changed-byte scope. Services and state are simulated; there is no UDC/Windows emulation.

Both components are required. No installer is emitted: loading a kernel file and patching im.elf RAM have different activation lifetimes. Deployment must verify the actual loaded module and fresh process map, after clearing old hooks. The candidate kernel must not be activated alone with the stock MJPEG producer. A file hash does not prove that the same bytes are running. Retain the stock kernel for rollback and restore it before returning to a stock-only streaming stack.

Hardware validation must check enumeration, host probe/commit acceptance, frames matching expected bars/counter, and stop/restart without reboot. If one-payload negotiation is rejected by the host, the next design must split frames into explicitly headered UVC payloads. Queue return values, completion status and actual byte lengths still need live evidence. This recipe does not assert successful frame delivery or implement live sensor capture.

The final kernel candidate includes `version=yuy2_640_v23` in optional `.modinfo` storage. This replaces the startup parameter type-description string; actual `__param` registration and parameter behavior remain byte-identical. This enables loaded-module verification through `/sys/module/usbg_video/version` on firmware without readable kernel memory.
