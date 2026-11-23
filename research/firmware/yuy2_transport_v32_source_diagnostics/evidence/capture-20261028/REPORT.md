# Revision 3.2 first camera trial — 28 October 2026

FFmpeg timed out after a25s bound (27.03s host elapsed),0bytes/frames. User returned camera to MSC. Installed module/wrapper MD5s match3.2; service uptime247.22s after activation reboot. No restart reported or evidenced by these uptime snapshots.

## Exact acquisition failure

The initialization fix still works: MAPS_READ0xbf66=48998bytes, QUEUES0035611a/0035611f/00356120. Destination type0x220 allocation and contract setup complete; Share succeeds for destination handle0x1769, Open succeeds at physical0x28f4b800 with0xc8000bytes and LEASE_READY. These addresses/handles are transient diagnostic values, never replay.

A source listing/signature candidate has handle0x1755, type0xe0b00, physical0x11971700,4096bytes. SSYC signature/version peek is a hint only. SHARE_FAILED then reports SDK rc0 and reply word0=0xffff8002. Reconstructed24-byte little-endian reply words:

ffff8002 611a1755 ffff0000 000e0b00 00000000 00000000

Command0x8002 is Share completion, signed16status at+2 is-1, handle+4=0x1755, queue-low+6=0x611a matches the private DMM channel. SDK transport returned0 but the DMM service explicitly rejected sharing the candidate. This is not a source Open, address-site or mmap failure: no source Open was attempted. The meaning of remaining fields and the service's rejection reason require tracing, not guesses. The candidate is not yet a verified video descriptor.

Worker quarantines with candidate metadata handle0x1755, pixel handle0 and destination SDS0x1770. No SOURCE/SOURCE_FLAGS/RESIZE/COMPLETE or SSYC dump; no source pixel acquired and no resize request. Destination allocation success does not prove live pixel packing or source eligibility.3.2 is diagnostic progress, not a working sensor webcam.

## Next investigation

Trace the actual DMM command2 negative-completion paths, including type/relationship/owner checks and missing/stale handle semantics. Source can change between signature peek and Share, but this run does not establish a race as the cause. Do not map an unowned source or weaken ownership checks. Prove rejection has no allocation side effect before clearing potential-share state/retrying candidates. Distinguish explicitly received negative replies from transport errors/timeouts, where ownership remains ambiguous. Any next patch must preserve existing guards and quarantine unknown outcomes.

## Preservation

Seven data artifacts (runtime/vga logs, maps, DMM units, memory, uptime and kernel ring buffer) matched camera MD5s; host SHA256s in .local/logs/archive-verification.json. Parsed reply in .local/logs/source-share-reply.json. No matching panic/Oops/OOM in retained ring buffer, not a complete crash history. Runtime506B and VGA706B logs were rechecked against archived MD5s, individually cleared and absence verified (1212B total). No broad/log or/tmp deletion; system/helpers/state snapshots preserved. Normal error filters, no sequential app debug capture. Service session closed. No patch/reboot during collection;3.2 remains installed and one-session-per-cold-boot rule applies.
