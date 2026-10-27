Installed and reboot-verified on27October2026. First stream/frame test pending. Current deployment evidence is evidence/install-20261027/deployment-summary.json. Original offline build documents and ZIP retain their historical NOT_INSTALLED status.

# Revision 3.0: experimental Sony SDF 640x480 capture

Built offline on 27 October 2026. NOT INSTALLED; NOT CAMERA VERIFIED. Camera remains on revision 2.9. This is a VGA resize test candidate, not a claim of a working decoded webcam. Binary hashes are in manifest.json.

## Changes

The existing USB transport is retained. Its new source is Sony SDF resizeRotate, following the actual libObj resize2VGA allocation/metadata recipe. It requests a separate 640x480, yc_compress=0 image of type 0x220. It does not select VEF table record 5, flip the global HD compression flag, or use the JPEG encoder; VEF type0x295 remains upstream.

A private worker finds SSYC metadata using bounded DMM listings. A read-only physical signature peek is only a hint. It then Share/Opens the metadata and referenced image, copies/revalidates metadata and checks geometry/capacity. YcStateInfo is required; multiple-segment sources and unsupported placement/content/scan flags are rejected. Source allocation lifetime is pinned, but a coherent completed producer frame is NOT established: tearing remains possible.

SDF receives an OWNED SSYC copy pointing to the pinned source image. Producer changes to the original descriptor cannot redirect SDF to another unpinned image. The owned metadata is rewritten only after the prior ACK/CMP. Destination geometry/compression/handle/capacity are checked before submission and after completion. Maps reject MMIO, overflow, excessive spans and USB overlap; SDF source/destination/input-metadata ranges are checked for collisions.

Only successful ACK/CMP plus valid destination metadata permits publication of a complete 614400-byte copy. No bars or synthetic fallback. One pending frame provides backpressure so SDF stops extra work while the host is not consuming output. Pixel packing remains UNVERIFIED: YUY2 is the advertised USB envelope, not proof of packed YUYV pixels. No CPU format conversion is implemented. Descriptor rate is 10 fps; there is no measured camera frame rate or 24 fps claim.

## Lifetime and test limits

Sony calls run on a lazy private pthread after host capture begins. No new load-time constructor or menu hook launches this worker. SDK synchronous receives can wait indefinitely; the USB/UI caller never joins the worker. Ambiguous outcomes retain resources and quarantine it until reboot. A stalled request may still affect shared hardware; a separate thread does not prove that the camera cannot freeze.

ONE STREAMING SESSION PER COLD BOOT. Stop is asynchronous. Known-completed per-frame Share/Open references are released. Owned destination buffers and owned input metadata remain reserved until reboot; uncertain references stay pinned. Re-entry after output detach is explicitly rejected even if no host capture occurred. This avoids 2.9's unresolved retained USB mapping whose DMM allocation disappeared. Reusable mode cycling and earlier MENU restarts are not fixed.

## Package and deployment prerequisites

The two candidate files are a matching pair:
- yuy2_640_v30vga.so -> /usr/lib/yuy2_640_v30vga.so
- libInfraStreamingUsb.so -> /usr/lib/libInfraStreamingUsb.so

NO AUTOMATIC INSTALLER is included. Before deployment, do a fresh service preflight after cold boot with streaming unopened. Verify current 2.9 files and retain verified 2.9/2.4p recovery copies. Install the module and gate together. Create /log/yuy2_640_v30vga, verify free storage/memory, and restore /usr read-only. No kernel, RTOS, DmmConfig or common-library write is part of this candidate. Do not deploy old RAM bootstrap artifacts.

Required inspected files (MD5):
- libObj.so: 0b4be3fb599b539c69c782bd400dd8e9
- libBizFw.so: 6416a5a6780bbe829eb30d85fc8e8dad
- libInfraUsbCmn.so: 31308976206a837f6f5c571992d2b499

The module links existing libpthread.so.0. Runtime SDK exports and six private libObj helpers require matching prologues. Private-entry reads must lie in readable libObj mappings. Guard failure submits no resize. Target loader/thread initialization, SDK queues, live SSYC availability, pools, compressed-input/uncompressed-output acceptance, cache behavior and pixel layout all remain hardware-test requirements.

## First hardware test

Archive, download, hash-verify, recheck and clear known previous research captures/logs first. Preserve system /tmp files and use normal error filters; do not enable unbounded application logging.

After guarded deployment and cold reboot, activate USB Streaming with OBS closed. Run capture_vga.py --output first-vga.bin. It requests five frames by FFmpeg stream-copy with a 25-second host timeout. Each payload is 614400 native bytes, with NO ZVYC0029 header. Do not use the 2.9 reassembler. Complete payloads alone do not prove a decoded image.

Exit to service promptly without restarting. Retrieve /log/yuy2_640_v30vga/runtime.log, vga.log, input-ssyc.bin and destination-ssyc.bin plus fresh DMM/maps/storage/memory state. vga.log is capped near 64 KiB per boot; each first-frame metadata file is <=64 KiB. Inspect SOURCE/DEST_FLAGS, RESIZE, COMPLETE, NO_SOURCE_SSYC, REJECTED and QUARANTINED. Preserve partial results. Archive/hash-verify/recheck/remove these exact research files afterward. Any new attempt needs a cold reboot, including recovery from a stalled SDK call.

## Offline checks and rebuild

Host fixtures mock hardware. They cover publication, producer metadata isolation, missing/malformed metadata, descriptor changes during acquisition, rejected resize, unexpected output compression, insufficient capacity, ambiguous Open failure, MMIO and USB overlap. Metadata contracts cover handles, geometry, ranges and compression. Original Sony ARM request, capacity and geometry methods were separately executed with hardware boundaries mocked. PIC activation, no constructor, no NEON and compiled ARM post-stop rebind rejection are checked. None replaces target validation.

Use repository .venv Python and ARM compiler:
python build.py --repo D:/02_Development_And_Projects/pmca-re --output candidate --streaming-image BASELINE.so

BASELINE.so must hash to 19461091c07aa6900829defb0060fcd6 (the inspected pre-permanent-patch baseline), not the installed 2.9 wrapper. SDK guard generation enforces the SDK hashes above. Build produces both candidate files and manifest with an address-independent streaming gate and performs no camera operations.
