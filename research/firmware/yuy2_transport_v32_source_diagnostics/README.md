## Deployment update — 28 October 2026

INSTALLED AND REBOOT-VERIFIED by user request. Matched file readbacks and postboot hashes passed; /usr read-only, new code absent from cold maps, service closed. Guarded installer and recovery scripts now in deployment/;10 local installer fixtures passed. Exact3.1 and2.4p recovery preserved. No3.2 streaming test yet. See evidence/install-20261028/deployment-summary.json. Build-time NOT_INSTALLED/no-installer statements below are historical.

# Revision 3.2: native source-acquisition diagnostics

Built offline 28 October 2026. NOT INSTALLED. Camera remains3.1 after its zero-frame test; service session is closed. This revision adds evidence to identify the source-acquisition failure, not an established fix or a working webcam claim.

## Why this patch

3.1 passed complete maps read, queue initialization and destination allocation/validation on camera. It then quarantined after SHARE of candidate SSYC type0xe0b00, with no pixel reference, resize request or frame. Its take() did not distinguish failed Share, Open, address-site or mapping. A signature peek is only a hint; this is not yet verified video metadata.3.1 replies were not retained, so retry/release semantics must not be guessed.

## Changed behavior

3.2 emits SHARE_OK, OPEN, OPEN_OK and LEASE_READY at acquisition stages. SHARE_FAILED and OPEN_FAILED record the candidate handle, SDK return value, reply word0 and all remaining five32-bit reply words through DMM_REPLY_04 and DMM_REPLY_10. OPEN_SITE_REJECTED records the same24-byte reply when the address-site field is unsupported. Values are logged in hexadecimal; negative rc/status values use two's complement. Reconstruct word0 followed by words04,08,0c,10,14 as little-endian for the original reply bytes. The final zero printed by DMM_REPLY_10 is padding, not a seventh reply word.

LEASE_MAP_FAILED includes handle, reason and physical address; LEASE_MAP_BYTES includes span and USB/staging start addresses. Reasons: -1 invalid DRAM/span; -2 USB overlap; -3 staging overlap; -4 mapping-size overflow; -5 failed open(/dev/stream); -6 failed mmap. No errno is recorded. SSYC_HINT and SSYC_HINT_BYTES record listing/signature candidates before ownership, not proof of a camera image.

Existing64KiB-per-boot VGA log cap remains. New destination /log/yuy2_640_v32vga/ must exist before activation. Instrumentation adds synchronous file writes on the private worker and may change timing; this is a diagnostic build, not a performance measurement. Ambiguous errors still quarantine. No retry, guessed subscription, new release or ownership change.3.1 procfs EOF fix, firmware guards, owned input metadata and one streaming session per cold boot remain.

## Matched files

- yuy2_640_v32vga.so:32632bytes; MD5 de59485d1ad155711d81cd592ed5b821.
- libInfraStreamingUsb.so:72796bytes; MD5 cc3de8f0f0b710e6e2027ac78ea94c50. Dependency is yuy2_640_v32vga.so.

Manifest records SHA256s. Local ZIP contains patched proprietary wrapper for authorized local deployment; do not publish binaries in Git. Source/recipes/textual evidence may be tracked. No installer supplied yet. Do not run3.1 installer unchanged. Later installation must verify current3.1 hashes, clear/quarantine via fresh boot, preserve recovery, install dependency first, verify readback/read-only mount and reboot. No camera access or file changes on camera occurred in this build.

## Verification

17 host worker scenarios pass: prior9 behaviors plus Share transport failure, Share negative reply with exact reply-word preservation, Open negative reply, unsupported address site, invalid span, mmap failure, stream-device open failure and USB overlap. Fault tests verify no pixel acquisition or resize, and existing conservative metadata ownership retention. Actual SDK/DMM responses are mocked.17 compiled ARM initialization regressions pass against real Sony prologues and captured maps;11 PIC/dynamic-table/startup checks and3 compiled ARM session restrictions pass. ARM text audit4775 instructions/no NEON. These checks do not prove a live frame or actual negative-reply semantics.

Build: source/recipe/build.py --repo REPO --output outputs/vga-v32/build --streaming-image WORKSPACE/outputs/uvc-startup-fix/candidate-1080p/libInfraStreamingUsb.so. Matching locally held Sony dumps and existing compiler/sysroot required. verify_worker.py runs host assertions; verify_loader.py --repo REPO --workspace WORKSPACE uses captured maps and prior3.0 build; verify_session.py checks stop/rebind restrictions. No Sony dumps distributed.

Next hardware step: guarded installation after fresh boot, one bounded5-frame/25s host capture, then service return without reboot to preserve runtime/vga logs and possible SSYC dumps. Archive/hash-verify/recheck/individually clear known test logs; preserve system/tmp/fonts/tools. No2.9 packet reassembler; payload remains614400 unframed native bytes, advertised YUY2 packing unverified. Do not replay transient handles or relax quarantine until failure replies are understood.
