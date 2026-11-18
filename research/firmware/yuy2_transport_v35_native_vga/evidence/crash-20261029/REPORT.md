# Revision 3.5 menu/streaming crash log collection — 29 October 2026

User reports crashes opening MENU or using USB Streaming. Retrieved surviving diagnostics in one authenticated service session; no flash, rollback, reboot, streaming test or logger reconfiguration was sent.

## Preserved evidence

- Fourteen snapshot files, 6,210,795 bytes total; every camera snapshot MD5 matches the downloaded bytes. SHA256 values in download-verification.json. Local originals: C:/Users/qn061/Documents/Codex/2026-10-22/chec/outputs/vga-v35/crash-20261029-01/.
- AccessLog.dat and AccessLog.bak: 2,097,220 bytes each, identical MD5 05b6579f523b8f7e3ac55e311c93cc2c. Changed from the earlier 3.4 snapshots; binary semantics not decoded. Printable-string inspection found no explicit crash/fault record, which does not exclude one in binary fields.
- ThreadMonitor.bin: empty. kikilog.dat: 1,957,888 bytes, predominantly non-printable; no useful text crash trace identified. Do not call this file decoded or empty.
- Current dmesg, process maps/status, uptime, boot ID, mounts, memory, installed hashes and storage saved. /proc/last_kmsg, /sys/fs/pstore and /var/log were absent. Current dmesg contains no identified panic/oops/fault address; it is not a surviving previous-boot console.

## Findings and limits

- Installed wrapper MD5 c16af3a036529b89d23fa4ccfd059ec3 and module MD5 e6b9fa6947a21e5a6a1603e070a1d00f still match revision 3.5.
- Initial observed uptime 176.28 seconds; snapshot 254.73 seconds. Short uptime is compatible with the reported restart but does not independently establish which user action caused it.
- No streaming/probe libraries were mapped in im.elf at collection. This is the recovered process state, not proof they were absent before a crash.
- runtime.log is 83 bytes: `YUY2 LOAD ...` and `YUY2 INSTALLED_V25 ...` only. INSTALLED_V25 is a legacy marker, not evidence that revision 2.5 was installed. No vga.log was present in the directory inventory. No surviving acquisition, SDF, frame or shutdown stages were recorded. RAM telemetry may have been lost on reboot; absence of persisted stages does not prove they never ran.
- Available space: /usr 11,219,968 bytes; /log 524,058,624 bytes; /tmp 6,619,136 bytes. The helper's write/readback check passed. Storage exhaustion is not present at collection; these values do not reconstruct precrash capacity.
- Menu/streaming crash cause remains undetermined. No fault PC, backtrace or proof attributing it to DMM/SDF/USB was obtained. Do not keep repeating streaming trials based on this log pull alone.

## Collection hygiene

Initial snapshot attempt stopped when a df applet was unavailable, before downloads. Retried using the existing space-check helper and successfully collected all files. Result 003 is authoritative. All generated crash-* snapshots (plus their manifest) were camera-MD5 rechecked against the verified local archive and individually removed; original AccessLog files, ThreadMonitor.bin, /tmp/kikilog.dat, runtime.log, system files/fonts/tools were preserved. Service session closed: job005 WORKBENCH_CLOSED / Done. Camera remains revision 3.5; no restart command sent.
