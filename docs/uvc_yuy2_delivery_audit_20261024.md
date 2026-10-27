# Offline audit of YUY2 zero-frame delivery — 24 October 2026

## Finding

The 640×480 prototype changes the userspace descriptors and frame producer, but leaves the kernel UVC negotiation and packetization contract at stock MJPEG values. This is a concrete implementation gap and the strongest offline explanation for zero host frames. The exact Windows failure path is not established without a USB trace or host-driver diagnostics. No camera access or deployment was performed in this audit.

The supplied team's report contains useful binary findings, but its claims of proven physical delivery and a proven Windows EOF discard loop are retracted by this audit. Revision 2.2 remains unverified for delivery and repeat activation.

## Reproducible binary facts

Original `usbg_video.ko` MD5: `5b59c2e62c80683d754955ab5de0467d`.
`work/audit_uvc_delivery.py` records SHA-256, constants and bounded execution results in `binary-audit.json`. Tests execute original ARM instruction fragments with simulated state; they do not emulate USB hardware.

| Contract | Kernel behavior | Prototype requirement |
|---|---|---|
| Frame interval | Default 333,333 in 100 ns units; paths `0x1204`/`0x121c` select NTSC 333,333 or PAL 400,000 | 1,000,000 (10 fps) |
| Maximum video frame | 14,745,600 bytes (`0x00e10000`) | 614,400 pixel bytes (`0x00096000`) |
| Maximum payload transfer | 300,000 bytes (`0x493e0`) | Current one-header request is 614,412 bytes |

Probe record: `.rodata + 0x7a`, actual file offset **0x2e66** in this binary. Frame-size field: file `0x2e78`; payload-size field: file `0x2e7c`. The pasted report's sample command using `0x1f74 + 18` is not the record location in this ELF. Use ELF section offsets and binary hash guards, never copied bare offsets.

The responder at `.text + 0x11bc` copies the 26-byte constant into its reply, overrides the interval according to camera mode, then copies it to EP0. `0x1390` routes streaming-interface probe/commit GET requests to that responder via `0x16a4`. Changing `libInfraUsbCmn.so` descriptor arrays does not change this kernel response.

The submission path copies a frame into staging after a 12-byte header (`0xf24–0xf70`), stores request length `size + 12` (`0x104c`), and queues a USB request (`0xad8–0xcdc`). There is no UVC payload-header insertion every 300,000 bytes in this path. USB packet subdivision by the controller does not create UVC headers. A 614,412-byte single payload therefore exceeds the advertised 300,000-byte limit. A host consuming that limit can lose framing within the pixel data; this is a mechanism, not an observation of Windows internals.

## Why the userspace negotiation hooks did nothing

The revision 2.2 constructor patches free wrappers at common-library offsets `0x12064` and `0x12098`. The stock kernel rejects the corresponding `0x4008f004` and `0x4008f005` ioctls through `0x2350`, returning -25 at `0x23b0`. These hooks do not intercept EP0 negotiation.

Probe/commit responses are generated in the kernel. Some class requests also dispatch event 7 to userspace (`0x199c–0x19e8`); saying negotiation events never reach userspace is too broad. The absence of our wrapper log markers is not proof that the host skipped negotiation.

## Corrections to the supplied report

1. **No proof that 180 frames or 110 MB crossed USB.** `SUBMITTED` counts zero API returns in the producer. The kernel can branch from `0xf10` to `0x10cc`, returning zero when both buffers are full without staging this frame. The preceding queue-helper return at `0xe34` is ignored. These paths weaken API counters as delivery evidence; they do not prove those paths occurred during the saved run.
2. **Completion does not establish successful delivery.** At `0x2508` the callback examines request status. Status 0, -5 (-EIO), and -84 (-EILSEQ) all reach common cleanup at `0x2530`, which can clear readiness via `disable_flag` at `0x2540`. It does not check `actual == length` before clearing readiness. -104 follows a different exit. Original ARM fragment execution confirms these status branches. Thus buffer recycling can occur following errors.
3. **Missing EOF is not a proven root cause.** Header arithmetic at `0xf44` does produce `0x8c/0x8d`, with EOF clear. However, the official UVC 1.1 class specification, Table 2-5, PDF printed page 31, describes EOF as optional for all payload formats. Its section 2.4.3.7 also describes FID with optional EOF for frame-based formats. The uncompressed supplement section 2.4 describes EOF semantics but does not contain the report's quoted MUST sentence. There is no saved evidence establishing the asserted Windows discard loop. Setting EOF on the final payload is reasonable interoperability work, but cannot be called a demonstrated fix.
4. **Maximum frame size is not an exact-length completion requirement.** A stale maximum is a negotiation mismatch, but the assertion that DirectShow must wait for 14.75 MB does not follow from its meaning as a maximum. `dwMaxVideoFrameSize` must describe pixel bytes, **614,400**, excluding UVC headers; `614,412` is not an interchangeable alternative.
5. **Evidence revisions were conflated.** The recovered 180-submission runtime log is revision 2.1. Revision 2.2 has verified RAM bootstrap readback and a zero-byte host capture, but its runtime/application logs have not been retrieved. Do not attribute revision 2.1 counters to revision 2.2.
6. **Exit 124 is the harness timeout.** `work/capture_yuy2_v22.py` kills the stalled process after 25 seconds and records 124; this is not a demonstrated internal FFmpeg or DirectShow timeout/error diagnosis.

## Implication for the next patch

Correct the kernel-visible probe contract alongside the userspace descriptor: 640×480 YUY2, frame size 614,400, interval 1,000,000. Align packetization with the chosen negotiated payload maximum. Two possible designs need evaluation:

- Keep a 300,000-byte maximum and split each frame into multiple UVC payloads, each with a header and the same FID; set EOF only on the final payload. With 12-byte headers and packed YUY2 alignment, pixel portions of 299,988 + 299,988 + 14,424 bytes fit. This requires explicit payload construction/queueing, not just USB packet splitting.
- Negotiate one payload of 614,412 bytes if the host accepts that maximum, retaining the existing one-header-per-frame transport. Do not assume host acceptance from descriptor enumeration.

Instrument kernel queue results, DMA result, completion status and actual/expected lengths. These distinguish transport failure from host parsing and avoid treating dropped/failed submissions as delivery. Keep the manager-lifetime restart correction separate; it addresses the known second-start rejection, not this protocol gap. No new patch has been built or flashed by this audit.

## Sources and verification

- Sony kernel and library disassemblies under local `outputs/offline-uvc-re/` and `outputs/raw-usb-investigation/`.
- Original ARM fragment checks: `python -B work/audit_uvc_delivery.py`; all assertions pass. Mock literals resolve only bounded state accesses, as marked in source.
- [Official USB-IF UVC 1.1 document set](https://www.usb.org/sites/default/files/USB_Video_Class_1_1_090711.zip), downloaded locally as `outputs/USB_Video_Class_1_1_090711.zip`. Extracted reference text is in this audit directory. Class spec Table 2-5, sections 2.4.3.7 and 4.3.1.1; Uncompressed Payload sections 2.4 and 3.2.
- Preserved revision 2.1 runtime: `outputs/yuy2-640-v21/deployment/camera-first-attempt/runtime.log`; revision 2.2 evidence state: `outputs/yuy2-640-v22/deployment/deployment-state.json`.
