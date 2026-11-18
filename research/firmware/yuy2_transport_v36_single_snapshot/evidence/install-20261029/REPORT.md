# Revision 3.6 installed and reboot-verified — 29 October 2026

User explicitly requested flash of the matched single-snapshot diagnostic. Installation and activation reboot completed. No streaming/OBS/FFmpeg frame test yet; no crash-free or corrected-format claim.

- Initial baseline: exact installed 3.5 wrapper/module hashes and inactive streaming/probe process maps. Archived 5 diagnostic files (70105B), verified their camera MD5 against downloads, rechecked and individually cleared; system/tmp/fonts/tools preserved. Temporary uipc diagnostic cleared; original kikilog/system logs retained.
- Exact package identities and all subsystem/recovery baseline guards passed. Adequate /tmp,/log,/usr margins and helper write/readback passed. No kernel/RTOS/DMM/config change.
- Dependency-first install and read-only remount completed. Module and wrapper downloaded from /usr and compared byte-for-byte with local build. Module 35816B, MD5 c2e06b5a7a9f1361c4fb2a087d5e8fe2; wrapper 72796B, MD5 886445056d2eba99ef62df3a9def5e0f.
- Recovery previous-wrapper 72796B MD5 c16af3a036529b89d23fa4ccfd059ec3, separate 2.4p rescue 72792B MD5 5fde77e394572ebcf420f8941575f6c4, rollback 1195B MD5 1e03861d438ff6cc2fd58c1c38aa6e71 all readback-verified. Existing 3.5 producer retained. Rollback restores 3.5, which has reported crashes; rescue is a separate option.
- Reboot command produced CPU shutdown and Restarting system console messages. Job006 lacks its terminal marker because reboot ended the terminal; this is not a failed install. Fresh service session postboot passed all hashes and startup guards at uptime 68.57s. /usr verified read-only; no streaming/probe mappings before setup. Recovery/rescue/rollback independently rechecked.
- Postboot free bytes: /usr11219968, /log524107776, /tmp6619136; helper passed. Existing logging configuration preserved.
- Service closed cleanly: job010 WORKBENCH_CLOSED / Done. Camera remains3.6. No further device action scheduled.

Authoritative deployment-summary.json supersedes the build package's historical NOT_INSTALLED status; package contents/checksums remain unchanged. Expected behavior is ONE native frozen image replayed at advertised640x480/YUY2/10fps, with uncorrected native packing. Do not interpret duplicate USB payloads as continuous live acquisition. First-acquisition/stop stability remains unverified.
