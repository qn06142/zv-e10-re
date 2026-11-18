# Offline frame input/output contract — 29 October 2026

Work paused at the user's request for a team handoff. No camera access, live IPC, flash, reboot or new patch occurred. Last known installation remains revision 3.4; its zero-frame capture and reported shutdown crash remain unresolved. The unfinished local 3.5 draft is not a flashing deliverable.

This investigation executes original Sony instructions with controlled external services. It substantially narrows the software contract; it does not establish a working live webcam, physical hardware behavior or a complete safe subscription. Historical claims of a fully solved delivery contract are superseded by this report and the sibling [protocol recheck](../subsystem-recheck-20261029/REPORT.md).

## What is now established

| Boundary | Original-code result | Evidence |
| --- | --- | --- |
| VDF output | Type-0 YC pin; exact producer Share-before-Send and SDS argument placement | `original-pin-initialization.json`, `producer-share-send-original.json` |
| Native consumer | Original encoder opens and parses the retained SSYC; separate pixel/SDS Share, Close and Free helpers | `encoder-original-io.json` |
| Completion | VDF SEND_COMP Execute is a no-op; ReleasePinAndMem selects a different command | `vdf-completion-vs-release.json` |
| SDF request | The 68-byte SDK request is embedded after a 28-byte RTOS envelope | `sdf-forwarding-original.json`, `sdf-short-command-parse.json` |
| SDF parameters | Original builder preserves source compression 1 and destination compression 0; forces transfer 1 and IIB 0 | `sdf-native-parameter-build.json` |
| SDF result | SDK return zero can accompany an ACK rejection or a nonzero CMP payload | `sdf-ack-cmp-control-flow.json` |
| USB | Source-to-staging DMA is separate from staging-to-USB transmission; slot-ready is not DMA completion | `usb-buffer-lifetime.json` |

## Producer and ownership

The original VDF initializer `0x63744f2c` reorders each raw table row `[pin_index,type,direction,queue]` into actual PIN_PROPERTY `[type,direction,pin_index,queue]`. Replaying table rows unchanged is incorrect. VDF pins use queue `0x0059000e`; array index 2 is YC output `[0,2,0,0x0059000e]`. Encoder construction `0x6364e6c8` independently establishes type-0 YC input/output properties. Queue `0x00570050` used in these experiments is a fixture, not a recovered live peer connection.

Original producer block `0x6374c500..0x6374c5e8`, original Share wrapper and actual DataflowInfraPin serialization execute. The controlled connected peer receives a 52-byte `0x1000/0x0102` message:

- source properties at `+8`, destination at `+0x18`;
- SDS type `0x000e0b00` at `+0x28`;
- SDS handle `0x8cc9` at `+0x2c`, offset zero at `+0x30`;
- pixel Share of type `0x295`, handle `0x7f24`, mode 0 precedes Send.

Those historical handle values are fixtures, never addresses or handles to replay on camera. Physical mapping, the ownership-manager factory, Share transport, logs and OSAL delivery are mocked. Producer mode is fixed to 0, bypassing its mode-7 multi-segment branch. Preceding static code opens old SDS, allocates/opens a new SDS, copies it, then closes old/new mappings after send; full allocation/error behavior was not executed by this fixture.

The producer sets the first Category 2 DataTransTiming word to `0xffffffff` before Send. Thus even authentic Category 2 fields are not by themselves a universal completed-pixel lease or timestamp-validity test.

Actual encoder helpers `0x63691dec`, `0x63691ebc`, `0x63691f94`, `0x63692038`, `0x63692218`, `0x63692180`, plus original parser and release wrappers execute against the retained 4096-byte SSYC. They recover pixel type/handle `0x295/0x7f24` through the real category getter. Individually invoked helpers emit DMM Open(5), Share(2), Close(6), Free(4) with independent pixel and metadata references. The harness controls their invocation order; this is not an execution of the entire asynchronous encoder lifecycle. DMM replies and physical mapping are fixtures. Share is not Open; Close is not Free; a reference protects allocation lifetime, not necessarily ISP write completion or CPU coherence.

VDF `SystemCmdPinSendComp` RTTI-linked vtable `0x64585008` selects `0x1000/0x8102`. Activate sets a message flag; Execute `0x63cfaa16` is a two-instruction return-zero leaf. `VdfInputReleasePinAndMem`, vtable `0x645823f8`, selects **`0x2001/0x050a`**, with Execute `0x6372808c`. They are not the same handler. Broader scheduling effects of the activation flag remain open. Do not generalize this no-op to all subsystems or send guessed release commands.

The preceding recheck also proves that Linux `dmpNative::YC1Pin` is type 1 and outgoing; its linked handler aborts on SEND/SEND_COMP. It must not be used as the guessed live YC receiver. A generic pin supports one peer. Reconnecting an occupied YC output risks disrupting the existing encoder; availability of the other VDF outputs is not established.

## SDF processing

Linux `libBizFw.so` SdfCh::resizeRotate builds a 68-byte version-0 request. Original RTOS forwarder `0x636bdf10` places it at `+0x1c` within a 232-byte internal message to `0x00560010`. External requests go to `0x0056000f`. SDK source/destination references at `+0x18/+0x38` consequently appear at internal `+0x34/+0x54`, matching actual ApiResizeRotate parser `0x63cade3a`.

The forwarder copies a fixed larger staging area. To test its tail, the original constructor/parser were run with all trailing bytes zero versus `0xa5`. The entire `0x29c`-byte API object was identical. This resolves default version-0 tail handling for the tested path; versions 1/2 have extended fields and were not tested. Metadata, capacity, mapping and auxiliary reads were mocked.

Original normal builder `0x636c5e44` was executed up to `0x636c6254`, before resource exclusion/module processing. It builds source compression 1 / destination compression 0 and forcibly normalizes both `data_transfer=1`, `iib_number=0`. Transfer 1 therefore cannot be treated as evidence that ISP DMA has completed. Heap/pool allocations and DMM span records are fixtures; no scaler hardware runs.

Do not inherit the team's claims that this proves one-pass decompression to YUY2. `WrapSrotateStart` actual wrapper `0x636ef2d4` calls driver `0x638e1bd0`; nearby enum conversion alone does not establish driver acceptance. Normal processing can allocate work resources. `ModuleResizeRotateNoMem` `0x636e5b20/0x636e5b40` checks capacity against intermediate geometry times two and has several processing branches. One pass, no intermediate memory and final YUY2 byte order remain unproved. Prefer the native full SDF API over a guessed hardware record.

Original SDK `sendAndRcvAckCmp` `libBizFw.so+0x366f0` sends, receives 16-byte ACK, then 24-byte CMP using timeout `0xffffffff` for both. Fixture ACK status 5 causes it to skip CMP yet return zero; fixture CMP payload status 7 also returns zero. The caller must inspect both response payloads and validate correlation. A private queue and one outstanding operation are necessary design constraints, not proof of cancellation. Merely moving an indefinite wait onto a thread does not make teardown safe. RTOS CMP builder `0x63cadbe4` writes its result at payload `+8`.

## USB output and lifetime

Original `libInfraUsbCmn.so` WaitVideoReadCmp uses ioctl `0xf002`; UpdateVideoBufEvt uses **`0x4008f003`**, passing the two-word `[bytes,physical]` record. The Thumb PLT veneer at `0x8bac` enters the ARM ioctl stub at `0x8bb0`; mixed veneers must not be resolved by fixed PLT index stride.

Kernel `usbg_video_core_ioctl` `.text+0x1e10` routes those commands. Four original-code fixtures establish `0xf002` returns `-16` only when both staging flags are set, otherwise zero. It is a slot-availability check, not a direct source-DMA wait.

Update calls `.text+0xd00`. Original prefix `.text+0xe68..0xf70` builds the DMA record `[614400,source_physical,staging_physical+12]`, creates a 12-byte UVC header and invokes `dma330_mem_transfer_async`. This is a real source-to-internal-staging copy. On the ordinary successful path, source reuse depends on that copy finishing; it need not wait until the host consumes USB staging. That distinction permits decoupled buffers, once completion is reliable.

However, original `.text+0xf88..0x10d0` logs a missing-completion timeout after a `schedule_timeout(1000)` expiration, then still marks a slot ready with `bytes+12` and returns zero. A fixture with DMA-done false reproduces this. DMA-start failure has another path which can also reach a zero return with a header-only slot. Do not treat Update success plus F002 success as proof DMA stopped or copied all pixels. The timeout duration is 1000 scheduler ticks, not a measured millisecond duration. Actual DMA cancellation/late callback behavior is unresolved.

`uvc_transfer_dmac_cb` sets a completion flag and wakes the waiting task. USB request completion `usbg_video_st_write_comp` frees endpoint requests and updates staging availability separately. `core_cb_stop` drains endpoint request lists, sets stop/wakeup state and clears staging flags. Static tracing of those paths does not prove the source DMA is synchronously cancelled on every disconnect/stop race.

## Applicability and remaining work

All 16 recorded RTOS ranges are byte-identical between original firmware MD5 `cdcae9d4fdbf66a33704a4c7564e346d` and the historical deployed candidate MD5 `90096db2c76148f4f9db5d104e5c608c`. Relevant USB callback, stop and ioctl ranges are identical between original kernel MD5 `5b59c2e62c80683d754955ab5de0467d` and candidate MD5 `c1cad400372e26eca729e4b9bc47a237`; submit differs only at `.text+0xf44` for the known UVC EOF header change. This is comparison to saved artifacts, not a fresh camera readback. See `input-hashes-and-applicability.json`.

Before a new live-frame patch, close these specific gaps:

1. Recover a genuine type-0 producer/consumer event route or a narrowly justified tee; prove when source references are acquired and released, including errors and stop. No arbitrary pool scanning or occupied-pin reconnection.
2. Trace the native SDF hardware completion/error/cancellation boundary and exact output packing. Compression 0 is not enough to call the result YUY2.
3. Establish USB DMA timeout/cancel/late-callback ownership. A reported zero return is insufficient for freeing or overwriting a source buffer on exceptional paths.
4. Design stop order around outstanding SDF and USB DMA, with resources retained until actual completion/cancel acknowledgement. Trace the 3.4 crash independently; the saved run never reached SDF, so these SDF findings do not establish that crash's cause.

## Reproduction

Recipes are in `recipes/`. From local workspace `C:/Users/qn061/Documents/Codex/2026-10-22/chec`, run:

```powershell
& 'D:/02_Development_And_Projects/pmca-re/.venv/Scripts/python.exe' -B 'D:/02_Development_And_Projects/pmca-re/research/firmware/raw_frame_source/verified_yc/evidence/frame-contract-20261029/recipes/run_all.py'
```

Nine original-code verification scripts, applicability collection and USB disassembly collection passed (11 recipe entries in `verification-summary.json`). Native test inputs require local firmware and the retained capture at `.local/outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin`, SHA256 `9c60c7088da03631af4cd06fbd8f9d444d084e9104ead87cb0147ef76ac45f9c`. No firmware binaries or raw captures are included here. Original-code execution with mocked services verifies selected software paths only.
