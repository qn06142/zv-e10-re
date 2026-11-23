# Revision 3.0 OBS failure: logs recovered — 28 October 2026

User tested OBS and reported no image. Camera was available in mass-storage mode; service log collection completed without streaming, rebooting, flashing or changing application debug filters.

## Observed failure

`vga.log` (179 bytes) contains `GUARD_FAILED`, `QUARANTINED` with zero source/destination handles, and two `STOP_REQUESTED` entries. No `QUEUES`, `SHARE`, `RESIZE` or `COMPLETE` marker appears. Neither input-ssyc.bin nor destination-ssyc.bin exists. runtime.log (555 bytes) shows USB output allocation success, source-ready/rebound, repeated RAW_SOURCE_ERROR, and stop/finish cleanup.

The failure is in `load_calls()` initialization, before source discovery or a resize request. GUARD_FAILED currently conflates dlopen/dlsym failure, SDK prologue mismatch, maps read/parse failure, private libObj address/range/prologue mismatch, and zero queue IDs after constructors. The existing log does not identify which branch failed; absence of QUEUES means queue validation never passed, not proof that constructors were never called. The worker quarantines and produces no image. This is not evidence of an OBS format issue or rejected pixel conversion.

Installed module, streaming wrapper, libObj, libBizFw and pthread MD5s exactly match deployment records. A correct on-disk hash does not establish relocated in-memory prologue equality or successful symbol resolution. Next investigation: audit guard generation against relocations and maps parsing, then add a distinct bounded initialization-failure reason for each return path; preserve the guards rather than bypassing them. No fix has been installed.

## Evidence and cleanup

Local directory: .local/outputs/vga-v30/logpull-20261028/. Includes raw runtime/vga logs, process maps, DMM listing, memory, uptime, kernel ring buffer, installed hashes and archive-verification.json. All nine downloaded artifacts match camera MD5s; host SHA256s recorded. Retained kernel ring buffer contains no matching panic/Oops/OOM record; this does not rule out previous resets. Inventory uptime was 471.02 seconds; no relationship to the earlier installation boot is assumed.

The two known runtime capture logs (734 bytes total) were rechecked against archived MD5s, individually removed, and absence verified. No broad /log or /tmp deletion. Remaining installation helpers and state snapshots preserved. Service session closed. Revision 3.0 remains installed and unproven for live images; proven 2.4p bars remains the transport control. One-session-per-cold-boot restriction remains; collection does not authorize another streaming cycle or deployment.
