# VGA reference binaries for the 4K/12-bit investigation

User paused camera tests on27October2026. This bundle preserves exact known binaries for offline comparison; do not install or mix its versions automatically.

- v24p-proven-bars is the hardware-tested synthetic640x480 YUY2 producer and its matching persistent gate. FFmpeg/OBS colour-bars success proves that tested transport sequence, not a genuine sensor image,12-bit pixels or4K support.
- transport-kernel-v23 is the paired proven USB kernel.
- v30-experimental is the currently installed VGA resize candidate and matching gate. Installation/readback/reboot passed; no live frame test occurred before the pause.

File sizes/MD5/SHA256 are in manifest.json. Next major milestone: [4K/12-bit next push](../../../docs/90-session/4K_12BIT_NEXT_PUSH.md). Current camera:3.0 installed, service session closed, no automatic resumption. Preserve2.9/2.4p recovery. The investigation must prove real native precision and complete buffer ownership before expanding geometry or changing the recording path.
