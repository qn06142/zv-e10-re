# Revision 3.5 OBS live-scene output, then crash — 29 October 2026

User reports a few frames in OBS followed by a camera crash, and supplied a screenshot with recognizable scene detail but severe magenta/green color and vertical stripe artifacts. The supplied screenshot is preserved locally as user-obs-frame.png (SHA256 9c625d68ad30480b04e01051417b003a75a6b3aacead828c61ff0371e5dabc6e). This is user-provided host evidence, not a raw frame capture made in this collection. It supports scene-bearing output, not correct packing/color, stability or frame rate.

## Collection

One authenticated service session retrieved 18 camera snapshot files, 6,280,735 bytes total. All match the camera snapshot MD5 manifest; SHA256 values are in download-verification.json. Local archive: C:/Users/qn061/Documents/Codex/2026-10-22/chec/outputs/vga-v35/crash-20261029-02/. No firmware write, rollback, reboot, new streaming trial or logger configuration was performed.

Installed 3.5 wrapper/module hashes remain c16af3a036529b89d23fa4ccfd059ec3 / e6b9fa6947a21e5a6a1603e070a1d00f. Initial uptime was 74.59s. Boot ID differs from the preceding crash-20261029-01 collection, confirming a restart between collections, without establishing the exact fault trigger or whether recovery was manual. No streaming/probe modules remained mapped in recovered im.elf.

## Surviving pipeline evidence

- runtime.log: 1,339 bytes; source allocation succeeded, staging physical address 0x15b00000. First three logged submissions are 614,400-byte payloads. Repeated RAW_SOURCE_ERROR 1 entries coexist with submissions; these markers alone do not establish fatal transport errors or how many OBS frames were displayed.
- vga.log: 42,000 bytes, 1,013 lines. Sixteen SOURCE and RESIZE_READY entries; fifteen RESIZE_ENTER, fifteen RESIZE_RETURN and fifteen COMPLETE entries. The fifteen returns contain three zero words; COMPLETE counters run 1..15 with byte count 0x96000 (614,400). These are logged worker outputs, not an independent count of host-received frames or proof of all response fields.
- Source geometry logged as 0x07800438 (1920x1080). Source pixel span size 0x1fa400 (2,073,600 bytes). Stale/unshareable pixel and metadata candidates continue to appear in the pool scan before usable candidates.
- Last persisted lines acquire source SDS 0x1f31 and pixel 0x9893, then `VGA RESIZE_READY 000016c0 0000159e 0000000f`. There is no subsequent persisted RESIZE_ENTER/RETURN or COMPLETE 16. There are no STOP_REQUESTED, STOP_CLEANUP or FINISH_CLEANUP markers. Buffered trace boundaries mean the final line is not necessarily the instruction at fault; do not claim the sixteenth SDF operation crashed solely from this tail.
- input-ssyc.bin and destination-ssyc.bin: 4,096 bytes each, archived and hash-verified. These descriptors can support later format/ownership analysis; no pixel frame was downloaded during this collection.
- System AccessLog.dat/.bak, ThreadMonitor.bin, kikilog.dat and uipc_stat_kernel.txt recovered along with dmesg, process maps/status, boot ID, uptime, memory, mounts and storage. Binary system logs remain undecoded. last_kmsg and pstore paths are absent. No fault PC or definitive backtrace was recovered by this collection.

## Storage and end state

Storage helper reports /usr 11,219,968B, /log 524,058,624B and /tmp 6,619,136B available; write/readback check passed. Storage exhaustion is not present at collection and does not explain the current evidence by itself.

Own generated crash-* snapshot copies and manifest were individually camera-hash rechecked and removed after verified download. Original runtime/vga logs, input/destination descriptors, system logs and /tmp contents were preserved. Service closed normally: job004 WORKBENCH_CLOSED / Done. Camera remains revision 3.5; no reboot command was sent.

This supersedes the previous zero-progress capture checkpoint: native source/resize/output now has runtime evidence and the user observed scene-bearing output. Correct pixel format, stable streaming, source event/ownership safety and the crash cause remain unresolved. Do not claim a fully working webcam patch or measured throughput.
