# Revision3.3: real metadata recovered; stale attached pixels

28October2026. Host FFmpeg timed out with0frames. User returned to service and subsequently requested a slower subsystem-focused offline investigation, pausing further flashes/tests. No new installation/reboot/stream cycle occurred in collection; camera remains3.3.

## Observed progress and current failure

Initialization and VGA destination Share/Open/map succeed. SOURCE_SHARE_DECLINED shows3.3 skipped the first exact no-reference rejection as designed. Next SSYC metadata candidate0x8cc9/type0xe0b00 successfully Shares, Opens and maps4096B at0x1196e700. Its image attachment identifies type0x295/handle0x7f24. Pixel Share fails with SDKrc0, reply command0x8002, translated status-5 and native-517(0xfdfb). The original kernel check at0x8894..0x88a0 rejects a slot serial mismatch with this native status. This establishes an invalid/stale pixel handle at Share time. It does not establish whether metadata was historical already or the image was released/replaced during acquisition. No SDF resize request or frame produced. Transient values above are diagnostics and must never be replayed.

## Actual retained SSYC recovered without another test

Read-only /proc/PID/mem extraction at the loaded module's ELF-derived source_snapshot address recovered the4096B copy already retained by the quarantined worker. A fresh live-map base guard preceded the read;8192B page readback hash matched camera. Extracted source-ssyc-retained.bin SHA2569c60c7088da03631af4cd06fbd8f9d444d084e9104ead87cb0147ef76ac45f9c. No source pixel memory was read. Process-address provenance is session-only.

Compiled verified C SDS decoder agrees with all31parsed ImageSizeInfo fields.12ETRY categories present:0,1,2,6,4,5,18,12,16,10,22,23. Category0 says image_attach1,type0x295,handle0x7f24,offset0; record/canvas/valid/target1920x1080; yc_compress1,data_site0,data_transfer1,data_placement1,data_content2,data_scan1,strip_width64,yc_bit_depth0,aspect2. Exact fields/category offsets are in .local/logs/source-ssyc-decoded.json. Unknown category meanings must be traced rather than inferred from their values.

An additional latent blocker is now visible: vga_source_contract rejects nonzero data_transfer, while this actual descriptor has1. Even a successfully pinned image from this descriptor would not satisfy the current contract. Do not flip the flag or delete the check without proving its enum and hardware implications. yc_bit_depth0 has no new live precision interpretation; geometry and compression metadata do not establish a coherent usable pixel frame.

## Why the test loop was insufficient

Host transport success with2.4p synthetic bars does not establish the live source handoff. The3.0initialization defect and3.2known Share refusal were isolated and improved, but memory-pool scanning is still being used as a stand-in for the real completed-frame delivery protocol. Metadata lifetime alone does not prove its referenced image remains valid. Offline mocks exercised chosen outcomes; they did not prove a live metadata/pixel pair, frame generation, hardware completion or safe release. Further narrow patches would encounter the now-known flag mismatch without solving that protocol.

## Preservation and pause

Eight camera-downloaded data artifacts match MD5s; SHA256s in .local/logs/archive-verification.json. Real SSYC and8192B readback remain local ignored binary evidence; do not distribute unrelated process-page bytes. Two runtime logs1673B plus8192B page scratch were rechecked, individually removed and absence verified (9865B). System/tmp/fonts/tools preserved. No sequential app capture; normal error filters. Service closed after collection. Further hardware testing/flashing paused; offline subsystem investigation continues. See docs/archive/sessions/YC_SUBSYSTEM_RESEARCH_PLAN.md.
