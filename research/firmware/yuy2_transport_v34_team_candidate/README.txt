DEPLOYMENT UPDATE 29 October 2026: Installed and reboot-verified by explicit user request. Exact readbacks/postboot hashes match. Recovery preserved, /usr read-only, service closed. No3.4 frame test yet. See evidence/install-20261029/deployment-summary.json. Build-time NOT_INSTALLED/no-camera statements below are historical.

# ZV-E10 revision 3.4 flashing package

Built offline 29 October 2026 from the team's revised3.3 source. NOT INSTALLED. No camera access, reboot, mode change or firmware write occurred. The recorded installed baseline remains original3.3 (module87ddc16bd8e0774926e5eb6d16165d20, wrapper909c4ffadc9e5972b25101529d5f8773). The team's rebuilt file named3.3 is a different candidate, not that baseline.

## Files

- yuy2_640_v34vga.so:33336bytes, MD5ac565b4060a7062745d3bd22037d5410.
- libInfraStreamingUsb.persistent.so:72796bytes, MD5ca3cbbc5947caf3373ebe451343fb926; install as /usr/lib/libInfraStreamingUsb.so.
- preflight.sh / install.sh / rollback.sh: guarded service-mode scripts.
- space-check.elf: existing storage and exclusive/tmp readback helper.
- manifest.json and evidence/: identities and offline verification.

These two libraries are a matched pair: wrapper DT_NEEDED names yuy2_640_v34vga.so. SHA256s are in manifest.json. Local package contains a patched proprietary Sony wrapper; do not publish package binaries in Git. Source/recipes/hash/text evidence may be tracked.

## Included changes

The team logic is preserved: source metadata accepts data_transfer0/1; a correlated native-517 pixel Share rejection clears the unacquired pixel lease and closes/frees only the acquired metadata reference before continuing candidate search. Other uncertain outcomes remain quarantined. Producer name/soname/dependency, log directory and artifacts now use distinct3.4 names.

Acquisition STILL SCANS /proc/udm/dmm_units. Event-driven frame reception and Category2 completion validation are not implemented. This package makes no claim that data_transfer means DMA completion or that raw native output is YUY2. It is an experimental candidate, not a demonstrated live webcam.

## Installation scope and recovery

Hardware testing remains paused until the user explicitly resumes it. Do not run this package as part of an offline review. When authorized, stage files in /log/yuy2_640_v34vga/ (create the directory first), preserve/recheck/clear known test logs, and use a fresh power-on with USB Streaming unopened. preflight.sh requires exact original installed3.3 module/wrapper, matching SDK/common/RTOS/DmmConfig/DMM/USB kernel, cold process maps, existing stable recovery, adequate storage and a successful/tmp readback. It refuses altered baselines, loaded streaming modules, overlays and existing3.4 recovery/staging remnants.

Run /bin/busybox sh /log/yuy2_640_v34vga/install.sh only after those conditions hold. Installer re-runs preflight; saves original3.3 wrapper plus its inode and a stable2.4p wrapper copy under /usr/share/yuy2-recovery-v34vga/; installs/validates the producer before switching the wrapper; restores/usr read-only. Read back both files and recovery artifacts against the host manifest, reboot for activation, then verify persistence/cold maps/read-only state before any streaming test.

rollback.sh restores EXACT ORIGINAL3.3, not directly2.4p. It preserves the3.3 producer and older recovery chain. It requires cold maps and a known current wrapper. Failed installation attempts restore the previous wrapper; an unused new producer file can remain for forensic recovery. Do not bypass preflight to repeat an interrupted installation.

The scripts do not reboot or capture automatically. One streaming session per cold boot. If testing is authorized later, request at most5unframed614400-byte payloads with25s host timeout using capture_vga.py, then return to service without reboot for bounded /log/yuy2_640_v34vga/{runtime.log,vga.log,input-ssyc.bin,destination-ssyc.bin}. Do not use2.9 packet reassembly. Ambiguous SDF operations retain buffers until reboot; hardware responsiveness/output packing/frame coherence remain unproved.

## Offline checks

28 host worker scenarios pass, including stale pixel rejection, metadata-only cleanup and successful next candidate. Real retained4096B SSYC passes the expanded metadata contract and bound checks.9 compiled ARM stale-pixel reply cases and9 inherited ARM metadata-refusal cases pass;3 ARM session guards and11 PIC/dynamic-table/no-constructor cases pass. Text audit4923instructions,0NEON. Guarded installer fixtures are recorded separately under evidence/installer-verification.json. Hardware boundaries are mocked; none establishes a live frame.
