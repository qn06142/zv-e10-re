# Revision 3.1 first camera trial — 28 October 2026

FFmpeg requested five640x480/10fps advertised YUY2 payloads, but timed out with zero bytes. User returned camera to MSC without reporting a restart. Installed module/wrapper hashes match3.1. Service uptime235.54s, greater than post-install uptime; no reset is evidenced between these snapshots.

## Progress confirmed on camera

VGA MAPS_READ 0000bf61:48,993bytes read during worker initialization. VGA QUEUES 0035611a 0035611f 00356120 confirms the guarded initialization and queue checks now pass. The original generic GUARD_FAILED no longer occurs. ALLOCATE 00000220 00000280 000001e0 records requested VGA image allocation; subsequent SHARE of destination image handle18f4 and later source search indicate destination setup/contract validation completed.

## Current blocker

Next entry is SHARE 000018db 000e0b00, followed by QUARANTINED 000018db 00000000 000018ef. These are transient session handles, never replay. A read-only SSYC signature peek selected a candidate metadata unit; the attempt to Share/Open/map that candidate failed before its image attachment was decoded and pinned. take() emits SHARE before the SDK call and can fail in Share status, Open status, returned address-site validation, physical span/overlap checks, open(/dev/stream), or mmap. Existing markers do not identify which branch. It is NOT established that Share itself failed or that this candidate is a correct video descriptor. The candidate may disappear between listing/peek and acquisition; no recorded reply proves that theory.

No SOURCE/SOURCE_FLAGS/ALLOCATE_INPUT_SSYC/RESIZE/COMPLETE markers or input/destination SSYC dumps. SDF resize was not requested; no pixel-packing conclusion is possible. QUARANTINED zero pixel handle does not prove no metadata reference was acquired: potential ownership is recorded before SDK calls and unresolved resources intentionally retained until reboot.

Next offline change should add bounded stage/return/status/address-site/map-failure evidence to acquisition; recover exact DMM negative-reply semantics before changing quarantine behavior or retrying a vanishing candidate. Do not bypass guards, guess handles, or release potentially owned references. This trial proves initialization progressed but does not establish a working native webcam.

## Preservation

.local/logs/ contains runtime.log506B, vga.log328B, process maps, DMM listing, memory, uptime, kernel ring buffer and camera-MD5 manifest; all seven data artifacts matched camera MD5s and host SHA256s are in archive-verification.json. Post-stop DMM listing lacks the transient18db/18ef/18f4 handles; that does not reveal which acquisition step failed earlier. No matching kernel panic/Oops/OOM in retained ring buffer, not a complete crash history.

The two runtime capture logs834B were rechecked against archived camera hashes, individually removed, and absence verified. No broad /log or /tmp cleanup, no new patch or reboot. Service session closed after collection.3.1 remains installed, one streaming session per cold boot; do not retest this session without a fresh boot. Normal error filters remain; no sequential application debug capture enabled.
