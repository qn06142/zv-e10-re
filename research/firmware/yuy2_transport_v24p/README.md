# Revision 2.4p — persistent, lazy YUY2 transport

Installed and reboot verified on 24 October 2026. First FFmpeg capture, same-session FFmpeg reopen, and subsequent user OBS preview passed without a camera-mode restart between clients. Output remains synthetic 640×480 YUY2 bars/counters, nominal 10 fps. See [deployment report](../../../docs/uvc_yuy2_patch_v24p.md).

`persistent_stream.py` adds a position-independent prepare gate and DT_NEEDED dependency on `yuy2_640_v24p.so` to pre-install streaming image MD5 `19461091c07aa6900829defb0060fcd6`. The producer has no constructor: mapping does not activate it. Video prepare calls `yuy2_activate`, which installs guarded runtime hooks once. Persistence removes manual service RAM bootstrap; the producer still patches process memory during activation. The permanent gate embeds no fixed process/library base.

Build offline with the repo ARM compiler/sysroot and Python dependencies. From this directory, replace placeholders with actual paths:

```powershell
python -B build.py --repo <repo> --output <out> --streaming-image <baseline-image> --stream-base 0x0a61e000
python -B persistent_stream.py --input <baseline-image> --output <out>/libInfraStreamingUsb.persistent.so
python -B kernel_patch.py --input <repo>/dumps/camera_2025/usr/usr/kmod/usbg_video.ko --output <out>/usbg_video.ko
python -B verify.py --repo <repo> --output <out> --streaming-image <out>/libInfraStreamingUsb.persistent.so --stream-base 0x0a61e000
python -B verify_persistent.py --stock <baseline-image> --candidate <out>/libInfraStreamingUsb.persistent.so --module <out>/yuy2_640_v24p.so
python -B verify_kernel.py --stock <repo>/dumps/camera_2025/usr/usr/kmod/usbg_video.ko --candidate <out>/usbg_video.ko
```

Expected: 54 producer/activation ARM cases, 11 ELF/PIC checks, 14 kernel checks (79 total). Hardware services are mocked offline; target loader/reboot/host results are separate. `build.py` also emits legacy RAM bootstrap/helper artifacts; these are unused by the persistent install. Its stream-base supports those artifacts and verification, not permanent relocation.

Final binaries: `libInfraStreamingUsb.persistent.so` MD5 `5fde77e394572ebcf420f8941575f6c4`, producer `9181ef744955190d04728cf4ef7965c5`, kernel `c1cad400372e26eca729e4b9bc47a237` (same revision 2.3 kernel). Generated binaries stay in the session output directory.

Shell scripts are hash-guarded for this camera/baseline and staging folder `/log/yuy2_640_v24p`. They are not automatically executed. Stage all three final binaries and final rollback script with its guarded hash before installation. Cold/unmapped streaming code is required; reboot and verify before future installation. Never replay historical workbench jobs or hot-swap loaded revisions. Recovery `/usr/share/yuy2-recovery-v24p/rollback.sh` restores the pre-install streaming baseline and factory kernel, removes the producer pathname, then requires a genuine reboot. It cannot hot-unload pinned buffers. Streaming baseline is a prior checked-startup/1080 candidate, not factory stock. Retain inode hardlinks until reboot clears mappings.
