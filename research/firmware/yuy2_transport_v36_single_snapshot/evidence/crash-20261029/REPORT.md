# Revision 3.6 repeated crashes — failed snapshot trial, 29 October 2026

User's clarified sequence: USB Streaming initially entered successfully, OBS received no frame, camera crashed; subsequent attempts crashed at the menu. Do not describe initial mode entry as successful image delivery. Revision 3.6 has NOT demonstrated stability or a working snapshot and must not be described as a crash fix.

## Retrieved evidence

One authenticated service session preserved 16 files / 6,232,824 bytes, all camera snapshot MD5 verified, with SHA256 values in download-verification.json. Local archive outputs/vga-v36/crash-20261029-01/. Runtime 269B, VGA log5635B, system AccessLog.dat/.bak, ThreadMonitor, kikilog and uipc stats, dmesg, maps/status, uptime/boot ID, memory, mounts, hashes and storage retained. Module c2e06b5a7a9f1361c4fb2a087d5e8fe2 and wrapper886445056d2eba99ef62df3a9def5e0f still match3.6. Initial recovered uptime51.77s; no streaming/probe maps remained in recovered im.elf. This does not reconstruct precrash mappings or identify which crash a log belongs to.

## What survived

Runtime records LOAD, legacy INSTALLED_V25, successful USB source allocation/binding, and RAW_SOURCE_ERROR1 (pending source). No RAW_BYTES or SUBMITTED markers. No native-vga-snapshot.bin, input-ssyc.bin or destination-ssyc.bin in directory inventory.

VGA log has destination allocation and Share/Open, then repeated candidate scans:13SSYC hints,7pixel Share refusals,4metadata Share refusals,6NO_SOURCE_SSYC. There are zero persisted SOURCE, RESIZE_ENTER, RESIZE_RETURN, COMPLETE, SNAPSHOT_READY or SNAPSHOT_DUMP markers. Last persisted sequence is rejected pixel Share followed by NO_SOURCE_SSYC. No shutdown/stop markers. Buffering and restart can lose records: this is not proof that the next native call never started or that the final persisted operation caused the crash.

The single-snapshot cap did not make the trial stable; the crash need not depend on completing fifteen resizes or repeated immutable replay. Source scanning/acquisition and earlier activation/menu paths remain unresolved. This does not prove DMM itself caused a fault. The current hypothesis needs a genuine frame-event contract and/or isolated activation/source investigation, not another repeated blind image trial.

No identified fault PC/backtrace in current dmesg; last_kmsg/pstore absent. Binary AccessLog/kikilog semantics remain undecoded. Storage is healthy at collection: /usr11219968B,/log524058624B,/tmp6619136B available; helper write/readback passed. Clearing already-small logs is not an established fix.

## End state

Own crash-* snapshot copies and manifest camera-hash rechecked and individually cleared after download; original runtime/vga/system logs and /tmp preserved. Service closed job004 WORKBENCH_CLOSED/Done. No flash, rollback, reboot, IPC experiment or new streaming test was sent. Camera remains3.6 with user-reported instability. Recommend restoring proven2.4p before further hardware trials; no rollback was authorized/performed by this collection. Default3.6 rollback restores3.5, which also crashed; the separately retained2.4p rescue is the stable-baseline option.
