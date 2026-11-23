# Revision3.4: zero frames and crash on streaming shutdown

29 October 2026. User reported camera crashed while turning USB Streaming OFF after the bounded FFmpeg attempt returned0frames. Surviving diagnostics were collected in service mode without another streaming attempt, reboot or firmware write. Installed3.4 hashes still match. Initial recovery uptime55.89s; later snapshot102.31s. Low boot age, cold maps and user report are consistent with a restart, but no pre-crash boot ID/continuous uptime sample establishes its exact timing. Do not exonerate the patch.

## Frame acquisition

Initialization, destination allocation/Share/Open/map pass. First rejected SSYC metadata candidate receives the known non-owning refusal and is skipped. Next metadata Share/Open succeeds. Its attached pixel type0x295/handle0x67fc Share receives native-517/status-5 and is logged PIXEL_SHARE_STALE. The team cleanup branch continues scanning: NO_SOURCE_SSYC followed by another SSYC acquisition shows progress beyond the old3.3 stop.

The later metadata handle0x1a71 is Shared/Open/mapped, but its pixel handle0x0ffc Share returns SDKrc0, command0x8002, translated/native status-1, matching request handle/queue/type and zero addresses. Existing kernel analysis identifies native-1 as unshareable unit state or saturated references; which occurred here is not recorded. The pixel path handles stale-serial rejection, but not this explicit non-owning-1, so it quarantines. Reply details in .local/logs/pixel-share-replies.json. All handles/physical/process addresses are historical session diagnostics, never replay.

No SOURCE, ALLOCATE_INPUT_SSYC, RESIZE or COMPLETE marker, and no SSYC output dumps. No SDF resize request or frame was produced. data_transfer acceptance therefore did not receive an end-to-end SDF test. Repeated pool scanning still does not establish a current completed metadata/pixel pair. This report does not propose another narrow refusal-only flash.

## Shutdown crash

Runtime stops at SOURCE_RETAINED and STOP_CLEANUP, with one VGA STOP_REQUESTED. The usual FINISH_CLEANUP entry is absent. That bounds the last persisted diagnostic phase; it does not identify the faulting instruction, prove a deadlock, or prove the stop hook caused the reset. No resize was in progress according to saved markers, but private channels, reserved destination resources and potentially owned metadata remained relevant side effects. Metadata remains conservatively retained after unknown pixel outcomes because global fault prevents drop(). Their interaction with stock mode teardown needs investigation.

Current-boot kernel ring buffer has no decoded matching panic/Oops/watchdog fault record; /proc/last_kmsg and the two checked pstore console paths were absent. System AccessLog.dat and AccessLog.bak were copied to bounded diagnostic snapshots and retrieved:2097220B each, identicalMD50b8afdeacb08a53100021d678da8c86f. Their binary format has not been decoded; no root-cause PC was recovered. ThreadMonitor.bin is0B. Do not treat those access logs as proven crash dumps or assume they are from this incident. No process-memory SSYC extraction after the apparent reset, which cleared old RAM state.

## Preservation

Ten data artifacts matched camera MD5s; host SHA256s in .local/logs/archive-verification.json. AccessLog binaries remain LOCAL workspace evidence, not tracked source publication. Original /log/AccessLog.dat,/log/AccessLog.bak,/log/ThreadMonitor.bin untouched. Two captured runtime logs2035B plus three diagnostic system-log copies4194440B were individually rechecked and cleared (4196475B total); system/tmp/fonts/tools preserved. No new sequential application debug logging, no new deployment or reboot. Service closed(job019). Camera remains3.4; further streaming tests were not run.

Next offline work must treat two distinct questions: reliable paired frame acquisition and shutdown behavior with reserved/quarantined resources. Need a real freshness/lifetime contract and a teardown proof including native failure paths; mocked frame success and no-NEON audit do not establish either.
