## Camera testing paused by user; next major push is 4K/12-bit — 27 October 2026

USER REQUESTED PAUSE AFTER FLASH. No3.0 FFmpeg/OBS capture was performed. All camera service workbench sessions are closed (job015 confirmed WORKBENCH_CLOSED/Done); no live test or new deployment should resume automatically. Leave installed3.0 in place; this pause did not request rollback. Flash/readback/postboot/inactive-map/RO checks passed as recorded below, but live VGA resize/output acceptance remains untested.

Next major offline direction: docs/90-session/4K_12BIT_NEXT_PUSH.md, also linked at the top of OPENGATE_FINDINGS.md. Use the actual hardware-proven2.4p VGA colour-bars binaries as the control, and the new3.0 Sony VGA allocator/SSYC/SDF findings as a route to trace genuine high-bit-depth4K buffers. Do not call3.0 colour-bars-tested or regard synthetic8-bit bars as evidence of12-bit acquisition. Verified reference bundle: research/firmware/4k12bit_baseline_20261027/ (five binaries with MD5/SHA256; separate matched2.4p/3.0 pairs and provenv23 kernel; offline reference only).

The next step is a verified producer/metadata/allocation/precision/sink map, followed by a guarded prototype with explicit remaining hardware requirements. Source precision,4K geometry, encoded bit depth and sustained delivery are separate proofs. Corrected packed UHD12-bit YUV420 size is18662400B/frame (not~11.87MiB); Bayer12-bit is12441600B/frame.24fps packed payloads are298598400B/s Bayer,447897600B/s YUV420,597196800B/s YUV422, excluding overhead/padding. Current USB2 VGA transport is diagnostic/control infrastructure, not a proven continuous4K/12-bit path. No new camera actions or patches during this documentation update.

## Revision 3.0 installed and reboot-verified — 27 October 2026

USER REQUESTED FLASH COMPLETED. Current camera revision is3.0 experimental VGA, not2.9. Module MD5 98acd3ba3d6628e006fe51d88dda25dc (30996B); persistent streaming library MD5 2a4c08511526f2b525c57a1d9bac9bad (72796B). Both were downloaded/readback verified and matched again after activation reboot. /usr is read-only; streaming library, producer and old observer/probe modules are absent from cold process maps, so no new streaming code active before setup. NO STREAM/FRAME TEST YET: live SDF acceptance, output pixels/packing, frame rate and coherent source frames remain unverified. User must now activate USB Streaming with OBS closed and report streaming for the bounded FFmpeg test. Do NOT reflash or load a RAM bootstrap merely because the offline package manifest says NOT_INSTALLED; that is its historical build-time status.

Deployment/evidence: research/firmware/yuy2_transport_v30_vga/deployment/ and evidence/install-20261027/; workspace outputs/vga-v30/deployment/. Installer passed10 simulated failure/rollback cases. Exact previous2.9 wrapper, stable2.4p wrapper and hardlinked old inode preserved under /usr/share/yuy2-recovery-v30vga/. rollback.sh there restores2.9, with cold-mapping guards; then existing /usr/share/yuy2-recovery-v29full/rollback.sh can restore2.4p if needed. Old2.9/2.4p producer files, kernel, RTOS, DmmConfig, SDK and common library unchanged. Required pthread is /lib/libpthread.so.0 (MD5 09cb541e6e785dd6bfeb76d74f29f5d2), not /usr/lib/.

Before installation6old capture/status logs7642B were archived/downloaded/hash-verified, rechecked and individually cleared; system/tmp/fonts/tools preserved. Storage and4096B/tmp write/readback passed. Normal error filters restored; no unbounded debug capture. A preflash reboot cleared loaded2.9 code; fresh preflight passed before installing dependencies first. Activation reboot observed, then a fresh service session verified hashes/recovery/RO/inactive maps/storage. Reboot workbench jobs report missing completion marker because terminal stopped during Restarting system; this is expected, not an install failure. Final postboot job014 passed. Service close job015 queued/completing.

ONE STREAMING SESSION PER COLD BOOT remains enforced. Next: use work/vga-v30/recipe/capture_vga.py for5unframed614400B payloads with25s timeout, then user returns to service without reboot for bounded vga.log/runtime.log and input-ssyc.bin/destination-ssyc.bin collection. Do not use2.9 reassembler. No bars/fallback or confirmed YUY2 conversion. Preserve failures/metadata and verify source ref release; owned input/destination allocations stay reserved until reboot and uncertain SDK results quarantine. Archive/hash-verify/recheck/clear known research captures as regular procedure. Do not assume2.9 stale USB-output reuse has been fixed beyond the new one-session guard.

## Revision 3.0 experimental VGA resize candidate built — 27 October 2026

OFFLINE ONLY; NOT INSTALLED or camera verified. Installed remains 2.9. Candidate/package: research/firmware/yuy2_transport_v30_vga/; workspace ZIP outputs/vga-v30/zve10-v30-vga-experimental.zip. Guide: docs/uvc_vga_v30_candidate_20261027.md. Module yuy2_640_v30vga.so MD5 98acd3ba3d6628e006fe51d88dda25dc (30996B); matching persistent libInfraStreamingUsb.so MD5 2a4c08511526f2b525c57a1d9bac9bad (72796B). Package has no automatic installer; preserve verified2.9/2.4p recovery and do fresh cold-boot service/hash/maps/storage preflight before any installation.

Uses Sony SDF resizeRotate and actual libObj resize2VGA paired allocation/metadata path to request owned640x480, yc_compress0, type0x220 output from native VEF0x295. Does NOT select global VEF record5 or flip HD compression. A private lazy pthread discovers SSYC via bounded DMM/read-only signature hints, then pins/revalidates metadata and pixel references. Requires YcStateInfo, rejects multi-segment/unsupported flags and checks spans/overlap. SDF receives an OWNED SSYC COPY pointing to the pinned pixel allocation: producer descriptor mutation cannot redirect it. ACK/CMP and destination metadata/capacity must pass before publishing a complete614400B copy. No bars/fallback or CPU YUY2 conversion. Actual packing/bit depth/coherent source completion and camera frame rate remain unproved. Advertised10fps only. Successful target capture is not yet established.

ONE STREAMING SESSION PER COLD BOOT. Stop does not join a potentially blocked SDK thread. Ambiguous outcomes quarantine resources; owned destination/input allocations stay reserved until reboot. Output detach permanently blocks rebind until boot, including stop before any host frames, preventing inherited2.9 stale USB-mapping reuse. No reusable mode-cycle fix or MENU restart diagnosis claimed. A separate thread does not rule out shared-hardware freezes. Live SSYC availability, SDK/thread init, compressed-to-uncompressed acceptance, cache behavior and target loader need validation.

Offline checks passed:9 mocked hardware-boundary worker scenarios (including immutable owned metadata, descriptor races, failures, size/MMIO/USB overlap), metadata contract fixture,6 original Sony caller+SDK request fixtures,4 original RTOS size fixtures, original Sony geometry method,11 PIC/no-constructor cases,3 compiled ARM post-stop/session checks and4523 module instructions/no NEON. Hardware boundaries mocked; see evidence/ JSON. Capture tool now saves UNFRAMED614400-byte VGA payloads; DO NOT use2.9 reassemble.py or assume YUY2 packing. First bounded FFmpeg run only, then service logs/SSYC extraction without restart. Archive/hash-verify/recheck/clear known logs first and after; preserve system/tmp files. New bounded logs: /log/yuy2_640_v30vga/{runtime.log,vga.log,input-ssyc.bin,destination-ssyc.bin}. No camera access or writes occurred while building this candidate.

## Native VGA and resize2VGA investigation — 27 October 2026

Offline only; camera remains on revision 2.9, no new live VGA test or writes. See docs/uvc_native_vga_resize_investigation_20261027.md and verified_yc/evidence/native-vga-20261027/. Found actual libObj resize2VGA() at0x19fd94: paired SDS type0xe0b00/image type0x220 allocations, width640 with aspect-dependent heights (426/360/640; fallback480), metadata store, resize helper0x19fc88. This is distinct from native VEF table record5/type0x295 with all640x480 and yc_compress0. Six original caller+SDK fixtures prove 68-byte requests: source type/handle+0x18/+0x1c, destination type/handle+0x38/+0x3c. They reference SSYC metadata, not bare pixel handles. Inspected RTOS parser uses a different extended layout; translation remains unresolved. Four original RTOS capacity fixtures prove VGA uncompressed614400B, HD uncompressed4147200B (exceeds existing0x320000 output capacity). Do not flip global compression flag. Next: recover source SSYC reference, complete paired destination allocation/metadata and release, verify compressed-to-uncompressed acceptance, bounded completion/cancellation, then one-shot live capture. Ten offline fixtures passed; no hardware-format proof. Fresh boot required before further live test because retained 2.9 USB output allocation reuse remains unresolved.

## Revision 2.9 complete native allocations captured — 27 October 2026

FFmpeg stream-copy captured16complete614400-byte USB packets,9830400bytes, no trailing bytes, exit0. All2.9 headers/payload CRC32/ranges/padding passed. Reassembly exported THREE distinct complete2073600-byte native allocations (IDs2/3/4); incomplete boundary IDs1/5 withheld. First packet starts ID1 offset614336, last is ID5 offset0. Snapshot SHA256s: ID2 4b0feb4634b753068f669fa96ec4705d989ecafeb87d12c66940b3cf65fbba47; ID3 df470de0c6cbb0c7c2b30f6448cb7e22a5f14168b687ddff043a47dc94037c5a; ID4 10ba544c9b58cdc45355066123058792a2ec55911c3a7d22f2031574317f04e6. Native image decoding, exact geometry/depth and frame-completion remain unproved.

One full binary plus accompanying text for decoder: workspace outputs/native-dmm-v29/decoder-handoff/zve10-vef295-full-snapshot.bin and .txt. Binary has native offsets0..2073599 unchanged, all64B chunk headers/final padding removed. Each group is one owned copy before USB chunking, never independently reacquired windows; source could change during that initial copy. At conditional1920-byte pitch all1080rows contain data; byte5 lag30 correlations0.8396..0.8520 across three snapshots. This supports structure through the full allocation, not definitive live metadata.

Measured FFmpeg elapsed6.76s:2.37USB PACKETS/s, about0.59full snapshots/s at4packets per allocation. Do NOT call this2.4image-fps or24fps. Camera runtime SNAPSHOT_US84.722..116.086ms (mean99.642), first PACKET_COPY_US304.686..359.570ms (mean336.191). Packet assembly includes full memset/memcpy and bitwise CRC over output mapping; it is the largest measured phase. CRC is a prime optimization candidate, but individual substeps were not separately timed. Remaining100ms entry sleep adds overhead. Module logs retain inherited INSTALLED_V25 label; installed MD5s match actual2.9 producer b4c6012cd876210fcfd0cf4b0d6f67e0 and stream32a2d064d25720c17dd9a43927d4a835; common/kernel unchanged.

After stopping, dynamically addressed module-state readback verified7native snapshots,25software packet submissions (includes prefetch beyond16saved),28requests/28replies, backendIDLE, no native shared/open refs/token, no pending heap snapshot, USB in-flight0. HOST_WAIT occurred after host close; final submit rejection during mode stop is in logs. Separately, the module retains its owned output mapping/handle0x0cb9 atphysical0x15b00000 although that unit is absent from post-stop DMM listing. These addresses are session diagnostics, never replay. Full mode-cycle reuse remains unverified and must not be assumed safe merely because native-source references were released.

User reported one restart before the successful run and requested proceeding. Runtime log contains two LOAD/setup sequences; cause unresolved. Persistent files survived and current capture checks passed; this does not prove crash independence or frame coherence. After collection,9known camera capture files199700bytes were downloaded, hash-verified, rechecked and individually cleared; storage and /tmp write/readback passed. Runtime/fonts/tools/system logs preserved. Service session closing. No additional patch or reboot during successful capture/log collection.

Compact evidence: research/firmware/yuy2_transport_v29_full_snapshot/evidence/full-capture-20261027/. Full host capture and all3native binaries remain under workspace outputs/native-dmm-v29/capture-first-01/. Next work: exact codec recovery with complete buffers/live metadata; optimize packet assembly/CRC and remove needless pacing with measured checks; resolve output allocation reuse before claiming repeatable mode cycling.

## Revision 2.9 installed and reboot verified; capture pending — 27 October 2026

User authorized flashing with camera connected in mass-storage/service mode. Exact prior2.8 hashes and cold process mappings matched. Normal error filters restored;19known diagnostic status files (714bytes, no large old application capture found) were downloaded, hash-verified, rechecked and individually deleted. /tmp runtime fonts/tools/system logs preserved. Space guard passed before/after cleanup and after reboot, including4096B /tmp write/readback. Initial memory:128796KiB total,1452KiB free,55820KiB cached; new4MiB snapshot heap is allocated lazily during actual capture and remains untested.

Installed /usr/lib/yuy2_640_v29full.so MD5 b4c6012cd876210fcfd0cf4b0d6f67e0 (30600B), /usr/lib/libInfraStreamingUsb.so MD5 32a2d064d25720c17dd9a43927d4a835 (72796B). Installer returned0; both binaries downloaded and verified. Previous2.8 stream MD5 27f4f4696c724caa8348edc51c86a517 and stable2.4p rescue MD5 5fde77e394572ebcf420f8941575f6c4 downloaded/verified under /usr/share/yuy2-recovery-v29full/. Explicit rollback.sh restores working2.4p; failed-install recovery restores previous2.8. Existing kernel/RTOS/config/common/SDK hashes unchanged. Kernel reboot messages confirmed restart; subsequent uptime54.10seconds and reread hashes confirmed persistence. /usr ext2 read-only; streaming library, yuy2 patch and observers/probes absent from pre-setup process maps. No MENU/streaming behavior or frame capture validated yet. Do not claim image output or improved fps.

Evidence: research/firmware/yuy2_transport_v29_full_snapshot/evidence/hardware-install-20261027/; full workspace outputs/native-dmm-v29/deployment/. Current module runtime log will be /log/yuy2_640_v29full/runtime.log on activation. Application logging remains at normal error filters. Service session closing after readback; no RAM probe installed. Next live step: USB Streaming with OBS closed, FFmpeg stream-copy at640x480/YUY2/10fps for at least16packets, run2.9 reassemble.py, then MSC/service log/ownership collection without reboot. Each packet now has64B header and614336B native payload; a2073600B allocation requires4packets. Pixel format and exact codec remain unknown.

## Independent codec recovery: exact parser still unresolved — 27 October 2026

Continued offline at user's request. No camera access or patch changes. New investigation/evidence: docs/uvc_vef295_independent_recovery_20261027.md and verified_yc/evidence/codec-recovery-20261027/. Across ten captures,34279blocks isolate candidate Y/C streams with W4=W5=0; supplied decoder leaves nonzero candidate-luma bits unread in29163(85.08%) and candidate-chroma bits in14604(42.60%). Its output is not a bit-complete validated decoder under the claimed routing. A57-bit isolated chroma candidate has only19ones, incompatible with64tokens each ending1 under the proposed pure-unary model. Alternate run syntax/count/routing remains possible.

Independent Rice/Exp-Golomb/sign/interleaved and initial-anchor searches found no validated parser. A compiled21952-variant groupwise search fit at most125/384isolated stream endings, rejected as universal; this is bounded negative evidence, not proof no adaptive/transform/Rice-like codec exists. Native bit-depth log mapper0x63a06dfc executed:0=DEPTH_8,1=DEPTH_10,2=DEPTH_12,3=DEPTH_14,4=UNKNOWN. Connection to SSYC enum/live source not yet proved. Additional Stage_Decomp path traced acquire0x63b31fec/start0x63b3218c/release0x63b32078 via hardware resource operations; no link to VEF0x295, possibly RAW-stage, do not call on YC based on name. Two Sony block-compression patent leads remain unconfirmed architectural references, not identified codec specifications.

Installed camera remains2.8; prepared2.9 unchanged/unflashed. Do not port heuristic reconstruction as a verified decoder. Full allocation plus same-delivery metadata, native codec specification, or independent known-content captures remain the most discriminating evidence. Metadata alone would identify format flags, not entropy rules.

## External decoding theory audited against firmware — 27 October 2026

Offline firmware/code/data cross-check saved in docs/uvc_vef295_codec_crosscheck_20261027.md and verified_yc/evidence/codec-audit-20261027/. No camera access or patch changes; installed remains 2.8, prepared 2.9 remains unflashed. External agent's report and images were read only.

Confirmed byte5 lag-30 correlation 0.865677 (lags29/31 ~0.195); 3453/9600 blocks with W4=W5=0; reported W0 header counts reproduced. Compressed-HD/64-byte-block/30-block-row interpretation is a strong candidate. It is not yet an exact decoded-image format. Original VEF builder executed for four real records: HD compression flag1, VGA0; ALL write strip_width64 before the compression branch. Thus strip_width64 does not establish 64-byte compressed packets. Original mirror/compression-gated alignment function0x63a460d4 passed32 input cases; only under gates r2 in{1,3},r3==1 does it require (field+0x30 + field+0x34) divisible by64. Thirteen CalcStripWidth selector fixtures and four metadata executions saved. yc_bit_depth remains untouched by the inspected builder, not established by this audit.

Actual reconstruction implementation contains manually chosen luma anchors, quantizer/residual scales1.6/0.8/0.75, modeled chroma around128 and Cr partly derived from Cb. Instrumenting its functions:544/9600 blocks parse fewer than56 luma residual tokens;5763/9600 parse fewer than64 chroma tokens, with remaining samples filled by the implementation. Natural-looking bounded output is not proof of exact anchor/color decoding. Zero-tail termination, escape coding and nonoverlap of candidate streams are unresolved. 1920x1080 active geometry, exact 1B/pixel, bit depth, 4:2:2 plane ordering and tear-free semantics still need matching live metadata/codec evidence. No matching software pixel decompressor found in bounded compression configuration paths or named Linux exports; not proof absent globally.

Next: full allocation capture with2.9 plus same-delivery ImageSizeInfo/YcStateInfo, then bit-exact codec validation using explicit bit accounting and independent scene data. Note2.9 uses64-byte headers, so native chunk payload is614336 bytes and final2073600-byte-allocation payload is230592 bytes. Use reassemble.py; do not apply the external report's unframed614400-byte offset schedule. A pin SEND hook alone does not establish frame stability without its reference/completion/return protocol.

## Revision 2.9 full-allocation patch prepared offline — 27 October 2026

Camera is offline; no device access or writes. Installed version remains 2.8. New source: research/firmware/yuy2_transport_v29_full_snapshot/; workspace package: outputs/native-dmm-v29/zve10-v29-offline-package.zip. Candidate producer MD5 b4c6012cd876210fcfd0cf4b0d6f67e0 (30600 bytes), persistent streaming library MD5 32a2d064d25720c17dd9a43927d4a835 (72796 bytes). NOT hardware verified.

2.8 sent only the first 614400 bytes of a 2073600-byte native allocation. 2.9 copies the whole returned extent once into bounded 4 MiB owned heap storage, completes native Close/Free, and sends numbered/checksummed chunks: 64-byte ZVYC0029 header + up to 614336 payload bytes per existing 614400-byte USB packet. Four packets cover the previously observed allocation. Host reassemble.py exports only complete, checksum-valid groups with headers/padding removed. No format conversion or synthetic fallback. USB YUY2 remains an envelope; OBS cannot display the new protocol as a proper image. Complete allocation does not prove coherent completed image, geometry, bit depth or compression format. Actual live ImageSizeInfo remains missing.

The 100 ms worker-entry sleep in 2.8 applied to multiple asynchronous native stages and is a plausible contributor to observed ~1 packet/s. New worker advances native state at most eight times per call with 1 ms retry sleeps; chunks share one owned snapshot. No camera performance claim. Wall-clock diagnostic timings added; full native copying, CRC and USB still cost time. Retains constructor-free lazy activation and existing kernel/RTOS/config. Source span limits and output-overlap guards reject unsafe buffers. Stop discards partial chunk groups after worker exclusion and drains native references.

Offline checks passed: compiled C ownership/full-copy/retry/range/mapping/reset fixture with exact 2073600-byte reassembly; eight host reassembler checks; compiled ARM worker with actual native state machine, delayed replies and retry preservation (CRC mocked in ARM and separately cross-checked from compiled C against Python zlib); 11 PIC/ELF cases; 4226 module instructions/no NEON; ten guarded installer/rollback fixtures. Hardware services, mounts and space helper mocked. Installer requires cold boot and exact installed 2.8 files; automatic failure restoration returns to 2.8, explicit rescue rollback to 2.4p.

Next live work: archive/hash-verify/clear known logs and temporary captures only, preserve runtime /tmp files, fresh boot with streaming unopened, current hash/maps/storage and memory checks (new 4 MiB heap reserve). Install guarded package; capture at least 16 packets with FFmpeg stream-copy, reassemble, recover logs and verify no native refs. Mode cycling and inherited kernel-owned output-allocation reuse remain unverified. MENU restarts unresolved. Do not claim 2.9 fixes crashes, achieves webcam frame rate or decodes an intelligible image.

## Revision 2.8 raw bytes captured; native YC buffer provenance verified — 26 October 2026

Installed2.8 producer MD5 5dd449056e4da5b7bea072d9e3b65d0b (28424B), streaming library27f4f4696c724caa8348edc51c86a517 (72796B), readback/reboot verified. Source selector now accepts observed native VEF type0x295, with shared type policy and allocation/open/status/span checks. FFmpeg stream-copy captured10complete614400-byte packets, then3more on same-session reopen, all distinct and no trailing bytes. Approximately1packet/s, despite10fps transport descriptor; pixels/packing remain unknown. No synthetic fallback or overlay. After exit:23native snapshots/submissions,100requests/100replies, context idle, zero shared/open references and no token. Last rejected Share at stop acquired no reference. Captured camera evidence was downloaded/hash-verified and cleared; final space guard and/tmp write/readback passed. Service session closed. Full mode-cycle capture and normal decoded-image output remain unverified.

Source is no longer supported only by a table coincidence: original VEF producer reads record+0x28 into ImageSizeInfo.unit_type and passes it to native RDV allocator0x637545ec (command12, queue0x0061003c). Returned handle is attached to ImageSizeInfo.unit_handle. Three real records and one type/handle taint control execute the original code with hardware services mocked; relevant regions match the patched RTOS image MD590096db2c76148f4f9db5d104e5c608c confirmed on camera. This verifies a YC image-attachment allocation family, not live metadata for the saved packet. Tested HD records set yc_compress=1, VGA sets0; all strip_width=64, data_content=2, data_placement=1, data_transfer=0, data_scan=1, data_offset=0. Do not infer bit depth, enum meanings, geometry, plane identity or packing from capacity alone.

Current source is research/firmware/yuy2_transport_v28_snapshot/; compact evidence verified_yc/evidence/native-dmm-v28-20261026/. Workspace outputs/native-dmm-v28/ retains full captures and state snapshots. User handed one unchanged614400B packet to another agent for offline image reconstruction. Updated text at decoder-handoff/zve10-vef295-snapshot.txt includes this provenance and conditional compression clues; binary SHA256 b0cceb40c44526e72784cec1892dcf86829113ba4c59376f19d5daf2a031714b remains unchanged. No messaging to other chats, new camera access or firmware changes during provenance verification. Recovery /usr/share/yuy2-recovery-v28snap/rollback.sh restores working permanent2.4p; previous2.7 image also preserved.

MENU automatic restarts recurred with normal error logging and old/tmp traces absent. Eight captures530033B were archived/verified/cleared from/log and known/tmp paths; runtime fonts/tools/kikilog were preserved. After deleting old/log captures Linux reported more free space than total; guard correctly rejected it. A controlled reboot restored in-range reporting and/tmp4096B write/readback passed. USB-unplugged checks preceded successful streaming; do not claim storage cleanup proved the crash cause or that menus are permanently fixed. New helper checks/tmp space and a real write/readback. Do not erase/tmp wholesale or infer disk corruption from the cached counter alone.

## Revision 2.7 first capture failed: active-source whitelist mismatch — 26 October 2026

Windows enumerates the expected USB camera and640x480/YUY2/10fps format; actual FFmpeg capture timed out30s with zero frames. User returned to service without a reported crash/reboot. Native SDK/private-queue initialization succeeded. Read-only module-state snapshot: backend IDLE, candidate0, no shared/open references or token, frames0, source errors602. Retained streaming-time DMM listing contains none of the three accepted types0x240b2e/0x6193f/0x61940. Exact compiled ARM selector replay rejects this listing and accepts an added positive-control whitelist row. Immediate cause is source selection, before native Share/Open, copying or USB submission. Those native operations remain hardware-untested. Do not claim a working raw webcam, an encoding failure or a format-conversion failure.

[First capture findings](../uvc_native_dmm_first_capture_20261026.md) records observed source candidates0x295/0x293 and the0xfe... alias guard issue; their role and packing are not established by size. Next: trace actual active producer/type mapping, then correct the source filter while retaining Share/Open/Close/Free ownership and address checks. Do not select audio, USB staging or0x276 output, or remove guards to force a frame. Source addresses from the read-only snapshot are session-specific and must never be replayed. No firmware change during this test;2.7 remains installed,2.4p rollback preserved. /tmp7600KiB free, normal logging. Camera captures were downloaded/hash-verified then individually cleared; service session closed. Full evidence in workspace outputs/native-dmm-callback/deployment/live/first-capture-01/; compact evidence in verified_yc/evidence/native-dmm-callback-20261026/first-capture-20261026/.

## MENU recovery after verified /tmp trace cleanup — 26 October 2026

After the 2.7 flash, user reported MENU/VIDEO caused automatic restarts. Earlier cleanup had removed only two /log diagnostic files (1711247B); /tmp was explicitly left full during deployment. That was incomplete as an operational cleanup. Current post-restart check reported /tmp 6464 KiB free, /log nearly empty, normal error-level logging, revision 2.7 hashes intact and no streaming/patch/probe mappings in the fresh process. A recovered MPR dump did not establish the restart cause; absent current mappings do not rule out pre-reset involvement.

Identified old research outputs in /tmp/opengate_trace/ (created by research/device/live_trace_record.py). Five files totaling 1124649B were downloaded, MD5-verified, rechecked on camera, then individually deleted. Preserved fonts, tools and system-managed kikilog.dat; never clear /tmp wholesale because it holds runtime resources and persistent helpers. /tmp then reported 7600 KiB free; a 4096-byte write/readback MD5 check passed and its scratch file was removed. User disconnected USB and retested MENU then VIDEO without streaming: **works now**. No firmware or logger-filter changes during this check; revision 2.7 remains installed. Cleanup/disconnection/reset timing mean this is observed recovery, not proven root cause or a permanent code fix. No real-frame capture yet. Service session closed.

Extend regular archive/hash-verify/clear procedure to verified research captures under /tmp as well as /log. Future deployment must check /tmp availability and perform an actual small write/readback before any firmware write; do not merely move staging elsewhere when scratch storage is full. Do not delete system-managed files or runtime fonts. Evidence in workspace outputs/native-dmm-callback/deployment/live/menu-crash-01/ and repository verified_yc/evidence/native-dmm-callback-20261026/menu-recovery-20261026/. Raw archived traces and MPR dump remain in the workspace. If menu restarts recur, preserve fresh reset evidence and compare against the guarded working-2.4p rollback instead of assuming storage is the sole cause.

## Revision 2.7 installed and reboot-verified — 26 October 2026

User authorized deployment. Guarded install completed with exit 0 and downloaded readbacks matching streaming MD5 c3aa9b92ea6c05ce78aa7894e8dfe35a (72796B), new producer ec185c27deb53f80f6f5a40d9a8f95f1 (28620B), working 2.4p backup 5fde77e394572ebcf420f8941575f6c4. After software reboot: uptime 125.67 seconds, installed hashes persisted, /usr mounted read-only, no libInfraStreamingUsb/yuy2/probe mappings present. Old 2.4p producer and proven USB kernel hashes unchanged. Recovery: `/usr/share/yuy2-recovery-v27snap/rollback.sh`, restoring working permanent 2.4p. Service session closed after verification. **No USB Streaming or real sensor packet test has been performed for 2.7.** Next: bounded fresh monitoring, activate streaming, FFmpeg opaque capture, test restart, return to service mode and archive/verify/clear logs. No eligible whitelisted DMM source was active during service-mode preflight; availability during streaming remains unverified.

Two old diagnostic logs (1711247 bytes) were archived and hash-verified before deletion. /tmp was 100% full: new Senser writes failed with error 130 and left empty files. /log was nearly empty; no system-managed /tmp files were deleted. Minimal /bin/busybox lacks find, df and awk. Corrected preflight uses a read-only statfs helper, actually executed on-camera; before install /usr available 11219968 bytes, /log 524025856 bytes. Package/helper/scripts were staged under /log, and direct terminal commands avoided full /tmp. The service workbench kept one session through preflight/staging/install. Existing toolbelt copied to /log/yuy2_640_v27snap/busybox for inspection; original binary name bbel does not dispatch applets properly. Never execute original obsolete fixed-base RAM helpers.

Ten adapted local installer fixture tests pass; actual preflight/install/readback/reboot evidence is in workspace `outputs/native-dmm-callback/deployment/live/` and repository `verified_yc/evidence/native-dmm-callback-20261026/deployment-20261026/`. The reboot job's final completion marker was absent because reboot terminated the session; CPU shutdown trace, reset uptime and new post-boot hashes/maps independently verify reboot. Current six-payload package includes space-check.elf; use the camera-adapted ZIP, not the superseded original five-payload ZIP. Updated reproducible package builder and single-step runner are in the source deployment folder. Previous pending-camera sections below are historical.

## Deployment package prepared — 26 October 2026

Guarded revision 2.7 installer, rollback to working permanent 2.4p, explicit single-step service runner and instructions are ready in `research/firmware/yuy2_transport_v27_snapshot/deployment/`. Ten local installer fixture cases pass, including pre-write rejection, damaged payload, failed activation, failed remount, automatic restoration and explicit rollback. Real flash/power-loss behavior is not proven. Workspace package: `outputs/native-dmm-callback/flash-package/`; ZIP alongside it. The package changes only the new producer module and streaming library, verifies existing SDK/kernel/RTOS/config hashes, preserves 2.4p and stores rollback under `/usr/share/yuy2-recovery-v27snap/`. No automatic reboot or mutation retries. **User is not ready; no camera session, log cleanup, upload, install or reboot was attempted.** When ready: fresh boot/service mode with USB Streaming unopened, archive/hash-verify/clear diagnostic logs, preflight, stage, install/readback, separate reboot, then bounded FFmpeg raw capture and restart check. Camera-side checks remain pending.

## Native raw snapshot callback implemented — 26 October 2026

Revision 2.7 now implements and auto-binds the missing acquisition callback. See [native DMM callback findings](../uvc_native_dmm_snapshot_v27.md) and `research/firmware/yuy2_transport_v27_snapshot/`. It uses original loaded libBizFw private-channel methods with prologue guards and native 24-byte requests to queue 0x0061003c: Share → Open(nonwaiting) → copy → Close → Free(only our shared allocation reference). Source candidates are selected from live `/proc/udm/dmm_units`; addresses come from native Open replies. No guessed source handle/address, fake 0x400 IPC, global observer hook or synthetic fallback.

Kernel finding: DMM opens do not pin allocation lifetime. Share increments unit+0xb20; Open increments separate +0xb21; final Free can destroy extents despite opens. The callback therefore shares before opening. This pins allocation lifetime, **not pixel immutability or frame completion**. Diagnostic snapshots may tear, and their packing remains unknown, deliberately deferred until a PC capture. Generic validated conversion still requires its stronger completed-frame contract.

Copied staging packets survive asynchronous cleanup, and no USB submission/new acquisition occurs before confirmed release. Pending IPC no longer triggers the stock ten-error stop mechanism. One outstanding command/private queue; ambiguous failures retain ownership. Stop discards unsent copies and progresses cleanup, retaining any unresolved state for restart. No background cleanup thread; a delayed stop can retain one shared allocation until later polling/reboot. Native SDK calls can allocate/lock internally; hard realtime ten-ms latency is not proven. Actual snapshot cadence is below the advertised 10fps envelope.

Offline verification passes: four native wire requests match executions of Sony SDK methods; twelve state/copy tests; fourteen compiled ARM worker cases including native callback, delayed replies, byte-exact output and second start; thirty-two inherited ownership/conversion cases; eleven PIC/ELF checks. Module text audit: 3876 instructions, no NEON. Service replies are fixtures. **No camera install, real-byte capture or working sensor webcam claim.** Active eligible source units and runtime mapping/coherence remain hardware questions. Permanent 2.4p remains last hardware-verified output.

Candidate: `outputs/native-dmm-callback/candidate/` in the workspace. Module `yuy2_640_v27snap.so` MD5 ec185c27deb53f80f6f5a40d9a8f95f1, 28620B; persistent library MD5 c3aa9b92ea6c05ce78aa7894e8dfe35a, 72796B. Repository evidence: `research/firmware/raw_frame_source/verified_yc/evidence/native-dmm-callback-20261026/`. No installer; obsolete generated fixed-base RAM helpers must not be executed. Preserve verified 2.4p rollback and 2.3 USB kernel. Next: separately authorized bounded hardware trial after archive/hash-verify/clear logs, capture opaque frames with stream-copy, verify restart, then analyze source packing on the PC. Previous 2.6 "callback missing" sections below are historical.

## Raw-byte diagnostic patch built —26 October2026

User directed us to defer pixel-format interpretation: tunnel source bytes through the existing webcam framing, save packets and analyze on the PC. [Revision2.6 raw diagnostic](../uvc_raw_byte_diagnostic_v26.md) implements that path in research/firmware/yuy2_transport_v26_raw/. It copies exactly614400 contiguous source bytes unchanged, with an optional inactive-configured byte offset; source format, stride, color flags and geometry are ignored. USB still advertises640x480/YUY2/10fps. No counter overlay, pixel conversion or synthetic fallback. USB readiness, source span bounds and ownership cleanup remain enforced. PC helper uses FFmpeg stream-copy and saves individual binary packets with hashes.

13 compiled ARM integration cases pass,32 inherited core cases pass,11 PIC/ELF cases pass; no NEON in audited module code. Built module and persistent streaming candidate are in workspace outputs/yuy2-v26raw/candidate/. No camera changes or installation. **A real Sony acquisition callback is still missing: this is an implemented opaque-byte transport path, not yet a camera-frame-producing patch.** Without a bound source it submits no frames. Prior assumption that only conversion was missing is incorrect. Prioritize a genuine bounded pixel-buffer reference next; do not spend more time interpreting its format before the first raw-byte capture. Do not replace working2.4p with an unbound candidate. Windows inventory found no connected Sony device during this work.

## Live-source continuation —26 October2026

Returned to genuine YC webcam work, offline only. [Native640x480 path and remaining blockers](../uvc_yc_live_source_20261026.md): original RTOS preview lookup and changeSSYCData executed. The preview table is nine20-byte records, not18;640x480 selects compression0. Native dataContent2 keeps full height with dataPlacement1; other tested values halve height with placement0. Thus placement does not establish YUY2/NV16. Native640 types0x6193f/0x61940 map to extents0x8e/0x8d; separate resize type0x240b2e maps to614400B extent0x14e. These are configured candidates, not current frame addresses or leases. Seven geometry and five metadata execution cases pass; source packing, active routing and read lifetime remain unresolved. No camera changes or real-frame patch claim.

Inherited scope corrections:0x63a2e47c is a JPEG-specific unit-alignment routine, not proof of a universal YC DMA rule;0x63dbcd70/+0x48 are address/length getters, not static plane tables. Three direct metadata-builder calls do not rule out every indirect call. Preserve completed31-field and multi-segment components and permanent2.4p bars. New evidence/tests are in verified_yc/evidence/yc-live-20261026 and verify_preview_update.py / verify_preview_geometry.py. Kernel mapping investigation remains a lead; do not use unverified address arithmetic in a target patch.

## Paused for handoff: native YC delivery & multi-segment pipeline verified — 25 October 2026

Offline reverse engineering completed all requested RTOS memory, geometry, and metadata components. No camera access or new installation; permanent 2.4p synthetic bars/counters remains the last hardware-verified transport. See [full source findings](../uvc_yc_source_recovery_20261025.md) and [ready-to-paste prompt](../90-session/YC_NEXT_AGENT_PROMPT.md).

All 31 scalar `ImageSizeInfo` fields are now fully integrated into `sony_yc_metadata.h/.c` and verified in Unicorn against Sony's real SDK getters and 60 truncation cases (`verify_metadata_decoder.py`). Additionally, SSYC Category 1 (`YcStateInfo`, 6 bytes) and Category 0x11 (`MultipleSegmentImageInfo`, 288 bytes) are fully implemented and verified (`verify_sds_reader.py`, `verify_multi_segment.py`). The multi-segment slice extractor (`sony_yc_segment_extract_image_size`) and dual-strip width merger (`sony_yc_segment_merge_image_size`) match real Sony RTOS code (`0x63cebf24` and `0x63cec0d8`) byte-for-byte across slots 0 and 1.

The complete VDF DMM IPC command family in `av-cam.bin` (`0x6371f4a0..0x6371f8f8`) is now mapped: Command 1 (alloc), Command 2 (share across queues), Command 4 / 13 (immediate/delayed sync free), Command 5 (open mapping / physical address resolution), and Command 6 (close mapping). All 10 methods and 18 call sites of the VDF Ownership Manager vtable (`0x645852c8` / `0x64585300`) and the frame completion/release handler `VDF::VdfInputReleasePinAndMem::Execute` (`0x63728000..0x6372889c`) are documented with disassembly evidence in `verified_yc/evidence/`. SDF plane alignment function `0x63a2e47c` proves hardware DMA requires 128-byte address and size alignment. All 35 pytest tests pass; all 6 verification scripts pass with 0 errors.

## Offline live-YC source recovery — 25 October 2026

User redirected work to genuine YC source reverse engineering and a live webcam patch; set loader diagnostics aside. No camera access this turn. [Verified source recovery](../uvc_yc_source_recovery_20261025.md):190 candidate local YC callsites recovered in libObj using actual PLT relocations and unwind ranges;25 metadata fields recovered by executing Sony's own getter/printer. Real renderer delivered-SDS path and separate pixel unit handle traced. New bounds-checked decoder in `research/firmware/raw_frame_source/verified_yc/` agrees with Sony execution, but pixel enums, live-preview routing and frame ownership/return remain unresolved. Permanent2.4p remains last verified synthetic transport; no working live-frame patch claimed. Revision3 RAM probe was installed before user stopped; current camera state is unknown. Never replay stale addresses. Keep routine archive/hash-verify/clear log procedure.

## YC retest: baseline passed; loader-only probe armed

User standing instruction: clear diagnostic logs regularly. Before each new hardware test, stop prior captures, restore normal error filters, archive and hash-verify diagnostic captures, recheck camera hashes, then delete only verified diagnostic paths and confirm absence. Preserve firmware, calibration, helpers and system-managed logs. Use a fresh test directory and bounded capture. After collecting each run, repeat archive/verify/clear. This is an operational procedure, not a scheduled automation.

Baseline without observer passed ten complete 640x480 YUY2 bars frames, counters1–10; uptime197.29→981.42 seconds confirms no intervening reboot. Persistent 2.4p hashes unchanged. Archived22 files/8,282,393 bytes with matching camera MD5s; cleared7 capture files/8,180,954 bytes. Earlier cleanup cleared26 diagnostic files/19,916,504 bytes after archive verification.

Revision3 is a temporary loader-isolation probe, NOT a YC metadata observer. Its activation writes only `YC_V3_LOADER_ACTIVATION_OK` to `/log/yc_observer/runtime-v3.log`, with no Sony API, GOT hooks, subscription or pixel access. Module MD5 `4a6de2407407c3b8f7ae2c2a3366ad60`; three ARM probe cases and four bootstrap cases pass offline. RAM write/readback verified for PID157/base0x0a661000, prepare0x0a669d00 and cave0x0a66a630. Addresses are session-specific: never replay after reboot/process change. No persistent firmware changes. Previous metadata observer remains withdrawn.

Fresh debug capture `/log/yc_retest_20261024_02/app-sequential.log` is active with a guard stopping capture/restoring error filters after300 seconds or16MiB (polled every2 seconds). Service closed; awaiting user streaming activation, FFmpeg and service return for collection. Current local state/evidence: `outputs/yc-retest-20261024/`. No successful revision3 activation is claimed yet.

## Observer withdrawn after second reboot — 24 October 2026

Both temporary observer attempts were followed by a reboot. Latest service snapshot shows uptime 133.59 seconds, no observer mapping, no streaming-library mapping, and no observer2 runtime log. The fresh boot cleared the RAM bootstrap; do not restore or replay old addresses. The observer/bootstrap is suspect, but no retained crash PC establishes the cause. No genuine YC metadata or live camera frame was captured. Earlier three-frame bars capture happened after the first reboot and validates only permanent 2.4p.

There is no evidence that `/log` is full: recursive directory inventory found 447 regular files totaling 84,328,592 logical bytes (80.42 MiB), versus reported volume capacity 524,206,080 bytes (about 500 MiB). The filesystem free counter incorrectly reports the entire volume free despite existing files; do not cite that counter as precise free space. Allocation overhead was not measured. No files were deleted.

Permanent streaming library MD5 `5fde77e394572ebcf420f8941575f6c4`, producer `9181ef744955190d04728cf4ef7965c5`, and kernel `c1cad400372e26eca729e4b9bc47a237` still match the working 2.4p installation. Application debug filters were not changed. Second-attempt evidence archive contains 56 files / 5,528,122 bytes, all verified against camera MD5s. Service session closed normally. Current evidence/state is in workspace `outputs/sony-backend-recovery/deployment/`, especially `second-attempt-archive-verification.json`, `log-space-assessment.json`, and `state.json`.

Next work is offline fault isolation of the RAM loader, real execution context and observer ABI before another hardware probe. Passing emulation/import checks did not validate execution on the camera. Do not reinstall the observer or guessed Sony IPC. The generic 2.5 lease pipeline remains offline; the real Sony source subscription, buffer layout and ownership contract are unresolved. Preserve permanent 2.4p synthetic transport.

## Withdrawn Sony backend completion claim

The earlier claimed subscription pin, 0x400 acquisition protocol, two-plane DMM reply, bounded acquisition and stable frame lease were not established by the binaries. See [corrected evidence](../uvc_sony_backend_recovery.md). Default and ARM-target Sony backend builds now fail closed; the former model is available only as an explicit non-target test fixture. No real Sony backend is complete.

## Revision 2.5 — offline live-source pipeline implemented; Sony backend pending

[Implementation report](../uvc_live_frame_implementation.md): lease-based acquire/validate/readonly-map/scalar-convert/unmap/release core is integrated into a new producer candidate; host completion precedes acquisition and failed source cleanup is retained. `yuy2_live_bind` registers a verified in-process backend while inactive. Initial offline core implemented with synthetic fallback prior to genuine subscription recovery. Stock `get_video_image(JPEG_DATA_INFO*)` is not a YC getter and its body is the installed PIC gate. `getYUVReadStart()` returns status, not a frame pointer. Source `research/firmware/raw_frame_source/` and `yuy2_transport_v25/`; session `outputs/yuy2-640-v25/`. No camera changes; permanent 2.4p remains installed.

## Live CPU verification — 24 October 2026

Direct service-shell `/proc/cpuinfo` reports four processors (0–3), ARM implementer `0x41`, part `0xc05` (Cortex-A5), revision 1, hardware ARM-CXD900X0. Features: `swp half thumb fastmult vfp edsp vfpv3 vfpv3d16 tls vfpv4`; **no neon**. Earlier Cortex-A9/NEON assumptions are incorrect for the Linux-visible CPU. VFPv4 is not evidence of NEON. Plan scalar integer conversion/copy; do not execute NEON kernels without new capability evidence. Live feature absence establishes unavailable advertised userspace support, not physical absence independently of kernel configuration. No instruction probe performed. Raw-source report NEON kernels/performance estimates need rework; older A9 compiler tuning does not establish A9 hardware. Evidence: session `outputs/zve10-cpuinfo-neon.log`. Read-only query; no firmware writes.

## Revision 2.4p — permanent installation, FFmpeg reopen and OBS pass

[Permanent deployment report](../uvc_yuy2_patch_v24p.md) supersedes historical pending/offline states below. Streaming library `5fde77e394572ebcf420f8941575f6c4`, constructor-free producer `9181ef744955190d04728cf4ef7965c5`, kernel `c1cad400372e26eca729e4b9bc47a237` / version `yuy2_640_v23`. Genuine reboot verified persistence, dormant boot and service access. Prepare activates automatically via PIC import; no manual RAM bootstrap, though runtime hooks remain. First FFmpeg and same-session reopen each yielded ten exact frames (counters 1–10, 29–38); subsequent OBS passed without mode toggle. HOST_WAIT/HOST_RESUMED confirms host-idle recovery; no producer failure-stop markers. Still synthetic bars/counters, not live footage.

59 camera files / 6,693,389 bytes hash verified; 24,808 application records decode without corruption/slack. Normal error logging restored, capture stopped, service session closed; camera last in mass-storage/service mode. `/usr` read-only, no overlay. Source `research/firmware/yuy2_transport_v24p/`, session outputs `outputs/yuy2-640-v24p/`; 79 offline checks pass. Recovery `/usr/share/yuy2-recovery-v24p/rollback.sh` MD5 `cd67ea02a57715d823ca7c1baf99499b` restores pre-install baseline (not factory streaming library) and factory kernel, then needs genuine reboot. Do not hot-unload pinned source or replay old jobs. Common-library eight-byte descriptor drift recurred after streaming; cause unresolved, installer did not write it. Raw-source work follows [canonical prompt](../uvc_raw_frame_source_prompt.md); preserve working transport and cold-install guards.

## Offline delivery diagnosis — 24 October 2026

## Revision 2.4 host-reopen candidate — offline verified, not installed

[Revision 2.4](../uvc_yuy2_patch_v24.md) treats WaitVideoReadCmp EBUSY as backpressure rather than invoking either our five-failure shutdown or Sony's ten-failure stop notifier. It reads libc TLS errno, preserves source bytes and ownership while busy, and resumes only on readiness success; other errors and explicit stop retain bounded recovery. Eight new regressions plus inherited checks pass: 50 producer + four bootstrap + 14 unchanged kernel checks (68 total). Userspace MD5 `c237ec9a3024d4b075e96943dab2ddb5`; kernel stays proven 2.3 MD5 `c1cad400372e26eca729e4b9bc47a237` / version `yuy2_640_v23`. Source `research/firmware/yuy2_transport_v24/`, local build `outputs/yuy2-640-v24/candidate/`. No camera changes this turn; 2.3 remains last live installation. Fresh-boot hardware host close/idle/reopen test is still required; kernel cancellation/readiness behavior is not mocked proof. Separate raw-source investigator uses [this prompt](../uvc_raw_frame_source_prompt.md); do not mix source acquisition into the reconnect patch.


## Work split — live raw source research and USB host-reopen fix

User requested the handoff/prompt target live uncompressed camera frames through our proven USB transport, while the primary agent fixes same-session USB host reopening. [Raw-frame investigation prompt](../uvc_raw_frame_source_prompt.md) is the canonical scope; the external `prompt_draft.md` has been redirected to the same content. No new agent or automation was launched. Raw-source research owns `research/firmware/raw_frame_source/` and `docs/uvc_live_raw_frame_source.md`; USB lifecycle candidate owns `research/firmware/yuy2_transport_v24/` and a separate revision report. Preserve the working 2.3 synthetic transport and its frame geometry. Raw-source work is offline only; do not replay camera jobs or change the currently loaded patch.


## Revision 2.3 final checkpoint — FFmpeg/OBS delivery confirmed, logs saved

Ten exact FFmpeg frames/counters and user-confirmed OBS frames after camera mode restart. Same-session host reopen remains broken; runtime confirms five-readiness-failure shutdown sequences and retained-source rebinding on mode restart. 57 files / 9,231,531 bytes hash verified; 111,319 application records decode with zero corruption/slack. Normal error logging restored, capture stopped, service session closed. Volatile kernel overlay and RAM hooks remain; do not hot-swap. [Full verified result](../uvc_yuy2_patch_v23.md). Next: host-inactivity/client-reopen lifecycle fix; no live sensor capture yet.


## Revision 2.3 — FFmpeg and OBS frame delivery confirmed

First FFmpeg capture passed ten exact synthetic frames/counters. User then restarted USB Streaming and confirmed OBS outputs frames with counters at 640×480 YUY2 / 10 fps. Same-session host reopen remains broken; mode restart restores delivery. Awaiting return to service without reboot for logs. [Current results](../uvc_yuy2_patch_v23.md). No live sensor capture yet.


## Revision 2.3 — first frames pass; later host open fails

First FFmpeg capture delivered ten exact synthetic YUY2 frames (6,144,000 bytes, counters 1–10). User later reported OBS failure; FFmpeg reopening the same session also timed out with zero bytes. Suspect host-inactivity/readiness handling, pending camera runtime logs. User asked to restart USB Streaming and try OBS as first client. [Evidence and current test state](../uvc_yuy2_patch_v23.md). Do not claim OBS or restart success yet.


## Revision 2.3 paired deployment — awaiting first stream test

Kernel temporary overlay loaded and sysfs version verified; RAM bootstrap/readback verified at fresh base `0x0a61e000`. Final kernel MD5 `c1cad400372e26eca729e4b9bc47a237`; 60 offline checks pass. Fresh debug logging is active; service session closed and user asked to activate USB Streaming for FFmpeg. Userspace constructor and host frames not yet confirmed. [Exact deployment checkpoint](../uvc_yuy2_patch_v23.md). Genuine reboot removes overlay and RAM hooks; underlying stock kernel was not overwritten.


## Revision 2.3 preflight — logs cleared, awaiting setup reload

User requested clearing old logs before reloading setup. Preserved and hash-verified all 75 selected test capture files (61,967,231 bytes), including five files newly downloaded. Rechecked every camera hash before exact-path deletion and confirmed each file absent. This removed old test `.log`/ring-dump capture files from known experiment folders; calibration, system-managed logs, firmware, module files and binary helpers were not deleted. Normal error filters restored; sequential capture stopped. Internal logger history was not explicitly reset. New `/log/yuy2_640_v23` created with clean preflight metadata. Service session closed normally. Awaiting user to open USB Streaming setup without starting, then return to mass storage/reconnect for fresh-map paired activation. Revision 2.3 is NOT installed. Local evidence and machine-readable state: `outputs/yuy2-640-v23/preflight/`. See [live checkpoint](../uvc_yuy2_patch_v23.md).


## Revision 2.3 candidate built — 24 October 2026

User requested a new patch; no deployment requested or performed. [Revision 2.3](../uvc_yuy2_patch_v23.md) pairs the revision 2.2 userspace producer/restart correction with a guarded kernel module candidate. Kernel probe now reports a 614,400-byte pixel frame, 614,412-byte payload maximum and fixed 10 fps in PAL/NTSC; the one-header frame payload asserts EOF. Five guarded kernel sites change, and exact rollback is verified. 42 producer/lifecycle + four bootstrap + 13 kernel checks pass, with descriptor/kernel contract checked during packaging. Source: `research/firmware/yuy2_transport_v23/`; local binaries/manifest: `outputs/yuy2-640-v23/candidate/`. Kernel MD5 `1789b7bd52bd00a11d9d6353778a7449`, userspace MD5 `bef71344d4d6308e57ab65bdff3283e5`. Both parts must be activated together; no automatic installer supplied. Verify loaded kernel and fresh process maps before deployment, clear old hooks, and retain stock kernel rollback. Hardware acceptance of larger payload and actual frame delivery remain unproven; no live sensor capture yet. Existing revision 2.2 camera state is unchanged by this work.


User requested offline reverse engineering only. [Audited findings](../uvc_yuy2_delivery_audit_20261024.md): userspace YUY2 descriptors/producer did not update the kernel probe responder. Kernel advertises stock 14,745,600-byte maximum frame, 30/25 fps, and 300,000-byte maximum payload; prototype queues 614,412 bytes with one UVC header. This is a concrete negotiation/packetization gap and strongest offline zero-frame mechanism, with Windows/on-wire behavior still unproven. The supplied team's EOF-only and 110 MB delivery claims were corrected: UVC 1.1 class spec makes EOF optional, and kernel success/cleanup paths can conceal drops/errors. Seven bounded ARM fragment cases plus constant assertions pass. Revision 2.1 owns the 180-submission runtime; revision 2.2 runtime remains unrecovered. No camera operations or new deployment. Align kernel probe and packetization next; retain revision 2.2's separate manager-lifetime correction.

> **SESSION RECORD - not a reference.** This is a dated log of how a finding was

## CURRENT CHECKPOINT — revision 2.2 deployed; user moving laptop

User requested saving progress before moving laptop. No further camera operations. Revision 2.2 RAM bootstrap installed/readback verified at streaming base `0x0ea6d000`; first activation enumerated 640×480 YUY2/10 fps, but FFmpeg timed out after 25 seconds with zero bytes. Stop/restart test was requested but NOT confirmed performed. Runtime/application logs not yet recovered; camera logging may remain active at `/log/yuy2_640_v22/app-sequential.log`. Last confirmed camera mode: USB Streaming first activation. No host sessions running. Preserve logs and verify actual camera state on resume; reboot clears RAM patch. Do not reinstall over loaded hooks. [Exact live checkpoint](../uvc_yuy2_patch_v22.md). Local `outputs/yuy2-640-v22/deployment/deployment-state.json` records current evidence. Menu check passed with normal logging and USB unplugged; no log deletion/firmware restoration performed. Earlier pending-install notes below are historical.


Menu investigation update: user completed MENU/VIDEO and streaming on/off successfully with USB disconnected and debugging enabled. Fourteen run artifacts hash verified; 45,839 application records decode cleanly. Capture stopped and logging restored to normal error level; awaiting repeat MENU/VIDEO check with USB unplugged. No YUY2 module installed, no firmware changes, no permanent menu fix claimed. Streaming library loaded at `0x0ea6d000`; revision 2.2 loader is being verified for this map while waiting.


Current blocker: inconsistent MENU/VIDEO-tab failure reported after the reboot to clear revision 2.1. [Menu investigation](../uvc_menu_crash_20261024.md). Fresh-boot maps confirm no YUY2 or streaming library loaded. Revision 2.2 is built/offline-verified but NOT installed. Initial logs/hash snapshots are preserved; application debug capture is active for reproduction. No storage-full error found and no logs deleted. Do not describe menu crash or host-frame delivery as fixed.


Revision 2.2 restart correction is built: [candidate report](../uvc_yuy2_patch_v22.md), source `research/firmware/yuy2_transport_v22/`. It detaches stopped managers while retaining one module-lifetime source, and requires driver completion before pixel reuse. All 42 ARM + four bootstrap cases pass; hardware installation/test pending. Original zero-frame delivery is not claimed fixed. A reboot command was sent to clear revision 2.1; verify old-module absence before guarded installation.


Latest repeat-activation finding: standby/no USB enumeration is now traced to three revision 2.1 connect rejections with error `0x21` (decimal 33): new VideoEsManager differs from the old manager retained with a DMA-pinned source. Service access still works. Nine new snapshots were hash verified; no reboot or further patch was performed. See the revision 2.1 live report's repeat-activation section. The initial zero-frame delivery problem remains separate and unresolved.


## Latest verified result — revision 2.1, 24 October 2026

[Live report](../uvc_yuy2_patch_v21.md): revision 2.1 installed in RAM and module activated. Windows/FFmpeg enumerate 640×480 YUY2/10 fps; ten-frame capture timed out after 25 seconds with zero bytes. Source unit `0x276` allocated exclusively (physical `0x15b00000`, 3,276,800 bytes), at least 180 submissions accepted by API, no host-frame proof and no PROBE/COMMIT runtime markers. Later readiness failures left source pinned; do not hot-swap or free it. User returned to service mode; 44 files / 7,655,944 bytes recovered and hash verified, debug capture stopped. The installer wrote RAM only; after streaming the common-library file read as prior 1080 candidate MD5 `bd32c223e60e363d900c7ac8be06641c` (eight descriptor bytes), despite stock hash after arming. RTOS/streaming hashes remained unchanged. File transition/persistence remains unresolved; see live report. Inspect original startup completion/host control and gadget DMA delivery next. Source-only recipe: `research/firmware/yuy2_transport_v21/`; 35 ARM + four bootstrap cases pass. Historical entries below retain earlier states.

> reached. Anything still true of it has been extracted into the topic docs; do
> not cite this file as fact. Kept for provenance only, so that a retracted
> claim is not silently re-derived.
>
> Current documentation: [docs/README.md](../README.md)
# Handoff: ZV-E10 reverse engineering

State as of commit `5990388` + verified UVC 1080p live deployment. Written for an agent picking this up cold.

**Repo:** `D:\02_Development_And_Projects\pmca-re` · **Python:** `.venv\Scripts\python.exe`
(always pass `-B` to skip stale bytecode) · **Tests:** 163+ passed across test suite (58 dedicated adversarial UVC tests, 100% pass in 0.86s).
**Git:** `qn06142 <90816999+qn06142@users.noreply.github.com>`, pushed to `github.com/qn06142/zv-e10-re`, default branch `master`.

```powershell
cd D:\02_Development_And_Projects\pmca-re
& ".venv\Scripts\python.exe" -B -m pytest tests/test_uvc_patch.py -v
& ".venv\Scripts\python.exe" -B scripts/patch_uvc.py --verify-only
```

---

## 1. Executive Summary & Current Device State

1. **UVC 1080p Webcam Patch Deployed & Verified**:
   - The verified 1080p UVC webcam modification is live on `/usr/lib/`.
   - `libInfraUsbCmn.so`: `ac1961d23addcd53f4fe7210d074eac2` (UVC 1.1 descriptors with `wTotalLength = 61`, 1920x1080 @ 30/25 fps).
   - `libInfraStreamingUsb.so`: `5a0417693a3d9ed1786c4d0afc043d6e` (VideoEsManager 1080p width `mov.w r2, #0x780`).
   - Stock copies remain intact on camera storage at `/setting/stock_libs/`. Reversible anytime with `/setting/revert_uvc.sh`.
2. **Residual 16:9 / Framing / NVRAM Patches Reverted**:
   - Reverted `/usr/share/app/color_cmn.uxc` back to factory stock `color_cmn.STOCK.uxc` (`f468bd3e72ca4e5b948a1c9f1f35c0a1`), removing the magenta framing guides from the LCD screen.
   - Restored `/setting/Backup.bin` and `Backup.bak` from factory original `/setting/Backup.orig` (`1c3165c21b13e13c6fed3c83425e2165`), clearing experimental aspect ratio tweaks.
   - Purged residual open gate / aspect test scripts from `/etc/`.
3. **USB Driver & Tooling Modernization**:
   - In-process Windows WinUSB support implemented in `pmca/usb/driver/windows/winusb.py` with `FILE_FLAG_OVERLAPPED` and isolated `WINUSB_INTERFACE_GUID` lookup.
   - `pmca/commands/usb.py` safeguarded with `try...except` to prevent single-driver `openDevice()` failures from breaking multi-driver enumeration.
   - Clean non-padded bulk packet sync handling for PID `0x0336`.

---

## 2. Root-Cause Post-Mortem: Why Prior UVC Patches Failed

Prior iterations produced broken streams or crashed `im.elf` with `SIGSEGV`. The 459-line engineering post-mortem in [`docs/uvc_patch_postmortem.md`](../uvc_patch_postmortem.md) isolates the 6 fundamental failure modes:

| Bug # | Failure Mode | Technical Mechanism | Affected Binary & Offset |
|:---:|:---|:---|:---|
| **1** | **Thumb-2 Endian Inversion** | Patcher wrote halfwords in reverse order (`f0 62 4f f4` vs `4f f4 f0 62`), turning `mov.w r2, #1920` into an illegal store `str r0, [r6, #44]`, crashing `im.elf` on stream start. | `libInfraStreamingUsb.so` (`0x908A`) |
| **2** | **Descriptor `wTotalLength` Mismatch** | UVC 1.1 requires `wTotalLength` to equal the sum of header + subordinate descriptors (14 + 11 + 30 + 6 = 61 bytes). Prior scripts clobbered `R_ARM_RELATIVE` pointers in companion tables at `0x14AB4` & `0x14DB4`, causing host USB stacks (`usbvideo.sys`, `uvcvideo`) to reject enumeration. | `libInfraUsbCmn.so` (`0x12537`, `0x14AB8`, `0x14DB0`) |
| **3** | **Bitrate Scaling Unit Bug** | Firmware scales bitrate in 100 kbps units rather than bps (`mov.w r3, #300` corresponds to 30 Mbps, not 300 bps or unbounded bandwidth). | `libInfraStreamingUsb.so` (`0x908E`) |
| **4** | **Upstream `set_path_sync` Zero Height Parameter** | `set_path_sync` hardcoded height to 0 at offset `+0x236`, breaking the BIONZ X hardware JPEG encoder aspect ratio calculations (`0x33E` timeout). | `libInfraStreamingUsb.so` (`0x8EB2`) |
| **5** | **DMM Memory Pool Exhaustion** | Unmetered frame allocations exhausted the camera's fixed Direct Memory Management (`dmm.ko`) DMA pool (`0x1D5` alloc error). | `libInfraStreamingUsb.so` (`0x9534`), `dmm.ko` |
| **6** | **Staged Baseline Divergence** | Earlier scripts targeted previously modified files rather than authentic firmware dumps in `dumps/camera_2025/usr/usr/lib/`. | `dumps/staged/uvc/binaries/stock/` |

---

## 3. Verified Patch Architecture & Deployment Suite

### Single-Shot Surgical Patch Generator
[`scripts/patch_uvc.py`](../../scripts/patch_uvc.py):
- Modifies **exactly 20 bytes** in `libInfraUsbCmn.so` (preserving `wTotalLength=61` and companion table pointers) and **exactly 1 byte** in `libInfraStreamingUsb.so` (`0x908C: 0xA0 -> 0xF0`).
- Decodes every modified instruction with Capstone in Thumb-2 mode to guarantee zero callee-saved register clobbers (R4–R11, SP, LR preserved).
- Staged output located in `dumps/staged/uvc/binaries/patched/`.

### Camera Deployment & Revert Tools
- **Live Deployment**: [`scripts/deploy_uvc_camera.py`](../../scripts/deploy_uvc_camera.py) (gzip + base64 chunked transfer, staged in `/setting/patched_libs/`, atomically copied to `/usr/lib/`, cold rebooted).
- **Residual Revert Tool**: [`scripts/revert_all_residual_patches.py`](../../scripts/revert_all_residual_patches.py) (reverts framing guide lines and restores pristine factory NVRAM from `Backup.orig`).
- **On-Camera Emergency Revert**: `/setting/revert_uvc.sh` (restores stock libraries from `/setting/stock_libs/`).

---

## 4. Multi-Layer Adversarial Verification Suite

[`tests/test_uvc_patch.py`](../../tests/test_uvc_patch.py):
- **58 offline tests** (100% pass rate in 0.86s).
- Covers 8 architectural domains:
  1. Cryptographic Dump Integrity (SHA-256 / MD5 validation).
  2. Capstone Thumb-2 Disassembly Guardrails (AAPCS compliance, literal pool bounds).
  3. UVC Descriptor Hierarchy (`wTotalLength = 61`, frame intervals 333333 / 400000).
  4. Relocation & Companion Table Preservation (`.rel.dyn` 781 relocations intact).
  5. USB 2.0 Bulk Endpoint & Transfer Bandwidth (512-byte max packet sizes).
  6. Multi-OS Host Descriptor Parsing Emulation (Windows `usbvideo.sys`, Linux `uvcvideo`, macOS `CoreMediaIO`).
  7. Adversarial Mutation Tests (asserts explicit test failure upon single bit flip, opcode swap, corrupted pointer, or truncated descriptor).
  8. CLI Generator & Subprocess Idempotency.

---

## 5. Live Camera Filesystem Layout

At current check:
- `/usr/lib/libInfraUsbCmn.so`: `ac1961d23addcd53f4fe7210d074eac2` (1080p UVC patched)
- `/usr/lib/libInfraStreamingUsb.so`: `5a0417693a3d9ed1786c4d0afc043d6e` (1080p UVC patched)
- `/usr/share/app/color_cmn.uxc`: `f468bd3e72ca4e5b948a1c9f1f35c0a1` (Factory stock)
- `/setting/stock_libs/`: Pristine factory stock copies of both UVC libraries.
- `/setting/Backup.bin`: `1c3165c21b13e13c6fed3c83425e2165` (Pristine factory original matching `Backup.orig`).
- `/setting/revert_uvc.sh`: On-device stock restore shell script.
- `/etc/`: Purged of test scripts.

---

## 6. Trap Reminders for Incoming Agents

1. **PowerShell Backtick Truncation**: Never pass inline strings containing backticks via PowerShell CLI arguments (`gh issue comment --body "..."`). Always use `-F body=@<file.md>`.
2. **WinUSB Handle Flags**: Opening a device handle for `WinUsb_Initialize` requires `FILE_FLAG_OVERLAPPED` in `CreateFileW`. Without it, `WinUsb_Initialize` fails with error 6 (`ERROR_INVALID_HANDLE`) or error 87 (`ERROR_INVALID_PARAMETER`).
3. **Multi-Driver Fallback**: Never allow a failure in `driver.openDevice()` to bubble up and crash `listDevices()`. Keep it wrapped in a `try...except` so secondary drivers (`libusb0`, etc.) can claim the device.
4. **Hibernation vs Cold Reboot**: On standard power-switch off, the camera enters RAM hibernation snapshot (`WBI1`) on `nflasha5`. Modifying files on `/usr` requires cold rebooting via `/bin/busybox reboot -f` to guarantee fresh reload into memory.
5. **No Blind Tests**: A test that only checks that bytes were written without decoding instruction opcodes or parsing descriptor byte-sums is a false test. Every patch must be guarded by disassembly and specification compliance checks.

## 2026-10-22 live encoder-fix deployment — supersedes earlier verified-1080p claims

User authorized flashing the offline encoder-workspace candidate. Current state is **partial deployment**, not verified working 1080p UVC.

- `/system/av-cam.bin`: `90096db2c76148f4f9db5d104e5c608c` — candidate RTOS workspace fix, persisted across reboot.
- `/usr/lib/libInfraStreamingUsb.so`: `19461091c07aa6900829defb0060fcd6` — candidate 1080p request and checked startup/caller, persisted across reboot.
- `/usr/lib/libInfraUsbCmn.so`: `31308976206a837f6f5c571992d2b499` — stock 720p descriptors after reboot. Candidate `bd32c223e60e363d900c7ac8be06641c` repeatedly matched immediately after writing, then reverted to factory inode/hash/timestamp. Atomic replacement, in-place eight-byte writes, and root-owned replacement all reproduced this. Inspected boot scripts did not explain it; dropping filesystem caches did not change it. Cause unresolved.

No post-deployment JPEG completion or host frame capture yet. The candidate's 59 offline emulation cases are not hardware validation. The earlier assertion that 1080p output was verified is incorrect.

Originals are verified in `/log/uvc_workspace_20261022/before/`: original RTOS `cdcae9d4fdbf66a33704a4c7564e346d`, common library `31308976206a837f6f5c571992d2b499`, and the user's intentional earlier width-only streaming patch `5a0417693a3d9ed1786c4d0afc043d6e`. Authentic stock streaming remains `/setting/stock_libs/libInfraStreamingUsb.so`, `cde7a1b42c919706aa5f61aba5fc0d75`.

Full second RTOS image does not fit on `/system`. The failed scratch copy was removed before active changes. A non-truncating 70-byte write via `dd ... 1<> /system/av-cam.bin` was tested on a staging copy, applied at file offset `0x810978`, and full-image MD5 checked. BusyBox lacks `conv=notrunc`. Original 70 bytes are `/log/uvc_workspace_20261022/workspace-original.bin`, MD5 `c0a3d45fd4b571b43af5a352193700a2`.

New `/log/uvc_workspace_20261022/revert-stock.sh` restores the RTOS function plus both authentic stock libraries and requires a subsequent verified reboot. It passed syntax checking; a full stock restoration has not been run. The older `/setting/revert_uvc.sh` restores only libraries and does not undo this RTOS change. Neither is proven recovery if the service shell cannot boot.

`/usr` returned read-only after reboot; `im.elf` PID 157 and `liro` were observed. USB sometimes disappears from Windows after leaving service mode; reconnecting the cable restored access. Do not treat USB return as streaming success. No font, resource, NVRAM, bootloader or partition-table changes were made in this deployment.

Deployment report and terminal logs: `C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\uvc-startup-fix\deployment\STATUS.md`.


## 2026-10-22 uncompressed USB 2 feasibility investigation

See ../uvc_uncompressed_usb2_feasibility.md. Offline analysis found that usbg_video.ko already uses DMA330 to copy physical-address/length payloads into USB staging buffers, separately from the JPEG producer. libBizFw.so has a concrete getYuvLayout wrapper at VA 0x39708, but a completed YUV frame acquisition/ownership contract is not yet recovered. Uncompressed 1080p30 NV12 needs 93.312 MB/s and cannot fit USB 2; lower modes or reduced frame rates are plausible pending measurement. Next proof: synthetic uncompressed UVC transport, then one real YUV frame. No camera operations were performed during this investigation. USB 3 remains deferred as requested.


## 2026-10-24 consolidation of the 2026-10-22 YUY2 prototype attempt

Durable results are now in [uncompressed USB investigation](../uvc_uncompressed_usb2_feasibility.md), [agent state](../agents/STATE.md) and [reference](../agents/REFERENCE.md). No new hardware test was performed for this documentation update.

The volatile 640×480 YUY2/10 fps synthetic prototype reached Windows/FFmpeg format enumeration, but a separate capture timed out after 25 seconds with zero bytes. The user reported a frozen camera and stopped hardware work for charging. No post-failure runtime log, DMM capacities or fault/thread trace was retrieved. The failure cause and the earlier VIDEO-tab crash remain unconfirmed.

Offline inspection found that source initialization failure permanently returns error 4 without a startup-failure completion, while the original video worker ignores the return. This is a concrete error-handling defect and a plausible freeze explanation, not a measured root cause. Corrected allocator interpretation: owner `0x2da`, staging unit type `0x50e`; the source helper takes unit type `0x50f`, not a requested byte count. Corrected descriptor length/pointer record VAs: PAL `0x1cab8`/`0x1cabc`, NTSC `0x1cdb0`/`0x1cdb4`.

Prototype changes are RAM hooks plus owned `/log/yuy2_640_20261022/` files; the earlier persistent RTOS/streaming-library deployment remains separate. Preserve `runtime.log` in that folder before a real reboot. Power-switch hibernation may retain hooks. Local evidence/source: `C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\yuy2-640` and sibling `work`. No complete synthetic frame, live YUV frame or working 1080p stream has been established.

## 2026-10-24 debugging attempt, forced restart and verified recovery

The user authorized debugging → USB Streaming → FFmpeg → service-mode log extraction. Debug capture was verified growing in `/log/usb_debug_20261024_01/app-sequential.log`. During the streaming transition Windows detected no Sony device and FFmpeg could not find the camera; no frame capture began. The user reported unresponsive controls and restarted the camera. This differs from the 22 October 25-second zero-frame timeout.

Recovered and hash-verified 34 files / 7,225,403 bytes, including the 1,936,183-byte binary application log. The prototype runtime file was identical before/after and already contained helper allocation error 4, source-initialization error 21 (`0x15`), and zero address/capacity. This establishes the earlier source-allocation failure, not a measured capacity shortage or the latest lockup cause. Application binary records remain undecoded. Fresh thread/DMM/kernel/MPR captures are post-restart state.

Uptime reset 5,049.03 → 53.57 seconds; YUY2 module was absent afterward and service access returned. Common-library hash reverted from `bd32c223e60e363d900c7ac8be06641c` to stock `31308976206a837f6f5c571992d2b499`; persistent RTOS/streaming candidates were unchanged. No new firmware or RAM patch was installed during recovery.

Full durable handoff: [YUY2 diagnostic reverse engineering](../uvc_yuy2_diagnostics_handoff.md). Host bundle: `C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\usb-debug-20261024-01`; verify with `transfer-result.json` and `camera/transfer.md5`. Next: decode preserved binary records, trace generic allocator error 4, recover correct lifecycle failure handling, then prepare a bounded test. Original VIDEO-tab crash and latest lockup remain unconfirmed. Do not automatically reapply the failed RAM prototype.

## 2026-10-24 revision 2 patch built after diagnostic handoff

User requested implementation. Created the source-only recipe at `research/firmware/yuy2_transport_v2/` and built the RAM-only synthetic 640×480 YUY2/10 fps module. Source allocation now requests exclusive JPEG workspace unit `0x276` / extent `0x333` (3,276,800 configured bytes), never audio `0x50f`. JPEG path configuration remains bypassed. Actual allocator success in camera mode is unverified; the pre-start guard returns an error instead of entering asynchronous Starting if allocation fails.

Implemented bounded retries, later connect retry, queued main-thread stop/reply recovery, and DMA-aware cleanup that pins an uncertain active source. Thirty ARM cases and four Thumb loader cases passed; portable rebuild yielded identical module hash. No camera operation, firmware write or RAM deployment was performed for this candidate. [Candidate report](../uvc_yuy2_patch_v2.md) records verification, exact hashes, limitations and next live acceptance. Current camera state remains the last verified post-restart baseline until checked again.

## 2026-10-24 revision 2 RAM bootstrap installation

User authorized installation. Initial guards refused an unloaded streaming library, then refused the stale base after the user opened its setup page. Rebuilt the loader for observed streaming base `0x0a663000` (common `0x04834000`, libdl `0x040ba000`), repeated 30 ARM plus four Thumb cases, and verified original target bytes. Uploaded the candidate and installed `0a66c0c0` / 380 bytes and `0a66bd00` / 12 bytes. Independent readback matched; firmware/config hashes stayed unchanged. Module MD5 remains `38e3b9a764b2bdb7470ac78e4ae25d4b`; rebuilt loader MD5 is `02a5084d5e2f7343b0d589a89b471a3e`.

Fresh debug capture under `/log/yuy2_640_v2/` was verified growing before service authentication closed. The user activated streaming; Windows and FFmpeg showed no Sony USB device. A cable-only reconnect was requested, preserving power/state for diagnostics. Module constructor execution and frames are not yet verified. Evidence: `C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\yuy2-640-v2\deployment`. Build/verification source now supports `--stream-base`; install addresses derive from the manifest. No firmware-image write or reboot was performed during this installation.
