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

## Paused for handoff: native YC delivery recovered —25 October2026

User asked to stop work and hand over. No camera access or new installation. [Ready-to-paste prompt](../90-session/YC_NEXT_AGENT_PROMPT.md) and [full source findings](../uvc_yc_source_recovery_20261025.md). New verified_yc C helpers decode native pin SEND, encode COMPLETE in Sony's original property order, and parse bounded SSYC/ETRY metadata without Sony C++ calls. Tests execute actual SDK constructors/SendComp/container insertion and lookup, plus the actual RTOS VDF metadata builder; this is offline evidence, not a successful live webcam patch. Permanent2.4p bars remains last hardware-verified output.

VDF queue0x0059000e and real pin registrations recovered. Native YUVInfo param0x11 feeds metadata builder0x6374ae88 and type0 output indices0/1; share command2 precedes delivery, temporary metadata mappings close with command6. Trace completion/write-stability, source packing/stride/planes and RTOS/Linux address translation next. Six extra fields (including YcBitDepth+0x36) verified via named getters; not integrated into the25-field decoder yet. Do not mistake synthetic input tags or initial geometry for camera observations. Source/evidence/test scripts preserved under research/firmware/raw_frame_source/verified_yc/. Camera/RAM-probe state unknown; preserve regular archive/hash-verify/clear logging procedure for future authorized hardware work.

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

## Revision 2.5 — offline live-source pipeline implemented; Sony backend pending

[Implementation report](../uvc_live_frame_implementation.md): lease-based acquire/validate/readonly-map/scalar-convert/unmap/release core is integrated into a new producer candidate; host completion precedes acquisition and failed source cleanup is retained. `yuy2_live_bind` registers a verified in-process backend while inactive. No Sony YC subscription/release backend is established by the supplied findings, so none is guessed or enabled; default output stays synthetic. Stock `get_video_image(JPEG_DATA_INFO*)` is not a YC getter and its body is the installed PIC gate. `getYUVReadStart()` returns status, not a frame pointer. Existing source survey's ownership/performance guarantees remain unproven. Source `research/firmware/raw_frame_source/` and `yuy2_transport_v25/`; session `outputs/yuy2-640-v25/`. No camera changes; permanent 2.4p remains installed. Next: identify actual completed-YC consumer subscription and lease-return ABI, bind it, then capture one live frame.

## Live CPU verification — 24 October 2026

Direct service-shell `/proc/cpuinfo` reports four processors (0–3), ARM implementer `0x41`, part `0xc05` (Cortex-A5), revision 1, hardware ARM-CXD900X0. Features: `swp half thumb fastmult vfp edsp vfpv3 vfpv3d16 tls vfpv4`; **no neon**. Earlier Cortex-A9/NEON assumptions are incorrect for the Linux-visible CPU. VFPv4 is not evidence of NEON. Plan scalar integer conversion/copy; do not execute NEON kernels without new capability evidence. Live feature absence establishes unavailable advertised userspace support, not physical absence independently of kernel configuration. No instruction probe performed. Raw-source report NEON kernels/performance estimates need rework; older A9 compiler tuning does not establish A9 hardware. Evidence: session `outputs/zve10-cpuinfo-neon.log`. Read-only query; no firmware writes.

## Revision 2.4p — permanent installation, FFmpeg reopen and OBS pass

[Permanent deployment report](../uvc_yuy2_patch_v24p.md) supersedes historical pending/offline states below. Streaming library `5fde77e394572ebcf420f8941575f6c4`, constructor-free producer `9181ef744955190d04728cf4ef7965c5`, kernel `c1cad400372e26eca729e4b9bc47a237` / version `yuy2_640_v23`. Genuine reboot verified persistence, dormant boot and service access. Prepare activates automatically via PIC import; no manual RAM bootstrap, though runtime hooks remain. First FFmpeg and same-session reopen each yielded ten exact frames (counters 1–10, 29–38); subsequent OBS passed without mode toggle. HOST_WAIT/HOST_RESUMED confirms host-idle recovery; no producer failure-stop markers. Still synthetic bars/counters, not live footage.

59 camera files / 6,693,389 bytes hash verified; 24,808 application records decode without corruption/slack. Normal error logging restored, capture stopped, service session closed; camera last in mass-storage/service mode. `/usr` read-only, no overlay. Source `research/firmware/yuy2_transport_v24p/`, session outputs `outputs/yuy2-640-v24p/`; 79 offline checks pass. Recovery `/usr/share/yuy2-recovery-v24p/rollback.sh` MD5 `cd67ea02a57715d823ca7c1baf99499b` restores pre-install baseline (not factory streaming library) and factory kernel, then needs genuine reboot. Do not hot-unload pinned source or replay old jobs. Common-library eight-byte descriptor drift recurred after streaming; cause unresolved, installer did not write it. Raw-source work follows [canonical prompt](../uvc_raw_frame_source_prompt.md); preserve working transport and cold-install guards.

# STATE — ZV-E10 reverse engineering, consolidated

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


## Offline delivery diagnosis — 24 October 2026

User requested offline reverse engineering only. [Audited findings](../uvc_yuy2_delivery_audit_20261024.md): userspace YUY2 descriptors/producer did not update the kernel probe responder. Kernel advertises stock 14,745,600-byte maximum frame, 30/25 fps, and 300,000-byte maximum payload; prototype queues 614,412 bytes with one UVC header. This is a concrete negotiation/packetization gap and strongest offline zero-frame mechanism, with Windows/on-wire behavior still unproven. The supplied team's EOF-only and 110 MB delivery claims were corrected: UVC 1.1 class spec makes EOF optional, and kernel success/cleanup paths can conceal drops/errors. Seven bounded ARM fragment cases plus constant assertions pass. Revision 2.1 owns the 180-submission runtime; revision 2.2 runtime remains unrecovered. No camera operations or new deployment. Align kernel probe and packetization next; retain revision 2.2's separate manager-lifetime correction.


## CURRENT CHECKPOINT — revision 2.2 deployed; user moving laptop

User requested saving progress before moving laptop. No further camera operations. Revision 2.2 RAM bootstrap installed/readback verified at streaming base `0x0ea6d000`; first activation enumerated 640×480 YUY2/10 fps, but FFmpeg timed out after 25 seconds with zero bytes. Stop/restart test was requested but NOT confirmed performed. Runtime/application logs not yet recovered; camera logging may remain active at `/log/yuy2_640_v22/app-sequential.log`. Last confirmed camera mode: USB Streaming first activation. No host sessions running. Preserve logs and verify actual camera state on resume; reboot clears RAM patch. Do not reinstall over loaded hooks. [Exact live checkpoint](../uvc_yuy2_patch_v22.md). Local `outputs/yuy2-640-v22/deployment/deployment-state.json` records current evidence. Menu check passed with normal logging and USB unplugged; no log deletion/firmware restoration performed. Earlier pending-install notes below are historical.


Menu investigation update: user completed MENU/VIDEO and streaming on/off successfully with USB disconnected and debugging enabled. Fourteen run artifacts hash verified; 45,839 application records decode cleanly. Capture stopped and logging restored to normal error level; awaiting repeat MENU/VIDEO check with USB unplugged. No YUY2 module installed, no firmware changes, no permanent menu fix claimed. Streaming library loaded at `0x0ea6d000`; revision 2.2 loader is being verified for this map while waiting.


Current blocker: inconsistent MENU/VIDEO-tab failure reported after the reboot to clear revision 2.1. [Menu investigation](../uvc_menu_crash_20261024.md). Fresh-boot maps confirm no YUY2 or streaming library loaded. Revision 2.2 is built/offline-verified but NOT installed. Initial logs/hash snapshots are preserved; application debug capture is active for reproduction. No storage-full error found and no logs deleted. Do not describe menu crash or host-frame delivery as fixed.


Revision 2.2 restart correction is built: [candidate report](../uvc_yuy2_patch_v22.md), source `research/firmware/yuy2_transport_v22/`. It detaches stopped managers while retaining one module-lifetime source, and requires driver completion before pixel reuse. All 42 ARM + four bootstrap cases pass; hardware installation/test pending. Original zero-frame delivery is not claimed fixed. A reboot command was sent to clear revision 2.1; verify old-module absence before guarded installation.


Latest repeat-activation finding: standby/no USB enumeration is now traced to three revision 2.1 connect rejections with error `0x21` (decimal 33): new VideoEsManager differs from the old manager retained with a DMA-pinned source. Service access still works. Nine new snapshots were hash verified; no reboot or further patch was performed. See the revision 2.1 live report's repeat-activation section. The initial zero-frame delivery problem remains separate and unresolved.


## Latest verified result — revision 2.1, 24 October 2026

[Live report](../uvc_yuy2_patch_v21.md): revision 2.1 installed in RAM and module activated. Windows/FFmpeg enumerate 640×480 YUY2/10 fps; ten-frame capture timed out after 25 seconds with zero bytes. Source unit `0x276` allocated exclusively (physical `0x15b00000`, 3,276,800 bytes), at least 180 submissions accepted by API, no host-frame proof and no PROBE/COMMIT runtime markers. Later readiness failures left source pinned; do not hot-swap or free it. User returned to service mode; 44 files / 7,655,944 bytes recovered and hash verified, debug capture stopped. The installer wrote RAM only; after streaming the common-library file read as prior 1080 candidate MD5 `bd32c223e60e363d900c7ac8be06641c` (eight descriptor bytes), despite stock hash after arming. RTOS/streaming hashes remained unchanged. File transition/persistence remains unresolved; see live report. Inspect original startup completion/host control and gadget DMA delivery next. Source-only recipe: `research/firmware/yuy2_transport_v21/`; 35 ARM + four bootstrap cases pass. Historical entries below retain earlier states.


**Self-contained.** Everything an agent needs to pick the thread up, on one page.
Nothing here requires opening another file; the topic docs are for depth.

Repo `D:\02_Development_And_Projects\pmca-re` · Python `.venv\Scripts\python.exe`,
**always pass `-B`** (stale bytecode bit once) · 68 tests pass, 4 skipped
(they need an SD card).

Long version by subject: [`../01`](../01-hardware.md) ·
[`../02`](../02-service-shell.md) · [`../03`](../03-binaries.md) ·
[`../04`](../04-messaging.md) · [`../05`](../05-formats.md) ·
[`../06`](../06-method.md) · [`../07`](../07-modification.md) ·
[`../08`](../08-camera-interfaces.md)

---

## Revision 2 candidate now built — 24 October 2026

The diagnostic findings below now have an offline implementation: [YUY2 transport revision 2](../uvc_yuy2_patch_v2.md). Source/build/verification recipe is `research/firmware/yuy2_transport_v2/`. It requests exclusive workspace unit `0x276` instead of audio `0x50f`, checks source/staging separation and capacity, performs source preflight before asynchronous connect, and adds bounded retries plus main-thread stop/reply recovery and DMA-aware cleanup. Thirty compiled ARM cases and four Thumb loader cases pass. The module rebuilds identically from the portable recipe. The RAM bootstrap has now been installed and read back at streaming base `0x0a663000`, with unchanged firmware hashes. Debug logging was armed, but after streaming activation Windows/FFmpeg could not find the camera; a cable-only reconnect was requested. Module activation, actual workspace availability, mode-switch ordering and host frames remain unverified. It still generates synthetic 640×480 YUY2/10 fps, not live sensor footage. Do not equate this candidate with a working webcam.

## Latest USB webcam state — 24 October 2026 recovery & verified analysis

This section supersedes older unchanged-camera and verified-1080p claims for the USB experiments. Read the [diagnostic handoff](../uvc_yuy2_diagnostics_handoff.md) for full byte-level evidence, disassembly traces, and verification commands.

- **Strict observation separation:**
  - **22 October 2026:** the RAM-only 640×480 YUY2/10 fps synthetic prototype advertised its mode to Windows/DirectShow and FFmpeg, but a separate ten-frame capture timed out after 25 seconds with zero bytes received.
  - **24 October 2026:** armed application debug logging. After the user selected USB Streaming, Windows detected no Sony USB device and FFmpeg reported the camera missing; no frame capture began. Camera controls became unresponsive, necessitating a manual power restart.
  - **Post-restart scope:** 34 files / 7,225,403 bytes matched camera MD5s. All `*-after.*` files are **post-restart snapshots** (uptime 53.57 seconds, YUY2 module unmapped), not a snapshot of the live hang state.
- **R1 established (Sony application log binary framing & complete timeline):**
  - Binary `app-sequential.log` (1,936,183 bytes) was decoded with 100.000% completeness (61,997 contiguous records, 0 slack bytes, 100% Subsystem 131 `0x0083` APP).
  - Framing: packed 16-byte header `<IHHQ` (`payload_len` uint32, `subsys_id` uint16, `area_id`/`component_id` uint16, `timestamp_us` uint64) with 0 inter-record padding and 0 word padding. Timestamp is a monotonic 64-bit microsecond boot clock derived via fixed-point multiplier `0x431bde82d7b634db` shifted right by 82 bits in `osal_ulogio.ko` `ulogio_print`.
  - Dual-phase structure: Phase 1 (offsets `0x000000`–`0x079f0e`, bytes 0–499,470, records 0–15,364) sequentially dumped the 13 circular buffers in RAM up to uptime ~5047.4s; Phase 2 (offsets `0x079f0e`–`0x1d8b1f`, records 15,365–61,997) streamed live chronological events starting at 5047.881s.
  - Baseline alignments verified: byte 504,783 (record 15,450, 5048.062s) in service mode; byte 508,944 (record 15,569, 5049.379s, growth of 4,161 bytes) exiting service mode.
  - Post-service mode capture extends **174.672 seconds** (46,428 additional records, 1,427,239 bytes) up to uptime 5224.050s, capturing the camera model transition, twin ERROR markers at 5064.721s (offsets `0x0bad34` and `0x0bad60`), and video/mute reconfigurations (`ActionSetYuvUiMute`, `YUV_RELD`) through 5219.9s before manual power interruption.
- **R2 established (Root cause of alloc_video_memory Error 4):**
  - Return code 4 is a **synthetic client error code** generated at `libInfraStreamingUsb.so` VA `0x9556` (`movs r0, #4`), triggered when DMM server response status `resp[2..3] != 0` (evaluated at VA `0x953a`).
  - Unit type `0x50f` maps to **Extent `0x58a`** in `/usr/setting/DmmConfig.bin`, with fixed size **6,144 bytes (6 KB)**, and is the dedicated USB Audio Class (UAC) PCM FIFO buffer owned exclusively by **`usbg_audio.ko` (Owner `0x2db`, VA `0x126c`)**.
  - Rejection mechanism in `dmm.ko`: `usbg_audio.ko` had already allocated extent `0x58a` during composite audio setup (`refcount != 0`), causing extent collision error **`-0x201`** at VA `0xa880` and ownership rule mismatch **`-0x6401`** at VA `0xa864`. Translated to `-1` in `resp[2..3]`.
  - Proven negatives: NOT an IPC transport failure (queue `0x0061003c` responded normally), NOT a raw RTOS kernel error, and NOT general memory pool exhaustion (pool `0x0c` has 1.8 MB available).
  - Stock comparison: `usbg_video.ko` allocates unit `0x50e` (Extent `0x589`, 1,843,200 bytes) with owner `0x2da`; stock `VideoEsManager` never calls `alloc_video_memory`, but receives completed frames from the hardware encoder over IPC route `0x0167046a` (`0x2009`).
- **R3 established (Lifecycle gaps & bounded cleanup/retry architecture):**
  - Worker thread discard: `VideoEsManager::video_thread` (VA `0x9700`) calls `set_video_data_to_driver` at VA `0x9746`, but immediately clobbers `r0` at VA `0x974a` with `ldr r0, [r4, #0x18]` (`uvc_scalar_sem`), discarding producer error returns and looping infinitely while `m_state == 2`.
  - Start notifier gate: `judge_notify_start_stop_evt` (VA `0x9578`) requires 10 consecutive frames at VA `0x95a8` before dispatching `SendEvtStreamingMain(9)` and setting `is_started = 1`; at VA `0x95d8` (`cmp r6, #1; bne #0x9614`), errors during startup (`is_started == 0`) are silently dropped.
  - StateMachine deadlock: `Ready::funcConnectCmd` (VA `0x7aa8`) stores `m_asyncReplyEndpoint` and enters `Starting`. `Starting::funcStartVideoDriverCmp` (VA `0x8800`) sends `{0x2003, 0}`, but `Starting::funcStopVideoDriverCmp` (VA `0x894d`) is an empty stub that never notifies `m_asyncReplyEndpoint`, leaving caller deadlocked in `Starting`.
  - Prototype 1-shot latch: `yuy2_640.c` latched `attempted = 1` and `init_error = 21` permanently without retry or cleanup.
  - Bounded architecture: 5-retry policy (150 ms delay, 750 ms bounded window), clean resource teardown (`cleanup_source` with `munmap` and `dealloc_unit`), semaphore-safe state transition (`uvc_status_sem` protecting `m_state = 1`), and active StateMachine error unwinding (`sendCompMsg(m_asyncReplyEndpoint, {0x2003, ERR_ALLOC_FAILED})` and transition to `Ready`).
- **R4 established (Root cause of zero-frame delivery & missing probe/commit markers):**
  - Dead ioctl stubs: `SendProbeInfo` (`0x11ea8`) and `SendCommitInfo` (`0x11ec0`) issue ioctls `0x4008f004`/`5`, which are unhandled in `usbg_video.ko` (`usbg_video_core_ioctl` VA `0x1e10` returns `-ENOTTY` / `-25` via `0x23b0: mvn r4, #0x18`). Neither is called by `libInfraStreamingUsb.so`.
  - In-kernel UVC negotiation & host control activation sequence: `core_cb_class` (VA `0x17b0`) terminates all UVC class setup requests in-kernel. `GET_*` requests are answered via `.rodata` offset `0x7a` (`dwMaxVideoFrameSize = 0x00e10000` = 14.75 MB, `dwMaxPayloadTransferSize = 300,000`). `SET_CUR(VS_PROBE_CONTROL)` reads 26 bytes but silently terminates because `wValue != 0x0200` (`0x198c`). `SET_CUR(VS_COMMIT_CONTROL)` dispatches event 7 via `proc_kevent_video` (VA `0x11df9`) to `_Z17proc_vendor_eventPv` (VA `0x11da1` via PLT `0x906c`), which handles vendor extensions. Host `SET_INTERFACE` invokes gadget callback `core_cb_start` (VA `0x10f0`), which executes `usbg_cmn_make_ep_list` (VA `0x1138`) to bind bulk IN endpoint `0x81` into `[cmn_obj + 0xb4]` and resets readiness `flag_A`/`flag_B` to 0 (VA `0x1198`/`0x119c`). This unblocks `UpdateVideoBufEvt` (which aborts with `-EBUSY` / `-16` at VA `0x0dc8` if endpoint is NULL), explaining why 0 probe/commit markers appear in application logs while streaming activation succeeds.
  - Successful 180+ frame pipeline ingestion & physical bus delivery: `UpdateVideoBufEvt` (VA `0x0d00`) copies physical buffer info (`0x0d80`), validates memory range (`0x0e54`–`0x0e60`), queries active endpoint `0x81` (`0x0db0`), copies frame via `dma330_mem_transfer_async` (`0x0f70`) using channel descriptor pre-bound during `usbg_video_core_open` (VA `0x1b10`, `0x1c40`/`0x1c64`), sleeps on `schedule_timeout` (`0x0fd4`) until DMA callback `uvc_transfer_dmac_cb` (`0x06a0`) fires, and queues deferred transfers (`0x0ad8`) to Endpoint `0x81` via `ep->ops->queue(ep, req, GFP_ATOMIC)`. Double-buffer readiness flags `flag_A`/`flag_B` are cleared exclusively by UDC completion callback `usbg_video_st_write_comp` (VA `0x248c`), proving the hardware UDC physically transmitted all 180+ frames (>110 MB) across the USB wire. If both buffers saturate, line `0x0f10: bne #0x10cc` drops incoming frames silently with return 0.
  - Host 0-byte delivery root causes: (1) UVC payload header byte 1 (BFH) is computed at VA `0x0f44` via `sub r8, r8, #0x74` (`0x8c` / `0x8d`), which has bit 1 (EOF) strictly equal to 0, while FID toggles on every frame (`0x0ed0`–`0x0edc`). Windows `usbvideo.sys` strictly requires EOF=1 on the final payload of uncompressed frames; upon seeing FID toggle without EOF, `usbvideo.sys` discards the preceding 614.4 KB buffer as truncated/corrupt on every frame boundary; and (2) in-kernel probe response advertises `dwMaxVideoFrameSize` of 14.75 MB. Because 100% of received frames are discarded by `usbvideo.sys`, DirectShow receives 0 completed samples, causing FFmpeg to time out at 25 seconds with 0 bytes (exit 124).
- **Bounded next-step test protocol:**
  - Safe staging verification: confirm `usbg_video.ko` staging unit `0x50e` (Extent `0x589`, 1.8 MB) is intact.
  - Legitimate video frame memory acquisition: acquire genuine video frame memory (dedicated frame buffer or hardware encoder output; never request audio unit `0x50f`).
  - Decoupled audio/video initialization: ensure UAC audio (`0x50f`, owner `0x2db`) and UVC video (`0x50e`, owner `0x2da`) are initialized independently without extent collision.
  - Hardware link & power-cycle verification: verify descriptor persistence in `libInfraUsbCmn.so`, clean device enumeration, and bounded host capture execution.
- **Camera after restart:** uptime reset to 53.57 seconds, service access returned, YUY2 module unmapped. Persistent hashes: RTOS `90096db2c76148f4f9db5d104e5c608c`, streaming library `19461091c07aa6900829defb0060fcd6`. Common library reverted from `bd32c223e60e363d900c7ac8be06641c` before restart to stock `31308976206a837f6f5c571992d2b499` afterward. Do not blindly replay old RAM deployment scripts.

Details: [uncompressed USB investigation](../uvc_uncompressed_usb2_feasibility.md), [diagnostic handoff](../uvc_yuy2_diagnostics_handoff.md) and [encoder deployment](../uvc_encoder_workspace_fix.md). Historical unchanged-camera observations below concern the earlier `libtestcmd.so` experiment.

## The one fact that explains most dead ends

**The service-mode filesystem carries the camera's rendering engine, its view
layer and 81 MB of resources — but not the application that uses them.**
`appFw.so`, `gui.so`, `libNVM.so`, `libSaveLoadSettings.so` and
`libInfraWebApi.so` are all named by the manifest and simply not present. The
files do not exist; this is not a permissions or mount problem.

So: no camera application in `comm`, `LMSGQ`/`LSEM` empty, `scenario.elf`
fire-and-forget, no TCP listener, and **a patched icon font cannot appear because
`gui.so` — the thing that draws labels — is not installed.** A whole-file
`md5sum` is not evidence that a string is drawn.

## Where things stand

| | status |
|---|---|
| run our own code as root | **done, proved** |
| persistent code execution at boot | blocked on a deliberate decision + the camera |
| command the RTOS subsystems | blocked on the RTOS message format |
| command the application | blocked: entry point absent, and boot mode unexplained — but the engine underneath is **resident and in use**, so this is narrower than it was |
| observe the firmware | **done** — `/proc/tmonitor` returns a live ~50 ms RTOS trace; `mask=0` means unmasked, not off |
| offline RE | **not blocked**; everything below can proceed with the camera disconnected |

## The camera is attached — verify before relying on it

`research/device/zve10_retry.py` reaches the service shell when the camera is
present, `/proc/modules` lists **47** modules, and the imaging manager is PID 157.
**It is intermittently absent** — the link has dropped mid-session more than once,
and `zve10_retry.py` reports `No devices found` / `link never came up` after six
attempts. Treat every device fact in this document as *"true at the check that
produced it"*, and re-verify before building on it.

**Camera state:** unchanged and as found. `libtestcmd.so` stock
(`f370de888ae662e7f509f2274846eac6`), mode and ownership restored, no `.orig`
left, `/tmp` scratch removed. The five persistence markers are still in place
(`/setting/_audit1`, `/system/_audit2`, `/usr/bin/_marker3`, `/usr/share/_marker4`,
`/usr/share/pmbp/_marker2`). `libIMDB.so` has **not** been touched.

**The SD card releases its dataset but not its device node.** Disk 2
(`Generic Mass-Storage`, FAT32 59 GB, drive `F:`, label `PMCA`) starts as
`OperationalStatus: Unknown` with an apparently stuck mount. Reads are fine —
831 files reachable — so dumps are still possible. The shell's `E&ject` verb takes
the disk to `IsOffline=True` / `No Media`, which is the storage layer letting go,
but the USB device stays enumerated (`Status=OK`) and the `F:`/`E:` letters remain
as phantom volume records. Non-admin cannot finish it; `fsutil volume dismount`
and `mountvol /p` both no-op silently. Closing Explorer does not help — no window
holds it. **Physical removal after the offline transition is very likely safe, but
that is inference, not a measurement**; it is confirmed only by the card
re-enumerating on the next attach.

---

## The attack path — proved, not theorised

Writable `/usr/lib` (ext2 on `nflasha15`, remountable rw, **not** wiped at boot)
→ `dlopen` → root. No exploit, no memory corruption, no race: the camera loads
its own libraries by name from a directory the service shell can write to, and
that directory survives reboot.

A 66-byte Thumb-2 payload of **raw `svc #0` syscalls only** (no PLT, no libc, no
new relocations, so the loader has nothing extra to bind) was injected into
`libtestcmd.so`'s `cmdline_show_revision`:

```asm
push {r7, lr}
sub  sp, sp, #16
movw r1, #0x742f ; movt r1, #0x706d ; str r1, [sp, #0]   "/tmp/ox\0"
movw r1, #0x6f2f ; movt r1, #0x0078 ; str r1, [sp, #4]
movw r1, #0x504f ; movt r1, #0x0a58 ; str r1, [sp, #8]   "OPX\n"
mov  r0, sp ; movw r1, #0x0241 ; mov r7, #5 ; svc #0     open(path, O_WRONLY|O_CREAT|O_TRUNC)
add  r1, sp, #8 ; mov r2, #4 ; mov r7, #4 ; svc #0       write(fd, body, 4)
mov  r0, #0 ; add sp, sp, #16 ; pop {r7, pc}              return 0, as the original did
```

66 of 10,128 bytes changed, all inside `0x1a48..0x1a8b`; length unchanged; all
25 exports still resolve. `/tmp/ox` containing `OPX` appeared, created in the
`scenario.elf` process as root. Restored and md5-verified against stock
`f370de888ae662e7f509f2274846eac6`.

Builder: `research/firmware/opx_payload.py`. Used rather than `libIMDB.so`
**precisely to avoid the one-way door** — `im.elf` does not link `libtestcmd.so`.

### The real target, and why it has not been done

Replacing `/usr/lib/libIMDB.so` would execute code at startup, on the next boot,
as root, **inside PID 157** — the process that owns 417 message queues, 134
semaphores and 310 callbacks and mounts every filesystem. That is the path to the
subsystems, and the same primitive is all that is required.

**It is a one-way door.** If the replacement is malformed, `im.elf` does not
start, the service shell never appears: **there is NO way back** (no boot up = no USB = dead / hard brick).
Modern BIONZ X cameras have no autonomous SD card unbrick bootloader. The
`crypter.elf` / `udtrbody.bin` updater door has the identical shape. Both carry
absolute permanent brick risk.

---

## Established, in the order the chain was built

1. **`scenario.elf` does not `dlopen` the plugins.** `libtestcmd.so` imports no
   `dlopen`/`dlsym`, only `osal_*`. It sends the name over the bus; the peer that
   would load the plugin is not running in service mode. So the 35 plugins had to
   be read directly.
2. **Their message ids are immediates, not data.** Sweeping `movw`/`movt` across
   all 35 gave **96 distinct values**, anchored against five
   `HDMI::PAYLOAD<MSG<id,1>>` template ids carried in mangled names — 2 of 5
   matched an immediate in exactly the right plugin.
3. **`libSysDef.so` names them.** Three exported MWF tables, self-describing.
   The object table then joins to `libObj.so` **exactly**: 25 implemented, 20
   declared-only, **zero orphans in either direction**. Two independent symbol
   lists agreeing exactly is unlikely by accident.
4. **`libIMDB.so` is the application manifest** — 174 libraries, 16 kernel
   modules, 22 paths, in boot order.
5. **The `.uxc` container round-trips.** 302/302 files, 12,082/12,082 index
   entries landing inside the file.
6. **The palette is authoritative**, proved on hardware by a colour that appears
   nowhere in Sony's palette.
7. **The engine is not dormant.** `libIMDB.so` names 174 libraries `im.elf` *may*
   load; `/proc/157/maps` shows **97** actually resident, including `libObj.so`,
   `libMWF.so`, `libSysDef.so` and two of the seven `viewUnified*` engines. What is
   absent is the application *entry point*, not the machinery. `im.elf` also holds
   `/dev/dmpgles2` open (fd 31) with `grm_gles` at refcount 2, so the DMP 2D engine
   and the VDF OSD port are reachable in a live process that is not the application
   — which makes an OSD injection a concrete option.

Details in [`REFERENCE.md`](REFERENCE.md).

## Blockers that need hardware

| # | blocker | why it needs the camera |
|---|---|---|
| 1 | `libIMDB.so` → `im.elf` persistent root | needs the device, and a decision about the one-way door |
| 2 | boot mode | `BOOTMODE=NORM`, no forcing file, no kernel flag — yet the application is not loaded. Either the reported mode is wrong or the service USB personality holds the system in the launcher. **Testing means giving up the shell.** This is the actual reason the subsystems are unreachable, and the one open question no amount of offline RE will answer. |
| 3 | `/proc/osal/uipc` write grammar | the node is read-write and the module has `__k_cmd_debug`, but the command grammar is unknown and it is a write into a kernel interface |
| 4 | host-tunnel code for `GetLensVersion` | must be determined live; read-only once found |

**`tmonitor` is no longer a blocker.** It was listed here as the cheapest untried
observation knob, and reading `/proc/tmonitor` settles it: a live ~50 ms RTOS
trace, ~650 sched and ~370 profile records per read, 60+ tasks, 15 module
prefixes, and the RTOS message primitives `osal_rcv_msg_tmo` (`0x5f0484ec`) and
`osal_wai_sem_tmo` (`0x5f049ac4`) with addresses. `mask=0` meant *nothing masked
out*, not "off". Detail in [`REFERENCE.md`](REFERENCE.md) §16a.

What it does **not** give is the LiRo kernel image: every LiRo wait channel is
absent from both `vmlinux.bin` (Linux only) and `av-cam.bin`. Finding that binary
is now a distinct open item.

### The `/dev/dmpgles2` ioctl is not a display door — settled

Its ABI is recovered: **17 commands, all `_IOC(dir, 0x82, nr, 4)`**, argument a
pointer to one `u32`, recovered by `research/firmware/sugilite_ioctl.py` and pinned
by `tests/test_sugilite_ioctl.py`. Detail in [`REFERENCE.md`](REFERENCE.md) §16b.

The load-bearing negative: **exactly one** of the 17 reaches the hardware, and it
is not a register write — `nr=15` writes the *fixed* value `0x20000001` to the
*fixed* BAR offset `0xC0`, and only when the caller passes exactly 1. The other 38
register writes in the module are in `sugilite_register_init` (21), clock
gating, and the ISR — kernel-internal.

The module also contains a complete **12-byte OSAL request/reply RPC into the
RTOS** (unsymbolised, 416 bytes, endpoints `0x008f013a` / `0x00910042` /
`0x008f0313`) — but **nothing branches to it and it has no symbol**, so no
pointer can reach it either. Unreachable from user space by any path.

So the drawing route is `libObj.so`'s exported `GRM_*` set, not the ioctl. The
remaining gap on that route is still the VDF OSD push entry point.

## Open offline, by value

1. **The RTOS message format in `av-cam.bin` (17,289,388 B, on disk).** What
   `sndcmd.elf` speaks. Highest value, needs no hardware, and gates issuing real
   commands. `sndcmd` returning RC=0 to `0x00dc0000` shows the firmware
   *accepts* messages — not that they do anything.
2. **The id→record index for `DefInh::sm_refTbl`.** Geometry is recovered
   (3,158,400 B / 800 = **3948 records exactly**, 88.2% populated, 24 field
   offsets, bimodal field count → tagged union). 6381 factor ids against 3948
   records fits an indirection rather than a direct array.
3. **`DefRsrc::scm_refTbl`** (98,778 B), indexed by `AcsrId_t`.
4. **The `0x4xxx` id family** — real, named by nothing.
5. **`ObjFaceRecorder` dispatch geometry** — the four `MSGID_*FACE*` strings are
   at `0xf03a41`–`0xf03bcc` and the pointer table is near `0x13dc660`, but the
   record layout is not established. (`0x13dc504` is a *different* table: its
   word 0 is `0x1000` and word 3 resolves to `MSGID_OPEN`.)
6. **`BK4` format** in `/setting/Backup.bin` (1,235,740 B, staged on the card).
7. **The style TLV** in `style_cmn.uxc` — 186 aligned 4-byte quads across 301
   files match a palette colour, 9,212× above chance, but the record is
   variable-length.
8. **Real member names for the class ids and property keys.** The blocker is
   named: `libJiritsuUIView.so` is not in the archive and was not in `/usr`
   either.

## What to do when the camera comes back

**In one session, in this order.**

1. **Do not touch `libIMDB.so` yet.** Collect the risk-free device state first:
   - `tmonitor` params (addr / size / mask, and whether it is writable)
   - a second `/proc/osal/uipc` capture, to diff against the stored one
   - the `0x4xxx` ids
2. Then decide on `libIMDB.so` **deliberately**, remembering that there is
   NO recovery path if boot fails (no boot up = no USB = dead).
3. Read [`../08-camera-interfaces.md`](../08-camera-interfaces.md) for the WiFi
   Direct link (`192.168.122.1`) — zero risk, and the main firmware's own
   interface. The camera runs a DHCP server there and nothing else listens.

The offline work continues regardless. Item 1 in the open-offline list is where
the time goes.

---

## Tooling

```powershell
# the five extraction tools, all run clean with no arguments
& ".venv\Scripts\python.exe" -B research\firmware\sysdef_tables.py    # MWF tables -> names
& ".venv\Scripts\python.exe" -B research\firmware\imcfg_block.py     # device table + id array
& ".venv\Scripts\python.exe" -B research\firmware\scenario_vocab.py  # flat movw/movt sweep
& ".venv\Scripts\python.exe" -B research\firmware\mwf_ids.py         # MWF category/message pairs
& ".venv\Scripts\python.exe" -B research\firmware\mwf_catalog.py     # full message vocabulary
& ".venv\Scripts\python.exe" -B research\firmware\factor_table.py    # sm_refTbl
& ".venv\Scripts\python.exe" -B research\firmware\cmd_surface.py     # av-cam.bin SDF/Exec surface
& ".venv\Scripts\python.exe" -B research\firmware\vdf_methods.py     # VDF string-resolved methods
& ".venv\Scripts\python.exe" -B research\firmware\elf_catalog.py     # 648-ELF inventory

# annotated disassembly: <elf> <symbol>
& ".venv\Scripts\python.exe" -B research\firmware\annotate.py `
    dumps\camera_2025\usr\usr\lib\libtestcmd.so testcmd_run_scenario

# the only camera link; one command per arg
& ".venv\Scripts\python.exe" research\device\zve10_retry.py "ls -l /usr/lib"

# what is really resident in im.elf; two sessions, do not merge them
& ".venv\Scripts\python.exe" -B research\device\im_runtime_manifest.py

# the live RTOS trace; writes the artefact on the spot, because the
# session log is truncated by the next command
& ".venv\Scripts\python.exe" -B research\firmware\tmonitor.py

# the /dev/dmpgles2 ioctl ABI; pure file reader, no camera needed
& ".venv\Scripts\python.exe" -B research\firmware\sugilite_ioctl.py

& ".venv\Scripts\python.exe" -m pytest -q
& ".venv\Scripts\python.exe" -B research\firmware\check_docs.py   # docs integrity
```

`annotate.py` resolves PLT stubs to symbol names, decodes literal pools to `u32`,
and names branch targets. It **requires a symbol that exists** — present in
`.dynsym`/`.symtab` with a non-zero size, or it raises `KeyError`.

Use `cpp_demangle.demangle(name)`, **not** `cxxfilt` — that shells out to a
binary which is not installed.

---

## The traps

**Every trap in this project fails silently.** Four mis-stride and mask bugs this
project returned plausible wrong answers rather than raising. The full list with
derivations is in [`../06-method.md`](../06-method.md); the ones that bite most:

| trap | consequence if wrong |
|---|---|
| `plt_map` mask | ARM P=24, U=23, B=22, W=21, L=20 **by bit position**, plus Rn=ip / Rt=pc. Do **not** mask cond, and do **not** pin the register field in one constant. Sanity check: `plt_map` on `AVBB_SCN_START_HDMI.so` must give **122** entries. |
| `plt_map` on a Thumb lib | PLT stubs are **ARM**, even in a Thumb library. |
| `.dynsym` `st_value` | bit 0 set means Thumb. ARM-mode decode of a Thumb function returns plausible nonsense, not an error. |
| capstone `op_str` | `movw r2, #0x1022` yields a register named `"r2,"` — **with a trailing comma**. |
| table strides | APICD is **36**, not 72. Stride 72 reads every *second* record, still starts in the right place and every name pointer still resolves — it just reports 58 records instead of 115 and pairs each id with the wrong name. Pinned by `tests/test_mwf_catalog.py::test_apicd_stride_is_36_not_72`. |
| vaddr vs file offset | `0x13ec720` is a **file offset**. `libObj.so`'s second PT_LOAD is vaddr `0x1365d8c` / offset `0x135dd8c`. |
| `av-cam.bin` pc-rel | the pool word and `addr` are **both** file offsets; do **not** apply the load base. `pc` is `addr + 4`, **not** `Align(PC,4)`. |
| console output | the shell wrapper truncates at 25 lines. **Never trust a count or an absence from wrapped console output** — re-read through a filter that emits one line, or read `zve10_shell.log`. |
| `dd` on this busybox | **no `conv=notrunc`.** Any `dd of=<live file>` truncates the target to the write offset. Use `cp`. |
| base64 by hand | a single mistyped character once decoded to `0000` at the *id field of the next record*. Generate chunks programmatically; hash on the camera **before** writing. |
| link is lossy at volume | a scan of `/proc/*/fd` across 263 processes floods the serial link and the **next** command's output arrives empty. Put the noisy query and the bulky query in **separate** sessions. |
| `$$` never survives | PowerShell expands it, so `/proc/$$/maps` arrives as `/proc/<pc-pid>/maps` and reports nothing. Use the literal pid. |
| shell verbs hide the `&` | the eject verb is `E&ject` — the accelerator sits **mid-word**, so matching `Eject` finds nothing and a first eject attempt silently never happens. Match `-like '*ject*'`, and hold the `Verbs()` collection rather than re-enumerating it (a second call returns a different set). |
| `zve10_shell.log` is scratch | `zve10_shell.py` opens it with mode **`"w"`**, so **every session truncates the last one**. A whole `tmonitor` trace was extracted, summarised, and then destroyed by the next three commands. Capture anything worth keeping into a tracked artefact **on the spot**, and make the capture the first command of the session. |
| a symbol name is not an identity | the trace emitted `0x60293424` as both `tty_insert_flip_string_fixed_flag` and `tty_insert_flip_string_fixed_fl`. `vmlinux.bin` has only the long one, so the short is a clipped copy. Group by address. |
| `\S+` drops names with spaces | `-profile user TC::VD_Seq S cpu:0` — a task name containing a space. Matching the name as `\S+` loses the record. Anchor on the trailing `cpu:N` instead. |
| a count is not a value check | recovering the ioctl table with the literal pool read at `addr+4` instead of `addr+8` still printed **17 commands** — the right number, all the wrong values. The pool is contiguous, so every site yields a different constant. Only comparing the recovered *set* catches it. Verified by mutation. |
| ARM PC is `addr+8` | in the ioctl's compare chain, `addr+size` reads the pool one word early and yields *instruction words* as command constants (`0x0a000055` is `mov ip,sp`). |
| ARM immediates are `imm8 ROR 2*rot` | `add r3,r3,#0xc0000004` is really `#0x11, 30`. Read the decoded operand, never capstone's printed text — the printed form is the effective value and is fine, but a hand-rolled regex on the text is not. |
| GCC refines one register across compares | `cmp r1,r3; beq E; add r3,r3,#K; cmp r1,r3; beq E2`. Clearing `r3` after the first `cmp` recovers 7 of 17 commands. Symbolic execution with a `seen` set shared across paths recovers 1. A single forward scan gets all 17. |
| no symbol means no pointer | the module's 12-byte RTOS RPC has no symbol *and* no branch to it. Either fact alone would be weak; together they make it unreachable. |
| never quote the docs fingerprint in full | `check_docs.py` scans the docs for 32-hex-digit strings and hashes that set, so writing the full fingerprint into a doc **adds it to its own input** and changes it. Quote it truncated (`070a0f50…`), as `09-provenance.md` does. Writing it in full moved the fingerprint to `4bf7d909…`. |

The `E&ject`, log-truncation and `\S+` rows are the same family: the operation
appears to run and reports nothing, or reports a plausible result — which is
indistinguishable from it not having worked. Pinned by
`tests/test_tmonitor.py` and `tests/test_im_manifest.py`. The latter intercepts
the tool's `run` and asserts on the commands it really issues, because a text
search for `$$` in the source finds it in the comment that documents the trap and
fails for the wrong reason.

The link-flood and `$$` rows are what made the runtime manifest return an empty
list three times before it worked, each time as a *plausible empty result* rather
than an error.

## House rules that were violated before they were learned

- **A claim about a byte pattern needs a computed chance rate.** 14,720 raw
  `0c 40` hits across a 27 MB bitmap atlas, zero of them in a structural word,
  was published as "14,721 references" before a null model existed.
- **A claim about a "constant" needs a cardinality check.** A property reported
  as 100% on a style-index test turned out to have **1 distinct value** across
  10,500 occurrences — a type tag.
- **Structural checks do not always discriminate.** Two of them (offsets inside
  the file; offsets non-decreasing) **both passed on a wrong `data_start`**.
  They constrain the offset array, not where the array ends. The check that
  discriminates is content: record 0 must yield a name that exists on disk.
- **Negative results are results.** Record them, with the null model. Three
  conclusions in this project were wrong in exactly the same way, and the
  correction is procedural.
- **Unquantified side effects get labelled, not omitted.** Same-length edits are
  preferred because they cannot move an offset or change an entry count.
- **A function that silently drops its evidence is worse than the bug it hides.**
  `drain()` returned `None`; three consecutive "transfer failures" were that one
  bug.

## Restore points

- SD card in the PC (`PMCA`, was `F:`) holds `F:\RE_DUMP\audit\Backup.bin`,
  md5 `bdc524e5cdcf3b290aed1c9271ccf921`.
- **`Backup.bak` does not exist** in the dumps or on the card, despite a note
  claiming it is a genuine earlier snapshot. Do not rely on it.
- `udtrbody.bin` is in three local copies plus the card.
- Stock `libtestcmd.so` md5 `f370de888ae662e7f509f2274846eac6`.
- `dumps/camera_2025/usr/usr/lib/libObj.so` is an **81,920-byte truncated
  decoy** that does not parse. The real one is `dumps/engine/libObj.so` (21 MB).
