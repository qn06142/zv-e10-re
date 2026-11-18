# Revision 3.8: rejected-descriptor capture

29 October 2026. **Built offline; NOT INSTALLED or camera-tested.** The camera remains on revision3.7. This is a diagnostic revision needed to identify the actual failing metadata contract. It does not claim working frames, a parser fix, corrected colors or safe recovery from the existing quarantine. No camera operations were performed while building3.8.

Revision3.7 established a real YC connection and received a native SEND, then rejected the SDS before opening pixels or submitting SDF. Its one combined error omitted which predicate failed and it did not preserve the raw SDS. Source references remained quarantined; returning to Mass Storage lost USB access, and manual restart was needed to retrieve logs. There is no proved causal link from quarantine to that USB failure.

## Changes

The same acceptance policy now reports a bitmask and independent image/state/multi-segment decoder results. Two bounded metadata reads are retained so instability can be distinguished from an unsupported layout. The error path exclusively creates /log/yuy2_640_v38vga/rejected-source.yc38, writes an80-byte header and both snapshots, fsyncs, closes and records success/failure. It attempts this once per module lifetime; it never overwrites an existing record. Writes handle short progress and stop on errors. Maximum payload is131152bytes (80+2*65536). This bounds byte volume and attempts, not filesystem syscall latency.

Normal accepted-frame processing has no added flash I/O while holding a frame. The existing successful-run dumps still occur only after clean teardown. The record is saved only after fault/stopping have prevented another source worker or publication. It contains metadata, **not camera pixels**.

The parser checks, source ownership policy, SDK operations, single-session restriction and quarantine remain. This deliberately does not relax a failed guard or guess how to release an unidentified pixel credit. If the rejection recurs, the camera may again need a restart to regain USB; the fsynced descriptor is intended to survive it. A complete record plus EVENT_REJECTION_SAVED is required to claim durable capture. Partial/write/fsync/close failures are explicitly logged. Do not call this a teardown fix.

## Rejection bits

| Bit | Meaning |
|---|---|
|0x01|Declared SDS size outside32..65536|
|0x02|Two metadata reads differ|
|0x04|Image category decoding failed|
|0x08|State category decoding failed|
|0x10|Multi-segment category present or malformed; only absent is currently accepted|
|0x20|Decoded pixel type differs from0x295|
|0x40|Decoded pixel handle is zero|
|0x80|Decoded pixel handle aliases SDS handle|

Image-dependent bits are evaluated only if image decoding succeeded. Parser result-1 is logged asffffffff; -2 asfffffffe. Geometry, format, raw header fields, declared/captured lengths and parsed attachment identity are logged separately. Oversized input is always rejected, with only its first64KiB copied. Unknown enum values are reported without being accepted.

## Binary record

Magic is ASCII YC38RJ01, then18little-endian u32 fields: version(1), header_bytes(80), copied_bytes, declared_SDS_bytes, rejection_mask, SDS_handle, SDS_type, SDS_physical, image_rc, state_rc, multi_rc, decoded_pixel_type, decoded_pixel_handle, decoded_pixel_offset, image_attach, yc_compress, reads_differ, total_bytes. First SDS snapshot and second SDS snapshot follow. Exact file length must be80+2*copied_bytes; copied_bytes must equal min(declared_bytes,65536).

recipe/decode_rejection.py validates the envelope and produces JSON with reasons, signed return codes, changed-byte offsets, SHA256s and bounds-checked category summaries. Example: python decode_rejection.py rejected-source.yc38 --output rejected-source.json. Output creation refuses to overwrite an existing report. Do not replay historical handles/physical addresses. A parseable record alone does not establish fsync success or valid pixel ownership.

## Artifacts and deployment

Matched module yuy2_640_v38vga.so MD5d577730ce4eeec70904cd4fb164580f5 (42648B); wrapper MD5f5d42a08e186b0cf2f519bd105457e08 (72796B). USB kernel is **unchanged from3.7**: MD5388799d95bbb524ca581c66b077b6dc2, versionyc37_fence. Install all matched files through guarded scripts only. The current3.7 module7c339b924987e6baa8e7046e041798c5 and wrapper277c023942dd4d3d347d9829eaf8be85 are the exact baseline. Stock common library31308976206a837f6f5c571992d2b499 and original kikilog51337167a2ab42d53557c2cce210c987 are guarded. Do not alter those mapped/boot-loaded dependencies.

Installer backs up the3.7 wrapper/kernel and retains a separate exact2.4p bars kernel from3.7's recovery directory. Default rollback restores failing3.7, not a working live webcam. --bars restores stable2.4p wrapper5fde77e394572ebcf420f8941575f6c4 and original bars kernelc1cad400372e26eca729e4b9bc47a237; producer9181ef744955190d04728cf4ef7965c5 must be intact. Both wrapper and kernel are verified before/after restoration.

Archive and camera-hash-verify only owned capture files before removing them. **Preserve system-managed /tmp/kikilog.dat, fonts, helpers, AccessLog and ThreadMonitor.** Require free-space plus an actual/tmp write/readback check. The rejection file must not already exist. Actual3.7 recovery showed reboot-f can resume cached kernel/VFS state. Fresh initialization must be established from native WBI controls and ssboot/loaded versions with target-specific guards and backups; see the3.7 recovery report. Installer does not automatically change the boot cache or reboot. Do not format or manually write FAT. After an authorized installation, byte-verify readbacks and fresh-boot state before one controlled metadata trial.

## Validation and limits

28 actual worker-C host fixtures cover continuous100-frame publication, backpressure, stop, SDK failures, each rejection family, snapshots up to the64KiB cap, exclusive file creation, partial writes and write/fsync/close failure. Seventeen binary records emitted by that C code were independently decoded;51malformed lengths were rejected. The worker fixtures mock native services and do not prove camera behavior. Nine compiled ARM frontend and11persistent/PIC checks passed; ISA audit decoded6163instructions/no NEON. Seventeen SDK-loader and fourteen installer/rollback fixtures passed. Sony producer/handshake protocol evidence is inherited from3.7; it has not been extended to prove rejected-transfer cleanup.

Local build: outputs/vga-v38/build/. Package: outputs/vga-v38/flash-package/. Source and small verification outputs can be retained in the project; Sony binaries, raw camera logs and future descriptor captures remain local. The next actual descriptor must be examined before changing acceptance rules or ownership cleanup.
