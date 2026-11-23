# ZV-E10 IMX284 Bayer RAW bring-up

## Latest status

- Sony's factory still command produced a real 6048 × 4024 Bayer frame with 16-bit little-endian samples. The measured path writes through ISP0 AIF3, reads through ISP1 AIF6, then publishes a retained DMM extent.
- ZVOS boots and reaches BayerRAW on hardware. Its first full still-readout attempt timed out, and LCD corruption obscured the other diagnostics. The next build preserves the receiver and DMA state before cleanup and was accepted by the RAM loader. A working standalone sensor readout remains unverified.
- See [factory RAW publication](#factory-raw-publication-on-the-final-capture-work-release), [SGC0 and IRQ replay](#4-offline-follow-up-on-sgc0-and-the-shared-isp-completion), and [timeout snapshot](#7-timeout-snapshot).

## 1. Early RdcW0 investigation (22 November 2026)

- **The standalone probe had no nonzero Bayer pixels at this checkpoint (`PIX nonzero=0`).**
- **USB Senser `/dev/mem` rapid-test harness is working** ([senser_bayer_runner.c](senser_bayer_runner.c) + [test_bayer_senser.py](test_bayer_senser.py)), allowing hardware tests without reflashing `rtos.bin` or rebooting into ZVOS on every iteration.
- **Physical DMA destination `0x25200000..0x25700000` (5 MiB) is proven safe:**
  - `/proc/cmdline` reports `mem=1G@0 ... memrsv=680M@0x15800000:uc`.
  - `senser-bayer-test-02` through `test-23` repeatedly verified `CHECK_NZ=0 CHECK_CHANGED=0 CHECK_PTR=0` across `0x25200000..0x25700000`.
- **Two distinct breakthroughs were achieved on live ZV-E10 hardware:**
  1. **Bare-metal IMX284 sequencer + continuous `SGC0..3` clocks + SLVS-EC PHY release** reached `I=7 T=0` (all 7 serial bursts completed) and sustained `0x00010001` across all four SGCs (`test-06`..`test-14`).
  2. **Root cause of completely dead `RdcW0` (`W0=00000000 C=00000000`) was found and verified live (`test-20-rdcw0`, `test-23-rdcw0`):** missing DFE internal crossbar routing (`0xfc0a0154 = 0x40000000`, `0xfc0a0180 = 0x00010000`, `0xfc0a8700 = 0x00000100` from resource `0x2f`). Adding those writes made `RdcW0` clear start bit 0 (`3 -> 2`), go active/busy (`0xfc0a9204 = 0x80000000`), and latch the target DMA address (`0xfc0a9210 = 0x25200000`).
- **Remaining blockers (`C` stays at `0x25200000`, `ERR=0x00010000`, `PIX nonzero=0`):**
  - In `--mode rdcw0` (tapping live stock preview), Core 1's live VSYNC interrupt handler overwrites `SGC2` (`0xfc0a13d0`, `0xfc0a1358`, `0xfc0a135c`) every frame, preventing `SGC2`'s `RdcW0` capture trigger (`0x08c00000`) from firing (`test-23-rdcw0`).
  - In `--mode full` (bare-metal bring-up), `generate_bayer_init.py` still extracts tables from resource `0x39` (movie) rather than resource `0x2f` (`Ifmt -> RdcW0`), and `SLV`/`SIF` (`0xfc0f00ac/b0 = 0`, `0xfc0a3210 = 0`) did not stream frames in `test-21-full`.

---

## 2. Key Hardware & Firmware Findings

### A. Verified Live Sequencer & IMX284 Wake / SGC0 / PHY Bring-Up (`test-06`..`test-14`)
1. **Mask Core 1 Sequencer IRQ during polling (`0xfc088f08 = 0`):**
   - When `0xfc088f08 = 1`, Core 1's running LIRO RTOS ISR steals `0xfc088f04` acks (`I=0 T=13` in `test-02`).
   - Calling `seq_irq_enable(0U)` and polling `(r32(0xfc088f00) | r32(0xfc088f04)) & 1U` completes all 7 bursts (`4` wake + `2` mode5 + VD-triggered `imx284_mode5_upload_2`) with `I=7 T=0` (`test-06`..`test-14`).
2. **Power Rails, SoC CRG & SLVS-EC PHY Release:**
   - Live stock active sensor rails differ from `0x637AD800`: write `0xfc029004 = 0x000000f2` and `0xfc029008 = 0x00000077` after `imx284_power_on_ops` (wait `5000 us`).
   - Apply `0xf2a300a4 = 0x00000400` (`0x637a75d0`, SoC CRG bit 10) and `0xfc02a040 = 0x00000000` (`0x637a8940`, SLVS-EC PHY reset release) **before** `imx284_wake_pre_writes`.
   - Call `slvsec_relock_mode5()` (43-write `0x637AEBD0` sequence in `senser_bayer_runner.c`, L619-674) right after `imx284_mode5_upload_1`.
3. **Continuous `SGC0` (`0xfc0a1100`):**
   - `generate_bayer_init.py` currently passes `0x63D26A42(..., 72, 0, 0, 1)` and zeroed `MEM+0x2000` to `0x6379CE58`, yielding `0xfc0a114c = 1`, `0xfc0a1150 = 0x20002`, `0xfc0a112c = 0`.
   - Overriding with live continuous XVS/XHS config **before** `imx284_wake_pre_writes` (and re-asserting before start) keeps `SGC0..SGC3` locked at `0x00010001` (`test-12`..`test-14`):
     ```c
     w32(0xfc0a114cU, 0x00000004U);
     w32(0xfc0a1150U, 0x00250005U);
     w32(0xfc0a112cU, 0x00000001U);
     w32(0xfc0a1108U, 0x00000000U); /* 0 = continuous, 1 = one-shot/stop */
     w32(0xfc0a1110U, 0x00000001U);
     ```

### B. `0xfc0a0000` is W1S (Write-1-to-Set), `0xfc0a0004` is W1C (Write-1-to-Clear)
- Disassembly of `av-cam.bin` (`0x6379e840` and `0x6379e850`, wrapped by `0x63d23ab8` / `0x63d23ac2`) confirmed:
  - `0x6379e840`: `str (1 << r0), [0xfc0a0000]` (**W1S**).
  - `0x6379e850`: `str (1 << r0), [0xfc0a0004]` (**W1C**).
- **Important:** Do **not** read-modify-write or restore `0xfc0a0000` (`r32(0xfc0a0000) | bits`), because `r32(0xfc0a0000)` returns active enable bits (`0xb1e8`, `0xb1fa`, etc.) and writing them back re-triggers all set bits (or clobbers active channels). Write only the specific single-bit masks (`0x2`, `0x80`, `0x8000`).
- Wait: note why `test-21-full` had `SGC0 a=00000001 c=00000001` (dropping from `00010001` in `test-14`): `run_full()` currently still has `w32(0xfc0a0000U, r32(0xfc0a0000U) | 0x00008082U);` at line 711! Removing that RMW (and switching to `res=0x2f`) avoids touching `0xfc0a0000` spuriously.

### C. DFE Internal Crossbar (`0xfc0a0150..0xfc0a018c`) & Resource `0x2f` vs `0x39`
- Unicorn trace of `0x6379AEE4`, `0x6379A510`, `0x6379CB68`, and `0x6379AB48` on `av-cam.bin` proved:
  - `generate_bayer_init.py` queried drive `0x17` -> `resource = 0x39` (movie) and only OR'd `(1 << 21)` onto `operation + 0x28` **after** `resource = 0x39` was selected.
  - Because the crossbar table (`0xfc0a0150..0xfc0a018c`) is driven by the operation's resource index (`0x6379e068`), `res=0x39` wrote **`0xfc0a0154 = 0x00000000`** and **`0xfc0a0180 = 0x00000000`**, leaving `RdcW0` disconnected!
  - Native `res=0x2f` (`0x6426a800`, `flags = 0x00200001` = pure `Ifmt -> RdcW0`) emits **173 MMIO writes total** (`25` acquire + `116` setup1 + `29` setup2 + `3` start), including:
    - Crossbar: `0xfc0a0154 = 0x40000000`, `0xfc0a0180 = 0x00010000` (all other `0xfc0a0150..018c` = `0`).
    - Enables: `0xfc0a0000 = 0x2, 0x80, 0x8000` (separate writes), `0xfc0a1300 = 1`, `0xfc0a1200 = 1`, `0xfc0a9000 = 4, 2`, `0xfc0a8700 = 0x00000100`.
    - Capture trigger in `SGC2`: `0xfc0a1354 = 0x01fb0497` (active V end), `0xfc0a13d0 = 0x08c00000`, plus `start`: `0xfc0a9200 = 3`, `0xfc0a1310 = 1`, `0xfc0a1210 = 1`.
  - Unlike `res=0x39`, **`res=0x2f` does NOT touch `0xfc098808` (`0x00020001`) or `0xfc098000` or `FOP` (`0xfc0ad600`)**. Notice `test-14` (where `ST=...:003e0007`) vs `test-21-full` (`ST=...:00020001`)! Wait: `test-14` had `0xfc098808 = 0x003e0007` only when `res=0x39` didn't conflict or before `test-21-full`? Checking `res=0x2f` avoids `0xfc098xxx`/`FOP`/`Img` writes altogether!

### D. Live Hardware Behavior Observed in Latest Tests (`test-19`..`test-23`)

| Test | Mode | Result / Key Telemetry | Takeaway |
| :--- | :--- | :--- | :--- |
| `test-19-rdcw0` | `rdcw0` (no crossbar) | `rc=0`, `W0=00000000 C=00000000`, `fc0a3210=00000775`, `dfe10=004a2251`, `fc0f00ac=3`, `fc0a0154=0`, `fc0a0180=0`, `PIX nonzero=0` | Stock preview actively streams valid pixels through `Ifmt`, but `RdcW0` crossbar is unrouted (`0154=0`, `0180=0`). |
| `test-20-rdcw0` | `rdcw0` (`0154/0180/8700` added) | `rc=0`, **`W0=80000000 C=25200000 ERR=00010000`**, `fc0a3210=00000775`, `dfe10=004a2251`, `PIX nonzero=0` | **Crossbar works!** `RdcW0` self-cleared bit 0 (`3->2`), went busy (`0x80000000`), and latched `0x25200000`, but `SGC1`/`SGC2` (`fc0a1210/1310=0`) weren't triggered. `stop_rdcw0()` left `0xfc0a9204=0xc0000000` until channel reset added. |
| `test-21-full` | `full` (`0154/0180/8700` + RMW on `a0000`) | `rc=0`, `CLEANED_IDLE`, `I=6 T=1`, `SGC0 a=00000001 c=00000001`, `W0=c0000000 C=25200000`, `fc0f00ac=0 fc0f00b0=0 dfe10=0` | Reused leftover `W0=c0000000` from `test-20`; RMW on `0xfc0a0000` broke `SGC0` (`00000001`); `mode5_upload_2`/wait timed out (`T=1`) and sensor/SLVS-EC didn't frame. |
| `test-22-rdcw0` | `rdcw0` (same boot after `test-21-full`) | `bayer_test check` `rc=0`, then **`CAMERA_SCN_EE_START_STOP b:1 b:0` froze camera** | **Never run `CAMERA_SCN_EE_START_STOP` (`--mode rdcw0`) after `--mode full` without rebooting!** `full` masks `0xfc088f08=0`, `0xfc0a0018/30=0`, and powers off sensor (`0xfc029000/08/28=0`, `PMU=1`), wedging stock Core 1 RTOS. |
| `test-23-rdcw0` | `rdcw0` (fresh boot, `SGC1/2` init, `h=0x240`, W1S `a0000`) | `rc=0` (clean `b:1 b:0` -> `b:16 b:0`), `W0=80000000 C=25200000 ERR=00010000`, `P0 SG2` showed **`fc0a13d0=06720000`**, `fc0a1358=000d0269`, `fc0a135c=05f10279`, `fc0a1310=0` | Stock Core 1 VSYNC ISR actively overwrote our `SGC2` window (`0x3ffe3ffe`, `0x08c00000`) every frame while preview was running! |

---

## 3. Recommended Next Steps (in USB Senser Mode)

### Path 1 (Cleanest): Bare-Metal `res=0x2f` in `--mode full`
No fighting Core 1's live preview ISR!
1. **Fix `senser_bayer_runner.c` `run_full()` vs native `res=0x2f`:**
   - Remove line 711 (`w32(0xfc0a0000U, r32(0xfc0a0000U) | 0x00008082U);`) — never RMW W1S `0xfc0a0000`.
   - Switch `generate_bayer_init.py` (or temporarily test a clean `res=0x2f` table in `senser_bayer_runner.c`) from `resource = 0x39` to native `resource = 0x2f` (`0x6379AEE4 -> 0x6379A510 -> 0x6379CB68 -> 0x6379AB48`). Note that in Unicorn, `res=0x2f` sets `0xfc0a1220..12c0`, `0xfc0a1320..13ec`, `0xfc0a1c00..1c7c`, `0xfc0a3300=0`, `0xfc0a8704..0xfc0a9274`, and `0xfc0a9200=3, 0xfc0a1310=1, 0xfc0a1210=1` without clobbering `0xfc098808` or `FOP`.
   - Check why `test-14` had `I=7 T=0` & `SGC0=00010001` & `ST=...:003e0007` & `fc0f00ac=2` (SLVS-EC locked!), whereas `test-21-full` had `I=6 T=1` & `fc0f00ac=0`. Likely causes:
     - `run_full()` clears `PMU_BASE_PA + 0x210/008/004 = 0`, wait: `bayer_capture.h` also runs DDRC B `bayer_psave_imager_wake()` (`0xf0105000`); in Linux Senser mode, check if `0xf0105068/138` or `0xfc020028`/`0xfc021024` differ before/after.
     - Keep `SGC0` untouched in `0xfc0a0000`, verify `I=7 T=0` returns cleanly, and compare `full`'s `P0 SL0`, `P0 SLV` (`fc0f00ac`, `fc0f00b0`, `fc0f00b4`, `fc0f00b8`), and `P0 SIF` (`fc0a3210`) against `test-23-rdcw0`'s working stock `Ifmt` values (`fc0a3210=0x775`, `fc0f00ac=2`, `fc0f00b0=1`, `fc0f00b4/b8=0`).
2. **Once `Ifmt` (`0xfc0a3210 != 0`) streams in `--mode full`:**
   - With `res=0x2f` crossbar (`0154=0x40000000`, `0180=0x00010000`, `8700=0x100`), `SGC2` (`0xfc0a1354=0x01fb0497`, `0xfc0a13d0=0x08c00000`), and `0xfc0a9200=3`, `RdcW0` will write live `1996x1122` Bayer RAW to `0x25200000`, `C` (`0xfc0a9210`) will advance/wrap (`> 0x25200000`), and `test_bayer_senser.py` will download `/tmp/bayer_full.raw` and render `preview_full.png`.

### Path 2 (Alternative Diagnostic in `--mode rdcw0`)
If debugging `RdcW0` + `SGC2` against stock preview before fixing bare-metal `SLV/SIF`:
- Investigate what `0xfc0a9208 = 0x00010000` (`ERR` bit 16) means in DFE AIF (`0xfc0a9208`), and why stock Core 1 ISR wrote `0xfc0a13d0 = 0x06720000` and `0xfc0a1358/5c`.
- Temporarily test a tight spin-loop in `run_rdcw0()` re-applying `0xfc0a13d0 = 0x08c00000` / `0xfc0a1358 = 0x3ffe3ffe` / `0xfc0a1310 = 1` across 2 frames (~60 ms) to see if `C` (`0xfc0a9210`) advances above `0x25200000` (note: do this cleanly and keep timeouts short so stock RTOS stays responsive, and **always** restore registers before `CAMERA_SCN_EE_START_STOP b:16 b:0`).

### Path 3 (Final ZVOS Integration & Flash — ONLY after `full` captures live pixels)
1. Sync all verified fixes into [generate_bayer_init.py](generate_bayer_init.py), regenerate [bayer_sensor_tables.h](bayer_sensor_tables.h), and update [bayer_capture.h](bayer_capture.h) / [os_shell.c](os_shell.c).
2. Rebuild `rtos.bin`, verify with both Unicorn unit/emulation suites (`verify_os_shell.py` and `verify_bayer_capture.py`), clean `/tmp/bayer_test` and `/tmp/bayer_*.raw` on the camera, and flash once via [stage_rtos.py](stage_rtos.py).

---

## 4. Modified & Active Files

| File | Purpose / Current State |
| :--- | :--- |
| [senser_bayer_runner.c](senser_bayer_runner.c) | Static ARM `/dev/mem` runner (`check`, `full`, `rdcw0`). Currently has crossbar + `SGC1`/`SGC2` + `stop_rdcw0()` channel-reset fix in `run_rdcw0()`, `slvsec_relock_mode5()` + `SG1`/`SG2` pipeline dumps. Note: line 711 in `run_full()` still has the RMW on `0xfc0a0000` to be removed when updating `full`. |
| [test_bayer_senser.py](test_bayer_senser.py) | Host runner building `bayer_test` (`-mcpu=cortex-a5 -nostdlib -static`), uploading via Senser, running `--mode {both,rdcw0,full,check}`, saving `log.txt`/`report.json`, and demosaicing captured RAW to `preview_<tag>.png`. Always invoke with `.\.venv\Scripts\python.exe`. |
| [generate_bayer_init.py](generate_bayer_init.py) | Unicorn extractor generating [bayer_sensor_tables.h](bayer_sensor_tables.h) from `.local/dumps/av-cam.bin` + `.local/dumps/staged/audit/Backup.bin`. Still on `res=0x39` + v9 SGC0/power params; needs sync once Senser `full` passes. |
| [bayer_capture.h](bayer_capture.h) | Bare-metal ZVOS IMX284 + `RdcW0` capture driver used by [os_shell.c](os_shell.c). Needs sync with verified live fixes once Senser `full` captures pixels. |
| [os_shell.c](os_shell.c) | ZVOS shell (Mode 3: `Live Bayer RAW`, Mode 4: `Bayer Probe`). Needs `rtos.bin` rebuild + flash after capture is verified. |

---

## 5. Exact Command Reference

Run commands from `d:\02_Development_And_Projects\pmca-re` using `.venv\Scripts\python.exe`:

```powershell
# Safe check + live stock preview RdcW0 test (never run after --mode full on same boot)
.\.venv\Scripts\python.exe research/device/zve10_ram_boot/test_bayer_senser.py --mode rdcw0 --out .local/out/senser-bayer-test-24-rdcw0

# Bare-metal bring-up test in Senser mode (reboot camera afterward before any CAMERA_SCN_EE test)
.\.venv\Scripts\python.exe research/device/zve10_ram_boot/test_bayer_senser.py --mode full --out .local/out/senser-bayer-test-24-full

# Regenerate bayer_sensor_tables.h from firmware dumps (once updated)
.\.venv\Scripts\python.exe research/device/zve10_ram_boot/generate_bayer_init.py

# Build ZVOS rtos.bin and run Unicorn verification suites
.\.venv\Scripts\python.exe research/device/zve10_ram_boot/build_rtos.py --display --source research/device/zve10_ram_boot/os_shell.c --out .local/out/zvos_shell_live_bayer
.\.venv\Scripts\python.exe research/device/zve10_ram_boot/verify_os_shell.py .local/out/zvos_shell_live_bayer/rtos.bin
.\.venv\Scripts\python.exe research/device/zve10_ram_boot/verify_bayer_capture.py .local/out/zvos_shell_live_bayer/rtos.bin

# Stage verified rtos.bin onto the camera (only after live capture is confirmed)
.\.venv\Scripts\python.exe research/device/zve10_ram_boot/stage_rtos.py .local/out/zvos_shell_live_bayer/rtos.bin --out .local/out/stage-live-bayer --backup-name rtos.pre-live-bayer-v9.bin
```

## 22 November follow-up

The generated mode-5 tables now use native DFE resource `0x2f` directly.
The full Senser runner uses the table's individual writes to `0xfc0a0000`
and leaves the movie FOP block alone. The test wrote the expected crossbar
values `0x40000000` and `0x00010000`. The entry snapshot already showed
RdcW0 status `0xc0000000`. During the run the SGC0 status stayed at
`0x00000001`, six serial bursts completed and one timed out, and the
RdcW0 pointer stayed at `0x25200000` with error `0x00010000`.
The DMA buffer remained empty. The trace is
`.local/out/senser-bayer-test-24-full/log.txt`.

After a battery pull, the next run began with RdcW0 control, status and
pointer at zero. The last sequencer burst still timed out, SGC0 still read
`0x00000001`, and RdcW0 never latched a destination or wrote pixels. The
receiver monitor showed no input activity. This rules out the previous
stuck writer as the sole cause. The cold run is
`.local/out/senser-bayer-test-26-cold-full/log.txt`.

A paired native-table replay confirmed that the old movie path enables
additional DFE bits `0x8`, `0x10`, `0x1000` and `0x2000` and separately
configures and starts SGC3. The raw-only path omits those movie operations.
This is a concrete difference to isolate in the sensor wake sequence. It
does not establish which operation makes the SLVS-EC receiver lock.

The ZVOS `BayerRAW` mode now checks for writer progress, an idle writer
at the final rows of the owned one-shot buffer and no writer error before
the CPU reads it. It keeps the current LCD frame while waiting, resizes in
software into the backbuffer, and re-arms the writer and SGCs against the
other aligned RAW slot. The menu retains both DMA slots if the writer stays
busy during exit. ARM replay verifies the alternating addresses, successive
modeled frames, and an LCD hold while the writer is busy. The shell verifier
also passes.

The Senser still-capture path previously returned a verified stock RAW frame.
The result above concerns the independent mode-5 producer. The live Bayer
build has not been staged or run after GO.

## Native initialization replay

The SGC0 extractor now runs the original DFE initializer `0x6379c994`
as far as its call to `0x63d26a42`. The initializer uses the IMX284
constructor's InitParam, whose 56 bytes matched the captured Senser
object. Native clock arguments after the object pointer are
`72, 3, 32, 4`. The earlier harness supplied `72, 0, 0, 1`. The native
call programs `0xfc0a114c = 4` and `0xfc0a1150 = 0x00250005` before the
SGC starts. The runner now uses these generated writes without manual
overrides.

Replay of the idle-to-mode-5 imager calls also found no additional
SLVS-EC relock between the 45-byte and 124-byte sequencer uploads. The
native wake already performs that operation, so the Senser runner
dropped its extra relock.

| Senser run | Change | Result |
| --- | --- | --- |
| `27-full-sgc3` | Added only SGC3 acquisition, setup and start from the native movie route | SGC3 reached control 1, final burst timed out, zero pixels |
| `28-native-wake` | Removed the extra receiver relock | Final burst timed out, zero pixels |
| `29-native-sgc-clock` | Used native clock arguments and removed repeated SGC0 overrides | SGC2 reached `0x00010001`. SGC0 stayed at 1, the receiver monitor stayed quiet, the final burst timed out and the buffer remained empty. |

Records are under `.local/out/senser-bayer-test-27-full-sgc3`,
`.local/out/senser-bayer-test-28-native-wake` and
`.local/out/senser-bayer-test-29-native-sgc-clock`. The native clock
table is shared with the ZVOS payload. No live payload was staged.

## Stock still capture through ISP AIF

The ZV-E10 returned to USB Mass Storage after Linux `/sbin/reboot`. Two
Senser sessions each started stock preview, triggered one `adjstctl.elf
0x404 0x4e` capture, and reached adjustment status idle. The camera switched
from imager mode `0x01` to `0x37` and back to `0x01` in each trace.

| Observed order | Stock AIF channel | Register base | Observed operation |
| --- | --- | --- | --- |
| 1 | ISP0 logical 3, write | `0xf3002380` | Status bit 31 rose and the cursor advanced through the programmed RAW span. |
| 2 | ISP1 logical 6, read | `0xf3102200` | In the poll where ISP0 went idle, ISP1 was busy and its cursor began advancing through the same span. |
| 3 | DMM publication | `0x043d7320`, `0x043bbc8c`, `0x043bbc90` | After ISP1 went idle, Sony retained the handle and published base `0x0b000000` with extent `0x03000000`. |

The native AIF table at `0x63e89724` supplies both channel bases and their
direction flags. Trace 07 captured identical geometry on both ports.
The `+0x20/+0x24/+0x28/+0x2c` words were `0x0b000000`, `0x2f40`,
`0`, and `0x0fb7`. These describe 12,096 bytes per row and 4,024 rows
with zero gap, consistent with the previously recovered 6,048 × 4,024
little-endian Bayer16 frame. The image occupies 48,674,304 bytes of the
published 48 MiB span. The acquisition audit reproduces the four geometry
registers through the original AIF setters for both channel IDs.

DFECore RdcW0 control, status, cursor and base were zero in every sample.
Both ISP cursors returned to zero once their busy bits cleared, so the
RdcW0 end-address test in the current ZVOS demo cannot be carried across
unchanged. The standalone sequence still needs the stock setup and trigger
that arm logical channel 3 and an owned DDR span before sensor readout.
Reusing a stock-managed span would also require waiting for the ISP1 reader
to finish.

The offline mode-transition replay uses the original imager SetMode
routine and the captured body profiles. It reaches the end of the
`0x01` to `0x37` SetMode call with modeled ADC reads. The mode-1
phase made three sequencer uploads. The target SetMode call made none
and did not write MMIO in this model. The target frame readout uses
additional stock services outside this replay. The observations establish
the stock still path and leave standalone sensor triggering after GO
unverified.

The binary samples and decoded geometry are in
`.local/out/rtos-stock-raw-dma-06` and
`.local/out/rtos-stock-raw-dma-07`. Run `trace_stock_bayer.py` from a
fresh boot to collect one exposure. The mode replay is in
`.local/out/rtos-stock-raw-mode37-replay.json`.

### Stock timing and AIF arm

A third stock exposure after Linux reboot completed with the same ISP0
write, ISP1 read and DMM publication. The expanded trace adds imager
state, sequencer and SGC registers. Times below are relative to the
first probe poll and describe sampled states.

| Time | Observed state |
| --- | --- |
| 490 ms | DFE control became `0x160`. SGC1 and SGC2 control cleared. |
| 504 ms | Imager words `+0x11c/+0x120` became `0x37`. SLVS-EC input monitor bit 0 cleared. |
| 520 ms | Imager `+0x124` became `0x37`. DFE control became `0x31fa`. SGC1, SGC2 and SGC3 control read 1. SGC2 `+0x54/+0xd0` became `0x05f51024/0x0d200000`. SGC3 `+0x54` became `0x05e7100f`. The sequencer run word read 0. |
| 530 ms | The SLVS-EC input monitor read 1. ISP0 was busy with a cursor inside the programmed RAW span. |
| 604 ms | Imager `+0x11c/+0x120` returned to 1. The ISP0 writer went idle and the ISP1 reader was busy. |
| 664 ms | The ISP1 reader went idle. |

The original AIF arm wrapper at `0x63da20f6` tests control bit 0 and
calls `0x639e21e0` to set it when clear. The acquisition audit ran it
against the two stock ports. With a control fixture of 2, it wrote 3
and rejected a second arm while bit 0 remained set. The expanded
hardware trace sampled control 3 at 520.120 ms and control 2 with busy
set at 529.987 ms.

The offline extractor now also runs the target readout setup
`0x637ad06c` after SetMode. It reached its return using the body
profiles, with ADC reads and firmware IPC trace calls modeled. It
produced three mode-`0x37` sequencer uploads of 251, 45 and 124 bytes.
Compared with mode 1, their bytes differ at 38, 1 and 24 positions.
The separate per-frame `SetImgRd` descriptor and complete ISP route
setup are still needed for standalone capture.

`BayerProbe` and the standalone RTOS probe now show the two measured
ISP AIF ports. The acquisition logic for `BayerRAW` still uses the
previous experimental route. The new probe makes no writes to either
ISP port.

The hardware recording is in `.local/out/rtos-stock-raw-trigger-01`.
The readout replay is `.local/out/rtos-stock-raw-trigger-replay-01.json`.

### ZVOS mode-0x37 capture trial

`BayerRAW` now runs the recovered native DFE setup for sensor mode
`0x37`, drive `0x2b` and resource `0x39`. Native replay reproduced the
SGC2 and SGC3 timing words measured during the stock exposure. Generate the
tables with `generate_bayer_init.py --profile-dir` and the captured body
property directory. The C payload configures ISP0 AIF3 for 6,048 × 4,024
16-bit pixels, with no line gap. Its dedicated non-cacheable span is
`0x35000000..0x37ffffff`, carved from the former cacheable mode heap.

Each arm submits the recovered 124-byte frame-synchronous sensor burst
and starts the DFE timing generators. The loop requires writer progress,
then idle with a reset cursor, no reported AIF error, and overwritten
markers at the end of the buffer. The CPU finishes Bayer reconstruction
and software resize before rearming. It keeps the last LCD frame during a
normal transfer and reports a timeout after one second.

This trial repeats the burst from the mode-transition replay. Sony's
per-frame `SetImgRd` descriptor and still ISP controller setup have not been
replicated in full. The ARM model supplies DMA data for verification. A
camera run after GO is required to establish sensor triggering and frame
production.

### Verification and staging status

| Evidence | What ran | Result |
| --- | --- | --- |
| Stock Senser RAW readback | ZV-E10 with Sony's stock sensor services | One sensor frame was read back at 6,048 × 4,024. The full 48 MiB allocation matched the camera-side SHA-256. See [verified sensor frame readback](LIVE_VIEW.md#verified-sensor-frame-readback). |
| ZVOS `BayerRAW` verification | ARM model with synthetic Bayer data injected by a modeled ISP0 DMA writer | Three frames reached the LCD model, alternating red over blue, blue over red, and red over blue. A fourth modeled transfer stopped while busy. |
| ZVOS on the camera | Senser staging attempt for `.local/out/rtos-isp0-bayer-live-01/rtos.bin` | The candidate read back byte for byte. Linux then failed to allocate memory while loading `boot.ko`. The staging script restored the previous `rtos.bin` and verified its readback. The loader never reached `READY`, and no GO was sent. |

The 28,900-byte candidate remains on the host with SHA-256
`35ce944491e96520b50bc2bc4c84a9836fb0b829da2a61cdfc8d63130a09a0cd`.
The staging record is `.local/out/stage-isp0-bayer-live-01/stage.json`.
Camera work stopped after the rollback. The standalone RTOS has yet to
produce a verified sensor frame. A hardware test must show successive
scene changes reaching the LCD after GO.


### Senser runner session, 2026-11-21 to 2026-11-23

This session continued the USB Senser `/dev/mem` tests in
`senser_bayer_runner.c` and `test_bayer_senser.py`. No ZVOS image was
built, staged or booted. No sensor pixels were captured.

#### Changes to the generator and tables

`generate_bayer_init.py` now writes 1 to `MEM + 0x2004` before the
native call at `0x6379CE58`. `bayer_sensor_tables.h` was regenerated
with `--profile-dir .local\out\rtos-live-view-hardware-20261121-03`.
`dfe_mode5_clock_sgc_writes` now contains `0xfc0800f4 = 0x0012541e`
and `0xfc0a112c = 1`.

#### Hardware runs

All runs used `test_bayer_senser.py`. Each output directory under
`.local/out/` holds `log.txt` and `report.json`.

| Run | Change under test | Result |
| --- | --- | --- |
| `senser-bayer-test-30-full` | Mode 5 bring-up with the regenerated tables | Exit code 0, ended with `CLEANED_IDLE`. SGC0 `0xfc0a1110` and SGC1 `0xfc0a1210` both read 1. RdcW0 `0xfc0a9200` stayed idle, cursor 0. Sequencer counts were `I=6 T=1`. SLVS-EC read `0x0103ffff` / 1. `PIX nonzero=0`. |
| `senser-bayer-test-31-full` | Added the 43-write SLVS-EC relock (`imx284_wake_pre_writes[98..140]`) and `0xfc098808 = 0x003e0007` | Exit code 0, ended with `CLEANED_IDLE`. SGC1 read `0x00010001`, so it ran. SGC0 stayed at 1. RdcW0 stayed idle. `PIX nonzero=0`. |
| `senser-bayer-test-32-full` | Wrote `0xfc099100 = 1`, `0xfc098908 = 0x20000` and `0xfc098008 = 0x10` straight after the clock table | The camera hung before the first sequencer burst (`B0`). The log stops after `bayer_test check`. The report records no completion marker for `/tmp/bayer_test full`. The user restarted the camera. |

An earlier `--mode rdcw0` run made with stock preview active gave these
results:

- RdcW0 was busy (`0x80000000`) with its cursor at `0x25200000`.
- The AIF error register read `0x00010000`.
- `PIX nonzero=0`, and no `/tmp/bayer_rdcw0.raw` was written.

The native getters `0x639e233c` and `0x639e2360` read error bits from
`+0x08`, and `0x00010000` falls in the `0x000f0000` field they mask.

#### Causes found offline

- **test-32 hang:** native order is `dfe_still_clock_writes` L706–712.
  It writes `0xfc098808` (`0x20000`, then 1) and `0xfc098000` (`0x40`,
  then `0x20`) before any `0xfc0989xx` or `0xfc099xxx` write. test-32
  wrote that block first.
- **SGC0 in test-11 to test-14:** SGC0 read `0x00010001` only after
  test-05. In test-05, `CAMERA_SCN_EE_START_STOP b:1 b:0` started stock
  preview and timed out before `b:16 b:0` ran. Stock preview is the
  likely reason SGC0 ran then. The `b:16` teardown later cleared
  `0xfc080014` and `0xfc0a1100` and set bit 6 of `0xfc021024`.
- **RdcW0 is idle in stock capture:** in
  `.local/out/rtos-stock-raw-trigger-01/report.json`, every
  `dfecore_rdcw0` field stays 0 during stock mode `0x37`. The RAW
  writes go through ISP0 AIF3 `0xf3002380`. The writer was programmed
  with base `0x0b000000`, line `0x2f40` and rows minus one `0xfb7`.
  Control went 3 then 2, status `0x80000000` while busy. The cursor ran
  from `0x0b589700` to `0x0dcfc200`, then reset to 0. After that, ISP1
  AIF6 `0xf3102200` read the same span.
- **Wake difference from ZVOS:** before test-33, the runner woke only
  the PMU at `0xf290e000`. `bayer_capture.h` `bayer_psave_imager_wake()`
  also releases DDRC_B at `0xf0105000` first.
- **Possible ZVOS ordering fault (not tested):** `bayer_capture_start()`
  writes `imx284_still_pre_writes` after the wake table. That table
  stops the SLVS-EC receiver, writing 0 to `0xfc0f0050`, `0xfc0f0150`
  and `0xfc0f0000`, and then restarts it with `0xfc0f0000 = 0x0103ffff`
  and `0xfc0f0050/0150 = 1`. No relock follows it before
  `imx284_still_upload_2`. This has not been compared on hardware.

#### `senser_bayer_runner.c` edits, not compiled or run

These edits were saved after test-32. They have not been compiled, and
`bayer_test` has not been run since.

- **Mappings:** `regions[]` grew from 6 to 8. It now also maps
  `0xf0105000` (`0x1000` bytes) and `0xf3000000` (`0x40000` bytes,
  covering ISP0 and FOPD). `reg_ptr()` searches every register region
  and skips index 5, the DMA buffer.
- **Defines:** added `ISP0_AIF3_BASE` (`0xf3002380`) and
  `BAYER_PSAVE_DDRC_B` (`0xf0105000`).
- **Wake:** `psave_imager_wake()` is a port of
  `bayer_psave_imager_wake()`. It logs DDRC_B `+0x68`, `+0x90`,
  `+0x138` and `+0x148` before and after. It replaces the PMU-only wake
  at the start of `run_full()`.
- **Entry check:** `run_full()` now also exits with 3 when ISP0 AIF3
  shows start, busy or stop at entry.
- **Removed writes:** the hand-written writes made after
  `dfe_mode5_clock_sgc_writes` are gone, including the
  `0xfc099100`/`0xfc098908`/`0xfc098008` writes behind the test-32
  hang. Of that block, only `0xfc098808 = 0x003e0007` remains.
- **Mode 5 polling:** cut from five samples to three (S0 to S2). P0 is
  still dumped. P4 is no longer dumped.
- **Mode `0x37` fallback:** if the 4.5 MiB buffer is all zero after
  Mode 5, the runner prints
  `MODE5 PIX nonzero=0 -> trying MODE37 ISP0_AIF3` and then:
  - stops RdcW0 and clears SGC1, SGC2, SGC3 and FOPD `0xfc0ad610`;
  - writes `dfe_still_clock_writes`, `dfe_still_setup_writes` and
    `imx284_still_pre_writes`, then sends `imx284_still_upload_0` and
    `imx284_still_upload_1`;
  - arms ISP0 AIF3: control 2, base `0x25200000`, line 12096, gap 0,
    rows minus one 359 (a 6048 × 360 strip within the 4.5 MiB buffer),
    then control 3;
  - sends `imx284_still_upload_2` and writes `dfe_still_start_writes`;
  - prints six `M37_S` samples, 100 ms apart, with AIF3
    control/status/error/cursor/base, SGC0 to SGC3, FOPD, the SLVS-EC
    monitors, ISP0 `+0x00/+0x08` and the sequencer state;
  - calls `analyze_and_maybe_dump("/tmp/bayer_full.raw")`, stops AIF3,
    and clears FOPD, SGC0 to SGC2 and the SLVS-EC enables.

The pixel statistics and the preview in `test_bayer_senser.py` assume
Mode 5 geometry: 1996 × 1122 at a 2016-pixel stride. A Mode `0x37`
strip uses a 6048-pixel stride, so that output would need a new
decoder.

#### Untested

- The runner edits above have not been compiled or run.
  `stage_rtos.py`, `bayer_capture.h` and `os_shell.c` were not changed.
- The planned next run, on a freshly booted camera with nothing run
  first, is:
  `.\.venv\Scripts\python.exe research\device\zve10_ram_boot\test_bayer_senser.py --out .local\out\senser-bayer-test-33-full --mode full`
- `.local/out/rtos-isp0-bayer-live-01/rtos.bin` (SHA-256 `35ce9444…a09a0cd`)
  is still unstaged. A possible fix for the `order:4` `boot.ko` failure
  is to run `sync`, `echo 3 > /proc/sys/vm/drop_caches` and
  `echo 1 > /proc/sys/vm/compact_memory` on a fresh boot before
  `insmod`. Neither has been tried.
- Never run `CAMERA_SCN_EE_START_STOP` (`--mode rdcw0`) after
  `--mode full` on the same boot.

#### Offline readback follow-up

The mode `0x37` fallback writes `/tmp/bayer_m37.raw` as 360 rows of
12,096 bytes. The USB host requires the save marker from the current run
and checks the reported and downloaded lengths before decoding. It records
the geometry in `report.json` and renders the two green sites in each
Bayer cell as a 3024 × 180 grayscale preview. Mode 5 keeps its 2016-pixel
stride and existing color preview.

The runner records whether ISP0 was busy, whether it went idle before
stop, the greatest in-buffer cursor offset observed, and the combined
error register values. A nonzero dump can still be a partial strip.
The runner checks that RdcW0 is idle before reusing its buffer for ISP0.
The host runs one experiment per invocation and defaults to `--mode full`.

Offline tests reproduced the 360-row register configuration through
Sony's original AIF helpers and exercised USB readback logic with a crop
from the saved stock RAW frame. This crop verifies the decoder.

#### Standalone ISP0 strip tests on the camera

| Run | Result |
| --- | --- |
| `senser-bayer-test-33-full` | USB terminal preflight passed. The command timed out before its completion marker and USB terminal cleanup failed. The host discarded partial output, so the last operation reached is unknown. |
| `senser-bayer-test-34-traced` | The logged retry completed the power-save wake, ran mode 5, and entered the mode `0x37` fallback. ISP0 AIF3 held control 3 and destination `0x25200000`. Busy stayed clear, the cursor and SLVS-EC input monitor stayed zero, and there were no nonzero pixels. |
| `senser-bayer-test-35-still` | Linux rebooted and the test ran within 23 seconds of startup. Added `--mode still` to skip mode 5 and arm ISP0 after the shared sensor wake. ISP0 still held control 3 without busy or cursor motion. The SLVS-EC input monitor stayed zero and there were no nonzero pixels. |

Both completed runs reported `CLEANED_IDLE`. Neither produced a strip.
Running mode `0x37` directly rules out the preceding mode-5 setup as the
sole cause of the failure. Stock mode `0x37` previously reached ISP0
control 2 with busy set and receiver input present. The next comparison
point is the sensor trigger and timing-generator startup before that
transition. Run records are under `.local/out/` using the names above.
The host now saves any terminal output collected before a timeout.

#### Native still request and capture arm

The still caller in `av-cam.bin` at `0x638ff754` calls the exposure
builder `0x63c04bf4`. The builder copies three words from firmware RAM
`0x6448139c + 0x184` into the shot's output record at `+0x0c`.
The caller copies those words into its capture context at `+0x750`.
Their initial values in the firmware file are zero. They need the
runtime exposure state to carry useful shot parameters.

At `0x638ff7aa` the still caller passes that descriptor and the context
byte at `+0x6874` to `0x637aae88`, with the last argument set to 1.
The wrapper reaches IMX284 vtable slot `+0x3c`, `0x637aca24`.
That routine consumes descriptor halfword `+0x02` and bytes `+0x06`
and `+0x0a`. It computes a value through `0x637ad74c` and passes it
twice to `0x63d2a9fe`, which patches the high and low command bytes.
The next still call at `0x638ff7b4` goes through `0x63d2a758` to vtable
slot `+0x44`, the readout routine `0x637ad06c`.

`extract_imager_profile.py --frame-request-hex` replays these last two
callbacks in order with an explicit 32-byte fixture. It initializes
the provider via `0x63d2b564` using the native `InitParam` at object
`+0x134`. With only request halfword `+0x02` varied across `0x012c`,
`0x0f00`, and `0x0fa0`, the request made no MMIO writes. It changed
bytes 40–43 of the subsequent 251-byte upload. The 45-byte and 124-byte
uploads stayed identical across those three cases. These values are
fixtures. The actual stock still descriptor has yet to be recovered.

The ISP arm has a separate call chain. CapController invokes the AIF
object at controller `+0x2c` through vtable slot `+0x10` at
`0x63d07d2e` or `0x63d07dd2`. The AIF table at `0x64587278` resolves
that slot to `0x63d0a846`, which loads the logical channel from object
`+0x20` and branches to `0x63da20f6`. The original wrapper arms the
port by setting control bit 0 when clear. The native AIF audit now
replays that concrete method using the confirmed port and strip geometry.

The DFE loader at `0x639daeb4` obtains the 65,536-byte image from
`0x639dfb38`. The local `dfe_dat.bin` matches the embedded bytes at
`0x64560700`. The external `/usr/dfe/dfe.bin` path is a fallback.
In the DFE image, ARM code at `0x0100030c` handles script events
`0x08` and `0x10`, then dispatches 12-byte records via `0x010001d4`.
The still-shot caller that publishes a script or establishes that this
handler participates in the shot remains unresolved. See the
[DFE image findings](../../firmware/zve10-session-2026-11/movie-bayer-audit/DFE-IMAGE-FINDINGS.md).

#### Where the still descriptor gets its exposure values

The same still task calls `0x63c047c8` at `0x638ff576`, before the
call that builds the sensor request. As part of preparing the shot,
`0x63c047c8` clears the `0x198`-byte exposure state at `0x6448139c`,
fills its inputs and calls the native exposure calculator `0x63bbe150`
at `0x63c04ab0`. The original stores take the output at stack `+0xd0`
and populate the shared exposure state that `0x63c04bf4` later copies.

| Calculator output offset | Exposure state offset | `SetImgRd` descriptor offset |
| --- | --- | --- |
| `+0x00` halfword | `+0x186` | `+0x02` |
| `+0x02` halfword | `+0x188` | `+0x04` |
| `+0x08` byte | `+0x18a` | `+0x06` |
| `+0x0c` halfword | `+0x18c` | `+0x08` |
| `+0x09` byte | `+0x18e` | `+0x0a` |

The calculator stores local halfwords `+0x36` and `+0x34` to output
`+0x00` and `+0x06`, respectively, and writes `0x1000 - local[+0x34]`
to output `+0x04`. The late override branches at `0x63bbe3fa` and
`0x63bbe412` can replace those locals from runtime byte pairs. The
imager audit executes the native result stores and both copies with a
known calculator-result fixture. The actual calculator inputs for a
stock exposure remain unknown.

The DFE image's normal and exception-return handlers are the direct
literal-load sites for script state `0x01036d00` in the local image.
Replaying the ARM handler verified that event `0x08` executes
`[0, first)` and event `0x10` executes `[first, last)` for valid bounds.
The host DFE post-start call at `0x638f5f7a` reaches
`0x63d73996 → 0x63d73666 → 0x6379c680`. An offline run using the
default resource `0x39` fixture (flags `0x01902111`) returned zero
without MMIO writes. Both output selectors returned zero for that
resource, which skips the timing-update branches. This narrows the
still trigger search. It does not bind the DFE script handlers to a
stock exposure.

#### Still task start order and ISP0 interrupt

The capture task at `0x638ff67c` contains the sensor readout, ISP arm,
and DFE start calls in one native function. Selected instruction ranges,
the IRQ entry, and the RAW publication wrapper match the saved body
`av-cam.bin` byte for byte.

| Call site | Native operation |
| --- | --- |
| `0x638ff6d6` | Apply the sensor mode through `0x6390b8fc`. |
| `0x638ff7aa`, `0x638ff7b4` | Supply the still descriptor to `SetImgRd`, then run IMX284 readout. |
| `0x638ff922` | Configure the capture controller using context token `+0x6ce8`. Configure DFE acquisition using token `+0x6cec`. |
| `0x638ff9c4` | Call imager slot `+0x74`. The implementation at `0x637ab558` waits for event group `0x18`, mask `0x100`, after any pending sequencer wait. The wake routine at `0x637ad440` sets that same mask. |
| `0x638ff9f4` | On the nonzero shot-index branch, resolve the controller token `+0x6ce8` and call its start slot `+0x0c`. The base CapController implementation reaches the ISP AIF arm via object `+0x2c` when byte `+0x91` is zero. |
| `0x638ffa36` | Start the DFE token `+0x6cec` via `0x638cf404 → 0x63d73588 → 0x63d23120 → 0x6379ab48`. This call follows the ISP start on the same branch. |

The sequencer and AIF audits execute the original event-wait and arm
instructions with fixtures. The latter shows that the controller
suppression byte gates the ISP0 write from control 2 to 3. The current
standalone loop arms ISP0 before submitting its last sensor burst.
The native sequence above supplies the per-frame request and calls
readout before acquisition configuration and the ready wait.

ISP0's IRQ 37 entry is `0x63d0fe38`. It reads and acknowledges the two
status banks at `0xf3000048` and `0xf300004c`. The `+0x48` path adds
the ISP0 tag `0x20000000` and calls `0x637772a0`, which invokes the
runtime subscriber when its full mask matches the tagged status. The
offline audit used subscriber mask `0x20008000`, combining the tag
and the mask stored by logical channel 3's constructor. The original
ISR acknowledges the status and only calls the fixture subscriber when
bit `0x8000` is present.

#### Native still callbacks and completion waits

The still capture setup at `0x63907340` passes two concrete callback
addresses to CamCore through `0x63771c30`. The controller's callback
setter at `0x63d08a6c` stores `0x63d88f91` at `+0x80` and
`0x63d88f71` at `+0x84`. The low bit of each address selects Thumb.

The controller allocation code at `0x637730c4` registers two wrapped
member callbacks against the event object at `ctl+0x48`. The object
constructor at `0x63777cec` installs vtable `0x64587668`, and the
ISP0 initialization at `0x63777770` supplies tag `0x20000000`.
Both entries use the normal IRQ status bank at `0xf3000048`.

| Registration call site | Callback table key | Callback chain |
| --- | --- | --- |
| `0x63773360` through slot `+0x08` | `0x24000000` | `0x63d08ea0` marks configured channels, moves the secondary callback from `ctl+0x84` to `+0x88`, and calls `0x63d88f90` through `ctl+0x80`. That callback sets event group `0x16`, bit `0x80`. |
| `0x63773336` through slot `+0x0c` | `0x28000000` | `0x63d0887e` runs channel cleanup and calls `0x63d88f70` through `ctl+0x88` when present. That callback sets event group `0x16`, bit `0x20000`. |

After DFE start succeeds, the still task stores wait mask `0x82` at
context `+0x6c04`. The cleanup task at `0x638ffb24` passes it to
`0x63906dbc` before releasing the CamCore and DFE tokens. The
inter-shot branch at `0x638ffa9c` waits for `0x20000` separately.
Both waits use group `0x16`. The channel 3 bit `0x8000` used by the
earlier IRQ audit does not invoke either of these two subscriptions.

The second bit in the still wait mask comes from the callback at
`0x63d88f54`, which sets group `0x16`, bit `0x02`. After starting
DFE, the still task calls `0x63907474` with selector 1. That case
wraps this callback and `0x63906ed4` and passes both records to
`0x638d146c`. Its capture-controller call goes through
`0x63d1068a` to `0x63778410`, which binds the callback records and
configures the shared ISP event object. The shared ISP IRQ 36 handler
at `0x637777c0` reads status at `0xf3120048` and dispatches through
the same subscriber table using tag `0x10000000`.

`audit_dfe_acquisition_dispatch.py` executes the original ISP0 event
object initialization, callback setter, subscription block, IRQ
handler, and wait wrapper with fixture controller and IRQ state.
It checks the two native table entries and verifies that sequential
status bits `0x04000000` and `0x08000000` set `0x80` and `0x20000`
respectively. The shared ISP replay below covers the group-`0x16`
bit-`0x02` path. The fixture substitutes the OS lock, trace,
event-set, event-clear, and event-wait services. The registration block, callback bodies,
and still setup bytes also match the saved `av-cam-body.bin`.

#### Factory RAW publication on the final capture-work release

Sony's factory command selector at `0x63927268` reads the command and
block from the record at request `+0x5c`. For block `0x404` and command
`0x4e`, it selects capture kind 2 at `0x6392759a`. The default branch
at `0x63927450` computes the Thumb callback `0x63d8fd53` from a
PC-relative literal. This is why searching for the absolute callback
pointer in the image found no reference.

| Address | Operation |
| --- | --- |
| `0x63927456` | Initialize the callback record through `0x63d799e6` and `0x638db77c`. The record stores the callback trampoline at `+0x00` and the Thumb target at `+0x08`. |
| `0x638dcc94` | Store capture kind 2 at `0x643b2de4+0x10` and copy the 20-byte record to `+0x14`. The publisher pointer ends up at `0x643b2e00`. |
| `0x638db916` through `0x638db94a` | The capture setup takes the registered callback from request view `+0x0c`, copies it into the setup stack, and passes it to capture-work constructor `0x638d95a4`. |
| `0x638d95a4` | Copy the record to capture work `+0x08`. Set its reference count at `+0x04` to 1. The capture-work vtable is `0x6458bc98`. |
| `0x638d963c` | The vtable release method at slot `+0x0c` decrements the count. A zero count reaches `0x63d79376 → 0x63d798c4`, which calls `0x63d8fd52` with the capture context. |
| `0x63d8fd52` | Call `0x63926fe0` with slot index 0, then run `0x638d933c`. The publisher takes the handle from context `+0x67b0`, retains it, opens the DMM extent, and publishes the descriptor before capture cleanup runs. |

Stock samples show the ISP0 writer and ISP1 reader completing before
the descriptor is published. The native still cleanup waits on group
`0x16` before releasing the CamCore and DFE tokens. RAW publication
comes from the final capture-work release. The exact scheduler call
that drops the last reference after the still cleanup task is still
unidentified.

The offline replay now executes the factory selector with a
`0x404/0x4e` fixture, the request enqueue routine, the capture-work
constructor, and the native virtual release. It verifies that a
nonfinal release preserves the source handle and the final release
publishes it. The replay supplies camera-ready state, memory allocation,
OS locks, and DMM replies as fixtures. It does not exercise the
live task queue or produce a new sensor frame.

From the repository root, run these two checks.

```powershell
.venv/Scripts/python.exe research/device/zve10_hardware_map/audit_dfe_acquisition_dispatch.py .local/dumps/av-cam.bin
.venv/Scripts/python.exe research/firmware/zve10-session-2026-11/movie-bayer-audit/verify_still_raw_handoff.py .
```

#### Where to resume

- **Shared ISP completion.** The IRQ 36 and selector-1 path has now
  been replayed. See the 23 November offline follow-up below for the
  two status banks and the callback order.
- **DFE script service.** The stock host acquisition entry is
  `0x6379ab48`. The ARM services at `0x0100030c` and `0x01000778`
  consume shared records at `0x01036d00` for pending bits `0x08`
  and `0x10`. Their participation in this shot is still open. The
  next offline check is to replay the unmodified mode-`0x37`
  resource start and look for a command-record write and a trigger
  for either bit. Check host alias `0xfc036d00` as well as
  indirection through shared-memory transfers. The status/mask
  operations at `0x63d25dfc` and `0x63d25e24` alone are not evidence
  of a submitted script.
- **Standalone RTOS.** Keep the stock Senser RAW frame as the reference
  fixture. The standalone loop still needs the per-frame sensor
  descriptor and stock readout order from the sections above. There
  is no newly verified standalone Bayer capture or flashable build
  from this offline trace.

---

## 23 November follow-up (Rizin/`pdg` DFE trace, `test-45`..`test-47`, `stock-reg-diff-03`)

### 1. Rizin + Ghidra (`pdg`) findings on `av-cam.bin` (`base=0x635C6000`)

Cutter's Rizin 0.9.1 on PATH includes `pdg`. The standalone Rizin
configured in `reconf.toml` lacks the plug-in. On this Thumb image,
the default Sleigh language truncated the cleanup tail branch.
The Cortex language recovered the publisher call and cleanup loop.

```powershell
rizin -N -q -a arm -b 16 -m 0x635c6000 -c "e ghidra.lang=ARM:LE:32:Cortex;s 0x63d8fd52;af;pdg" .local/dumps/av-cam.bin
```

- **`0xfc0a0200` (W1S) / `0xfc0a0204` (W1C) pair:** `0x63d2509c` (`arg1 + 0xa0200 = arg2 << 4`) and `0x63d250aa` (`arg1 + 0xa0200 = arg2 << 5`) write bit-set enables in `0x637a24d4`, while `0x637a25f0` / `0x637a25fc` (called from `0x637a264c`) write the same bit positions to `0xfc0a0204` to clear them (`0x637a2038`, `0x637a2044`, `0x637a2050`, `0x637a2b08` also write `0xfc0a0204`). Both addresses read back the same live mask (`0x00000011` in active `EE`), so writing `0xfc0a0204 = 0x11` clears what was just enabled in `0xfc0a0200`.
- **`0xfc0a0000` (W1S) / `0xfc0a0004` (W1C) pair:** `0x6379e840` (via `0x63d23ab8(bit)`) writes `1 << bit` to `0xfc0a0000`; `0x6379e850` (via `0x63d23ac2(bit)`) writes `1 << bit` to `0xfc0a0004`.
- **DFE / SGC0 / `0xfc080` / `zpdctl` / CRG call chain:**
  - `0x63d73502 -> 0x6379cb68 -> 0x6379a510 / 0x6379a57c` drives the `0xe8`-byte DFE module table (including `0x6379e2b8 -> 0x63d264ac / 0x63d263b0`, `0x63d260ee -> 0x63d25f9e` targeting `0xfc0a1520` after `0x63d25f30` writes `0xfc0a1500 = 1`), and `0x63d735f8 -> 0x63d73644 -> 0x6379ce58 -> 0x63d26acc` + `0x637a4278` configures and triggers SGC0 (`0xfc0a1120/1124/112c/1130/1108/1110`, `0xfc0a1194/98/9c/a8/ac`).
  - `0x6379c994` (in vtable `0x64588a28`) calls `0x63d238b2 -> 0x6379e6c4` (`0x6379e490`, `0x6379e594` on `0xfc021024`, `0x63d2388e`), `0x6379ed04 -> 0x6379cfdc(0xa/0xb)`, `0x63d267a4`, `0x63d26a42`, `0x637a3858` (arbiter init including `0x637a37f8 -> 0xfc080030` and `0xfc080020`), and `0x6379a478 -> 0x6379b054`.
  - `0x639df964(1)` invokes `0x6379cfdc(9)` (`0xfc01f168`), `0x6379cfdc(3)` (`0xfc01f144`), `0x6379d158(0x20000)` (`0x637a4738 -> 0xfc098908`), `0x6379cfdc(0xe)`, and `0x63d23300(1)` (`0x63d25e4e`).
  - `0x63a26438` (`clk_enable`) / `0x63a25914` (`clk_disable`): `case 0x4e` controls `0xf2a30030` bit `0x800` and `0xf2a300b0` bit `0x08000000`; `case 0x38` controls `0xf2a30030` bit `0x08000000`.

### 2. Live hardware runs (`test-45`..`test-47`, `stock-reg-diff-03`)

| Run | Change tested | Key observed output | Outcome |
| --- | --- | --- | --- |
| `test-45` | Added `0xfc0a0200 = 0x01, 0x10` + `0xfc0a0204 = 0x11` before `dfe_mode5_clock_sgc_writes` | `P0_CLK 1e=08310000 8030=00fffffc 80f4=0012541e a0200=00000000 a0204=00000000` (proving `0xfc0a0204` cleared `0xfc0a0200`); `I=6 T=1`, `SGC0..3=00000001` | `PIX nonzero=0` |
| `test-46` | Removed `0xfc0a0204 = 0x11` write | `a0200=00000011 a0204=00000011`, `fc0a0200=00000011`, `fc0f0080=0000000f`, `fc0f0180=0000000f`; `I=6 T=1`, `SGC0..3=00000001`, `M37` `SGC=00000001:00000001:00000001:00000001` | `PIX nonzero=0` |
| `test-47` | Added `0xf2a30038 = 0x08000000` after `imx284_wake_post_writes` | `a330=147fffff a000=0000b1fa` (`0xf2a30030` matches active `EE`); `I=6 T=1`, `SGC0..3=00000001`, `M37` `SGC=00000001:00000001:00000001:00000001` | `PIX nonzero=0` |
| `stock-reg-diff-03` | Clean `reboot -f`, then `4088`-reg `dump` in `idle` vs `CAMERA_SCN_EE_START_STOP b:1 b:1` | `84` diffs written to `.local/out/stock-reg-diff-03/diff.txt`; newly covered blocks found `0xfc01f310` (`0 -> 0xe`) and `0xfc0a11a8` (`0x026b0000 -> 0x026b0001`, vs `0` in `bayer_sensor_tables.h:169`) | Active `EE` `0xfc0a1110=00010001` |

### 3. Current workspace state & resume notes

- **Unstaged debug changes in `senser_bayer_runner.c`:** `test-48` is currently staged (not yet run live because the camera disconnected from USB after `stock-reg-diff-03`): sets `0xfc01f310 = 0x0000000e`, `0xfc0a0200 = 0x00000001 / 0x10`, `0xf2a30038 = 0x08000000`, adds conditional `SGC0_172=` (`0xfc0a0004 = 0x0000b088`) and `SGC0_ACT=` (`0xfc0a1120/1124/11a8`) probes when `SGC0` bit 16 stays `0`, adds extended `dump_regs_bin` + `dump PATH` CLI mode, and still carries `P0_CLK` logging and unused `slvsec_relock_mode5` (remove temporary probes/warning once capture works).
- **Remaining diffs (`regs_act.bin` in `stock-reg-diff-03` vs `test-47`):** `0xfc01f310`, `0xfc080030`/`0xfc0800f4`, `0xfc098280`/`290`/`2a0` & `0xfc099110`, `0xfc0a0000` (`0x0172` vs `0xb1fa`), `0xfc0a0010`/`0028`, `0xfc0a0150`/`154`/`178`/`180`, `0xfc0a1120`/`1124`/`11a8`, `0xfc0a1358`/`135c`, `0xfc0a39xx`/`3axx`, `0xfc0ad6xx`, and `0xfc0f00xx` (note `0xfc0f00b0=1` awaits packets).
- **Next step when camera reconnects:** Run `test_bayer_senser.py --out .local\out\senser-bayer-test-49 --mode full` to observe `test-48`'s `SGC0_172` / `SGC0_ACT` / `1f310` results. If `SGC0..3` still stays `0x00000001`, either diff unscanned MMIO blocks from `av-cam.bin` (`0xf200..0xf2ff`, `0xfc00..0xfc01`, `0xfc02f..`, `0xfc03..0xfc07`) on a fresh boot or check whether `SGC` clock/enable is issued by Core 1 / another peripheral block not yet mapped in `init_regions`.

### 4. Offline follow-up on SGC0 and the shared ISP completion

Rizin PDG with `ghidra.lang=ARM:LE:32:Cortex` led to the SGC0 timing
routine at `0x63d26acc`. Its caller `0x6379ce58` loads the first
timing dimension from request `+0x38`, the second from `+0x3c`
with an optional multiplier from `+0x18`, and the signed offset
from byte `+0x40`.

| Register | Native programming |
| --- | --- |
| `0xfc0a1120` | The first timing dimension minus one occupies bits 16–29, and the second minus one occupies bits 0–13. |
| `0xfc0a1124` | The first timing dimension minus 101. |
| `0xfc0a11a8` | The signed offset controls bit 0. Zero clears bit 0 and preserves the high timing field. A nonzero offset sets bit 0 and writes the first timing dimension minus one plus the offset into bits 16–29. |
| `0xfc0a1110` | The start helper requests start via bit 0. The getter at `0x637a3f60` reads bit 16. |

The original timing routine reproduces both sets of words from
`stock-reg-diff-03` when given inputs reconstructed from the register
fields. Using timing inputs `840, 1430, 0` reproduces idle
`03470595 / 000002e3 / 026b0000`, with the high `11a8` field
retained from the fixture. Inputs `619, 1940, 1` reproduce active
`026a0793 / 00000206 / 026b0001`. These are SGC0 timing inputs.
The capture data does not establish the whole source request.

The caller applies timing **before** calling `0x637a4278`. For
selector 1 and start argument 0, the native replay writes
`0xfc0a112c = 0`, clears bit 16 at `0xfc0a1130`, clears bit 0 at
`0xfc0a1108`, then sets bit 0 at `0xfc0a1110`. The fixture provides
a controller state check that returns zero. It cannot model the
hardware transition of bit 16. Test 48 currently writes the active
timing words in its diagnostic fallback **after** a start attempt.
That fallback still differs from the stock order. When comparing the
probe to the stock call chain, check the timing words and the four
start writes in order.

The same offline audit runs the real selector-1 callback builder,
native shared ISP registration, and the IRQ 36 handler. It supplies
a controller fixture and timing arguments at the setup boundary.
Both status banks register bit 0 with shared ISP tag `0x10000000`.
Normal status bit 0 at `0xf3120048` calls `0x63778338`, which moves
the completion callback from controller `+0x64` to `+0x78` and
invokes the other callback at `+0x50`. Alternate status bit 0 at
`0xf312004c` calls `0x63d10660`, which invokes and clears the
parked completion callback. That path sets group `0x16` bit
`0x02` via `0x63d88f54`. The replay verifies that alternate-only,
an unrelated normal bit, and a repeated alternate after consumption
do not set the event.

Both checks are in `audit_dfe_acquisition_dispatch.py`. Neither
replay establishes sensor packet arrival on hardware. The staged
probe has not been run as part of this follow-up.

### 5. Live Senser runs 49 and 50

Both runs reached `CLEANED_IDLE`. Run 49 exercised the staged probe
and confirmed that `0xfc01f310` read back `0xe`. Both the DFE mask
change and the diagnostic late SGC0 timing writes left the SGC0
status at `0x00000001`.

Run 50 removed the early mode-5 SGC0 start from the clock table,
moved the active EE timing before the explicit start, and used the
four selector-1 writes verified in the offline audit. The camera
read back timing `026a0793:00000206:026b0001` and `112c=0`.
The SGC0 active bit stayed clear in both samples. In both runs the
mode-37 ISP0 writer reported `busy_seen=0`, `peak_offset=0`, and
`PIX nonzero=0`. Neither run produced a Bayer frame.

Logs and machine-readable reports are under
`.local/out/senser-bayer-test-49` and `.local/out/senser-bayer-test-50`.
The live comparison leaves the clock or input gating that precedes
the SGC0 status transition unresolved.

### 6. ZVOS repeated still readout order

The `BayerRAW` capture loop now submits the complete mode-`0x37`
readout sequence on each shot. It sends the 251-byte and 45-byte
bursts through software run mode 2, queues the 124-byte burst in
frame-synchronous mode 0, configures ISP0 AIF3, then arms the writer
and starts DFE. The previous loop sent the first two bursts during
initialization and sent only the last burst after each ISP0 arm.
The standalone code still uses the existing recovered burst bytes.
The stock exposure-specific `SetImgRd` descriptor and hardware-ready
signal remain open.

`verify_bayer_capture.py` checks the three uploads and their run
modes before every modeled ISP0 arm. It also exercises repeated DMA
completion, the CPU resize and LCD flip, and exit during a busy
transfer. The shell verifier passed as well.

The candidate is `.local/out/rtos-bayer-still-order/rtos.bin`
(28,792 bytes, SHA-256
`3f245920702d53ad7f65a4c84c1c27d9bffe92d10c9d89a851bf10029c627941`).
The first camera attempt hit an order-4 allocation failure in
`boot.ko`. The staging script restored the previous payload and
verified the restoration by readback.

On a later USB session with about 24 seconds of camera uptime, the
loader allocated its 64 KiB arena, loaded the candidate and reached
`READY`. The retry performed `sync` and dropped caches. This kernel
does not expose `/proc/sys/vm/compact_memory`. The module accepted
`GO` and USB detached. The owner confirmed BayerRAW displayed an ISP0 timeout. Screen
corruption obscured the other status rows. The reports are under
`.local/out/stage-bayer-still-order` and
`.local/out/try-bayer-still-order-02`.

### 7. Timeout snapshot

The diagnostic build reads the ISP0 writer, SLVS-EC monitor, SGC0
and SGC2, and shared ISP interrupt status before stopping the writer.
It distinguishes an observed but incomplete DMA transfer from one
whose busy bit was never observed. The four rows below the timeout
message show these values in hex.

| Row | Left to right |
| --- | --- |
| DM | ISP0 control, ISP0 status, highest observed byte offset |
| RX | SLVS-EC `0xfc0f00ac`, SLVS-EC `0xfc0f00b0`, SGC0 control/status |
| IQ | SGC2 control/status, shared ISP normal status, shared ISP alternate status |
| WR | ISP0 DMA cursor, ISP0 error word, sequencer timeout count |

The normal and `--no-dma` Bayer capture checks and the ZVOS shell
check passed. The diagnostic candidate at
`.local/out/rtos-bayer-timeout-diag/rtos.bin` reached `READY`
and accepted `GO` on the camera. The staging log is
`.local/out/try-bayer-timeout-diag-01/stage.json`. Hardware
register values from the new screen have yet to be observed.
