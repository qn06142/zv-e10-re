# Resident runtime display bring-up

18 November 2026. Profile display (v03) is installed, byte-verified and staged READY/unloaded in Senser. The owner reports no LCD change after activation, while the LED heartbeat still works. This trial failed to demonstrate display output. The owner reported the v02 runtime LCD was black but backlit. This first display experiment reuses that powered panel and its inherited timings; it does not perform a cold panel initialization.

## Native path recovered

Sony's Thumb routine at av-cam.bin file offset 0x807c1c calls three native field setters for bits 23:16, 15:8 and 7:0 of 0xf3445108. Two adjacent control wrappers at offsets 0x807c14/0x807c18 set bits 25/24 of that same word. The original path around 0x4b4b30 uses those controls together, converts the colour components, and calls the colour setter. Another path passes neutral chroma 0x80/0x80 and a shifted luma value. This supports interpreting the components as Y/Cb/Cr and using the native constant-colour/mute path. The precise hardware meaning of each control bit has not been independently specified.

The local reference image MD5 cdcae9d4fdbf66a33704a4c7564e346d differs from the camera's current whole-image MD5 90096db2c76148f4f9db5d104e5c608c. Five ordinary-file pages were read from the camera and matched the reference exactly, including the header, setters, native caller and wrapper pages. Their SHA-256 hashes are recorded in [hardware evidence](display-v03-hardware.json). This does not establish equality of the full images.

Read-only service-mode controls returned 0xf3445108=0x03008080, timing word 0xf3445048=0x02800025 and 0xf344505c=0x01df01df. These support 640-pixel/480-line LCD geometry. They are service-mode observations, not a normal-shooting register capture. 332 distinct controls were read only where stock instruction sequences showed read-modify-write access. The raw capture remains local; no controller register was written during that inspection or module stage test.

## Runtime behavior

os_display.S selects the shared resident runtime with a display test enabled. After privileged handoff it alternates Y=235 and Y=16, with Cb=Cr=128, in sync with the access LED. Each update preserves the original upper byte and sets the same two native control bits. Its sole added MMIO destination is 0xf3445108. It does not change clocks, panel timing, GPIO panel power, serial panel commands, framebuffer addresses or DMA descriptors. The inherited scanout must continue working for this experiment to appear on glass; darkness is a meaningful failure result, not proof that the colour-word mapping is wrong.

Use Setup → Version and the complete Up → Down → Left → Right → Up sequence twice: BOOT RDY, then BOOTING. Expected candidate behavior is alternating light/dark LCD plus the existing heartbeat. It remains in RAM until power is removed. Briefly remove the battery afterward to return to stock boot. av-cam.bin, the GUI library, launcher and boot selection were not replaced for this trial.

## Verification and artifacts

- verify_display_native.py executes the original Thumb colour and control setters for three initial control words and two luma values. All six cases match the runtime's update while preserving unrelated bits.
- verify_runtime.py with --display executes the new ARM image at two addresses with high vectors initially on/off. Each case checks five heartbeat cycles, ten exact colour writes and all private fault-vector branches. MMIO and CP15 effects are modeled; hardware scanout is not emulated.
- verify_launcher.py passes with the new module and unchanged GUI/launcher bytes.
- build.py --profile display builds against the matching prepared Sony GPL headers. The ABI-guarded module is 8192 bytes, SHA-256 1390f2105a93595c32919709b26e797c87aba7dacf78337ee28dcebcbf6e2fbd; the ARM image is 308 bytes.
- install_display.sh is a single-use guarded installer. It retains the previous working resident module at /log/zve10-ram-boot/display-v03/previous-runtime-v02.ko, checks READY and unloads before replacing the active module. It sends no GO. Full final module and backup readbacks matched their builds; /usr is read-only and no test module was left loaded.

A framebuffer, text console and independent panel reset/power/clock/timing sequence remain separate work. See the [RAM handoff guide](README.md) for the inherited-state boundary and stock fallback.

## Failed trial and hardware mapping boundary

The owner reported no change on the LCD with the LED flashing normally. There is no post-trial file readback in this record. The active v03 package has not been rolled back or reactivated in response to that report.

The verified field writes were insufficient to establish a visible output transaction. The original native control prefix also calls wrapper 0x807c36, which sets bit 0 at 0xf344510c; v03 did not reproduce that write. Its hardware meaning is unresolved, so it must not simply be labeled a commit strobe or added as another guessed fix. The handoff also runs kernel_restart_prepare, whose source invokes reboot notifiers and device_shutdown. No normal-shooting-to-post-shutdown display clock/routing/state capture exists. This source path does not prove which display driver or clocks were affected in the actual trial.

Further write trials are deferred while building the [hardware atlas](../../../docs/hardware/README.md): register meanings, value provenance, bus ownership, clocks, reset/power, update semantics and complete transactions take priority over another pixel patch.


## Split-screen pixel-format trial

The installed v04 comparison profile is a 640×48 OSD0 strip. The left half encodes red, green, blue and white as RRRRGGGGBBBBAAAA. The right half encodes the same bands in RGB565. This is a single stream of 16-bit words under the inherited two-byte OSD selector. Color, opacity and orientation on the LCD determine which encoding is consistent with scanout.

The full-height attempt failed during module init when the kernel could not allocate order-8 contiguous memory. The smaller 61,440-byte DMA allocation reached READY over Senser, unloaded cleanly, and was installed and read back byte for byte. Active module SHA-256 is `3b1f322572157fe38bfffb1a7f487b23f062681204d8b2ce2dc837db02074c6b`. The v03 backup is `/log/zve10-ram-boot/osd-compare-v04-strip/previous-display-v03.ko`. No GO was sent.

After the standard shutdown and SMP stop, the profile checks the inherited Output 0 and OSD0 state, runs the bounded native AIF stop handshake, then starts OSD0 with its own buffer. It reuses existing panel timing. A slow LED heartbeat indicates the register sequence ran, while a solid LED indicates the comparison stopped at a guard, timeout, or fault. Visible scanout and pixel format remain pending the owner trial. The runtime and the two encoders passed offline checks with modeled MMIO.

Disconnect USB and use the complete **Up → Down → Left → Right → Up** sequence twice on **Setup → Version**. Look for the order and colors of the bands on each side, and note the LED state if the LCD stays dark. Power off and briefly remove the battery to exit the runtime.


### v04 owner result and v05 correction

The owner observed an entirely white LCD with a slow LED heartbeat. The v04 heartbeat establishes that the post-shutdown route check and bounded AIF stop completed and the code issued the start request. v04 did not check live DMA readback. The observation does not distinguish the pixel encodings.

v04 limited AIF to 48 source rows while leaving the mixer at its inherited 480-row setting. The body-matched stock OSD0 path at file offset `0x4b5b4c` passes the descriptor height to `0x806652`, which changes bits 10:0 at `0xf344042c`. Offline execution at height 48 changed `0xabcdefff` to `0xabcde830`, preserving higher bits. The v05 build applies that change and samples the current AIF address for 80 ms to check whether it enters the owned DMA span. Slow blink means it was observed in range. Fast blink means no in-range sample was seen. Solid LED means the guard or stop failed, or the runtime faulted. Visual output remains the test of scanout.

The v05 binary and mocked register checks passed. The cause of the white panel remains unconfirmed pending the corrected hardware trial.

v05 reached READY over USB on 19 November, unloaded cleanly, and was installed and read back byte for byte. SHA-256 `09ed8887ad52f2d86a97e18774520d6ef4df66641efb9e0cf32a0e78c8d20329`. The v04 backup is `/log/zve10-ram-boot/osd-compare-v05-strip/previous-compare-v04.ko`. Hardware activation is pending.


### v05 owner result and v06 sustained-start test

The owner reported an entirely white LCD with a slow heartbeat on v05. The current AIF address entered the test buffer span at least once. Pixel fetch and sustained scanout remain unverified.

Stock live-view snapshots showed AIF control at both 3 and 2. Sony's checked start at file offset `0x7dc0f6` sets bit 0 only when it is clear. v06 polls the OSD0 control word after the first in-range sample and writes 3 only when it reads exactly 2. It keeps the same buffer, mixer dimensions and pixel words. The offline ARM fixture modeled both a consumed start and unexpected control values at two load addresses, with both initial vector modes. The runtime reissued the start only on the modeled consumed state.

The camera reached READY and unloaded v06 over Senser before the switch. The installed bytes matched SHA-256 `5c86f816d72e2809ba7219e67732af1d415bbd0ffe91c5c0f9523a146e17acb4`. v05 is saved at `/log/zve10-ram-boot/osd-compare-v06-strip/previous-compare-v05.ko`. GO was left to the owner.


### v06 owner photo confirms rear-LCD scanout

The owner photo shows a strip across the top of the rear LCD, with red, green and blue in order on the left half and muted bands on the right. The left words are `0xf00f`, `0x0f0f` and `0x00ff`. Their visible colors match RRRRGGGGBBBBAAAA packing. Under that packing the right-hand RGB565 red and green words have zero in the alpha nibble, consistent with their absence as saturated primaries. This establishes that Output 0 / OSD0 can scan the owned RAM buffer to the rear LCD under the inherited timings with the tested RGBA4444 encoding. It does not quantify alpha blending or demonstrate cold panel initialization.

Only 48 of the 480 source rows were drawn by the demo. The white area below the strip lies outside the test surface. A full-frame replay still needs a DMA buffer strategy that works around the failed contiguous allocation.

Evidence is the owner-supplied photograph, SHA-256 `b627bad1481dad0bf73e1ef0863b7737ad8d635ba07838f3cc1465599898c104`, held with the conversation.


### v07 full-frame color bars

The `osd-full` profile builds a 640×480 RGBA4444 frame with eight vertical bands and an eight-pixel black border. It uses the v06 sustain loop and the native 1,280-byte pitch. The allocator first tries a single coherent allocation, then searches up to 24 owned 64 KiB coherent allocations for a physically contiguous run. It frees unrelated blocks and refuses to stage if it cannot cover all 614,400 bytes. Offline checks exercised both allocation paths, rejection of a fragmented run, all frame pixels, and the full-height AIF and mixer values.

The camera reached READY in Senser and unloaded before installation. The final module matched its host bytes, and GO was left to the owner. The backup is `/log/zve10-ram-boot/osd-full-v07/previous-compare-v06.ko`. The full-frame visual trial is pending.

Staging receipt `ZVBOOT_STAGE_OSD_FULL DMA=05300000 bytes=614400 chunk=65536`. SHA-256 `ec98fb2bcebd5b168bbc8afe19511a703f039493db33859680bb882c215de9e3`.


### v07 owner result

The owner confirmed full-screen color on the rear LCD. This is the first full-frame scanout from the resident runtime. Staging proved the 614,400-byte span, and the runtime kept the image static. The next hardware milestone is a timed two-frame loop that checks the frame boundary and proves the CPU can prepare the next frame without modifying memory still in scanout.

For Bad Apple, encode the source clip as compact monochrome frames on the host and load the clip into RAM before GO. The resident path has no filesystem reader. Expand each frame into RGBA4444 on the camera and use the verified frame-boundary update path. Measure the resident display cadence before picking a playback rate.


### v08 procedural fire animation

The `osd-fire` profile advances a small heat grid and expands it 8× in each direction into the verified RGBA4444 surface. It uses the inherited scheduler counter for a nominal 100 ms hold. At each update it stops OSD0 and waits for the busy bit to clear before overwriting the single owned DMA buffer. It then restarts scanout and resumes the v06 start refresh. A stop timeout leaves the pixels untouched. The single-buffer pause can cause a brief blank during updates.

The fixed 480-row build failed to allocate a contiguous span on the 19 November service boot. This adaptive build tries 480 rows and falls back to 192 or 96 rows. The allocation can differ between Senser staging and the stock GUI activation. The module reached READY, unloaded, and matched final byte readback. The previous full-screen module is saved at `/log/zve10-ram-boot/osd-fire-v08-adaptive/previous-full-v07.ko`. GO was left for the owner.

Staging receipt `ZVBOOT_STAGE_FIRE 80x24 procedural, 640x192 scanout`. SHA-256 `46efd793d044e77bcd13f424eafedbe2b1a24dd45512d7221d1040636ffddcfd`.

The full-height v09 reserved-page prototype failed USB staging with ENOMEM on this boot, so v08 remains installed. The read-only follow-up showed 18,084 KiB free and no free blocks above order 6. The allocation experiment did not change the handoff ownership boundary.
