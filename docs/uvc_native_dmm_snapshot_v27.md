# Revision 2.7: native DMM raw snapshot callback

Deployment update: installed 26 October 2026; downloaded readbacks and reboot persistence verified, /usr read-only, patch unloaded before streaming. Rollback to working permanent 2.4p is preserved. No sensor capture yet. See deployment/README.md in the source recipe for the camera-adapted procedure and full /tmp findings.

Built offline on 26 October 2026. Not installed or camera-verified. Permanent 2.4p remains the last hardware-verified webcam transport.

The new default backend is implemented and auto-bound by the streaming worker after USB readiness. It uses the original loaded libBizFw DataflowInfraCh constructor and a private reply queue; four SDK entry points have 16-byte prologue guards. It does not patch Sony global C++ methods, subscribe guessed pins, use diagnostic 0x400 IPC, or replay source addresses.

`native_dmm.c` implements Share (2) → Open (5, mode 0, wait 0) → read-only copy → Close (6) → Free (4, our shared reference only). Exactly one command can be outstanding. Each callback polls once without sleeping and sends at most one request. A timeout never resends a command. Wrong reply IDs, ambiguous sends and failed cleanup retain ownership and fail closed. Initialization and native send/receive wrappers can allocate or lock internally: a hard ten-millisecond worst-case bound is NOT established.

Why Share is required: dmm.ko tracks allocation references at unit+0xb20 separately from opens at +0xb21. Free may destroy the final allocation despite a nonzero open count. A successful native Share is therefore required BEFORE Open. The wrapper owns only that extra reference. Share pins allocation lifetime; it does not freeze producer writes or establish completed-frame delivery.

Selection reads bounded `/proc/udm/dmm_units` and prioritizes active types 0x240b2e, 0x6193f, 0x61940 with allocation/open references and enough capacity. This is a runtime candidate search, not proof those types are active while USB streaming. Physical address/length come only from a successful Open reply. Reject multiple extents, zero/wrapping/non-DRAM spans, short windows and USB-destination overlap. No eligible unit means no frames; no fallback is enabled.

The worker copies exactly 614400 contiguous bytes from source+offset to its owned unit 0x276. It ignores pixel format, stride and geometry and advertises 640x480 YUY2/10fps only as a transport envelope. The source may tear or contain tiled/compressed data. Sequence numbers count software snapshots, not sensor frames. Actual snapshot cadence is lower than the advertised 10fps because acquisition and cleanup advance over worker ticks. No image conversion or counter overlay is applied.

The owned copy survives asynchronous Close/Free replies. Only after cleanup is acknowledged can it be submitted to USB. A pending native reply no longer increments the stock ten-error stop counter. Stop discards any unsent copy, polls cleanup, and retains unresolved native state for later cleanup/restart. There is no background cleanup thread; stopping with delayed replies can leave one shared allocation pinned until a subsequent start/stop progresses the acknowledgements. Do not unload the module or destroy its private queue while anything is pending.

## Build

Use the repo virtualenv Python and ARM GCC at C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe. The streaming baseline must have MD5 19461091c07aa6900829defb0060fcd6. Build into a new output directory:

```
python -B build.py --repo <repo> --output <candidate> --streaming-image <baseline>
python -B persistent_stream.py --input <baseline> --output <candidate>/libInfraStreamingUsb.persistent.so
python -B verify_opaque.py --repo <repo> --output <candidate> --streaming-image <candidate>/libInfraStreamingUsb.persistent.so
python -B verify_persistent.py --stock <baseline> --candidate <candidate>/libInfraStreamingUsb.persistent.so --module <candidate>/yuy2_640_v27snap.so
python -B verify_isa.py --module <candidate>/yuy2_640_v27snap.so
```

Compile/run test_native_dmm.c with native_dmm.c, native_dmm_wire.c, raw_live_source.c and raw_frame_source.c, defining RAW_FRAME_CONVERSION_ONLY; repeat with test_raw_live_source.c and just the latter two sources. These are injectable host tests, not hardware tests.

The inherited builder also emits obsolete fixed-base RAM helper artifacts. Do not deploy or execute those. The persistent candidate uses address-independent lazy activation with no module constructor; SDK/private queue initialization happens only on the worker after USB readiness. A guarded installer and rollback to working 2.4p are now packaged under research/firmware/yuy2_transport_v27_snapshot/deployment/; ten local fixture tests pass. Camera-side preflight and installation remain pending while the user prepares. Retain the proven 2.3 USB kernel and the working 2.4p rollback for any separately authorized hardware trial.

## Offline evidence

- Four request encodings match executions of Sony's original DmmCh allocShare/open/close/free methods, destination queue 0x0061003c. Do not confuse it with VDF queue 0x0059000e.
- Twelve native state/opaque-copy tests pass, including delayed replies, no duplicate sends, failed Share/Open/Close, wrong queue, invalid extents and retaining the copied packet during delayed release.
- Fourteen compiled ARM worker cases pass. The actual compiled native callback is exercised through the USB worker with fixture service replies, byte-identical output, and a second start. Camera services are mocked.
- Thirty-two inherited ownership/conversion cases and eleven PIC/ELF checks pass. ISA audit: 3876 instructions, zero NEON in module text; external libc excluded.

Evidence is in outputs/native-dmm-callback/ in the workspace, and verified_yc/evidence/native-dmm-callback-20261026 in the repository. The source selectors and native hardware services have not yet been exercised on the camera. No real sensor bytes have been captured by this revision.

## First hardware trial

Preserve current hashes/rollback and unknown old RAM-probe state first. Follow the standing stop/archive/hash-verify/clear diagnostic log procedure and use fresh bounded capture; do not delete system-managed logs. Verify available source units and loaded SDK guards. On a separately authorized install, test first capture and restart, recover native state/logs, and restore the verified transport if selection or cleanup fails. Successful host capture is the next evidence required.

Use `capture_opaque.py --output <new directory>` with OBS closed. FFmpeg uses stream-copy to preserve raw packets; save frame-NNNN.bin plus hashes and analyze packing on the PC. Do not interpret a corrupted-looking YUY2 preview as proof the byte tunnel failed. Conversely, zero frames or synthetic bars are not evidence of a sensor snapshot.
