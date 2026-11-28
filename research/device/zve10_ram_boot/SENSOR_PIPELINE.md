# Sony ZV-E10 Sensor Readout Pipeline (`av-cam.bin` RE + Hardware Verification)

> Canonical summary & cross-system map: [docs/hardware/SENSOR_PIPELINE.md](../../../docs/hardware/SENSOR_PIPELINE.md) · [BAYER_HANDOFF.md](BAYER_HANDOFF.md)

**Target:** Sony ZV-E10 (`CXD90057` SoC + `IMX284` 6048x4024 Bayer sensor)  
**Primary binary:** `.local/dumps/av-cam.bin` (`base=0x635c6000`)  
**Reference captures:** `stock-reg-diff-04/{regs_idl.bin,regs_act.bin,regs_stp.bin,diff.txt}`, `stock-trace-ee-02`, `sgc0-factory-passive-01`, live dump `/tmp/rd2.bin`

---

## 1. Causal Bring-Up Order (`stock-trace-ee-02`, Mode 1 LiveView)

Stock EE brings up sensor timing, SPI streaming, and SLVS-EC link **before** enabling `DfeTop`, `Crossbar`, `IFMT`, or `RDC`:

| Timestamp | Phase | Verified Hardware Events & Registers |
| --- | --- | --- |
| `548.930 ms` | **1. Pre-arm & sensor wake** | `0xfc08010c` clears bit 0 (`3 -> 2`). `MPHY/PHY` set (`0xfc02a008=0x1101`, `0xfc02a06c=0x0012007c`, `0xfc02a080=0x0`, `0xfc02d00c=0x11`, `0xfc02d010=0x1`). `0xfc0a0000` held at `0x160`. `IMX284 wake` (`0x637ad310`) drives `0xfc029028: 0x70 -> wake_0 (12 ms) -> wake_1/2 (6 ms) -> 0x7e (20 ms)`. |
| `682.554 ms` | **2. SyncSeq, SGC0 & `mode_2` SPI** | `0xfc0800f4 = 0x00012ac8`, `0xfc080028 = 0x00fffffc`, `0xfc080030` steps `0x00fffffc -> 0x0012542e -> 0x0012542c`. `SGC0` Mode 1 (`1120=0x026a0793`, `1124=0x0206`, `11a8=0x026b0001`, `11ac=0x00110061`) activates: `0xfc0a1110 = 0x00010001` **while `DfeTop` is still off**. `IMX284` receives `mode_2` SPI (`0x0832=0x03`, `0x03`, `0x00` ...) synchronized to active XVS/XHS. |
| `694.125 ms` | **3. SLVS-EC RX Lock** | `0xfc0f00b0` transitions to `1` (`+11.6 ms` after `SGC0` active, `18.7 ms` **before** `DfeTop`/`IFMT`/`RDC` turn on). |
| `712.864 ms` | **4. `DfeTop`, Crossbar & DMA** | `0xfc0a0000` switches `0x160 -> 0x172` (`0x160 | 0x02 | 0x10`), `0xfc0a0200/04 = 0x11`, Mode-1 crossbar (`0xfc0a0150=0x02000000`, `0xfc0a0178=0x00020000`), `0xfc0a0560/64 = 0xffff`, and `IFMT`/`RDC` (`0xfc0a1200/1300=1`) enable frame readout. |

---

## 2. Firmware Functions Verified in `av-cam.bin` (`rizin`)

- **IMX284 power-on (`0x637ad800`), wake (`0x637ad310`), and power-off (`0x637ab9fc`)**
  - The wake handler sets `0x14/0x16/0x15` -> `0xfc029028=0x70`, uploads `wake_0` (`0x63eb3abe`), waits `12 ms`, uploads `wake_1` (`0x63eb3d24`) & `wake_2` (`0x63eb39c2`), waits `6 ms`, sets `0x12/0x11/0x13` -> `0xfc029028=0x7e`, waits `20 ms`.
  - Calls `0x637aeae0` / `0x637aebd0` -> `0x637a8320..0x637a850c` to configure `0xfc0f0000..01c4` (`SLVS-EC` RX).
- **Per-mode `IMX284` SPI tables:**
  - Mode pointer arrays at `0x645bc738` and `0x645bc804` index into the packed `(u16 reg, u16 val)` pool at `0x6461861e..0x64618916`.
  - Live `stock-reg-diff-04/regs_act.bin` dumps the runtime `.data` shadow (`0x0461861e..0x04618918`) and assembled Mode-1 P2S bursts (`0x0426b61c..0x0426b697` = `mode_2`, `0x0426b698..0x0426b717` = `upload_0[0x7c:]`; last uploaded `mode_2` FIFO sits at `0xfc088340..`).
  - `Mode 1` differs from `Mode 5` by 20 bytes in `upload_0`, 2 bytes in `upload_1`, and 18 bytes in `upload_2` (including `0x0832 = 0x03, 0x03, 0x00` and `0x0021..0x004e`, `0x099c = 0x07`).
- **`SGC0` (`0xfc0a11xx`) & `SyncSeq` (`0xfc0800xx..0114`):**
  - `0x6379cb68` (`DfeCore_Start`) -> `0x6379a57c` -> `0x6379a478` -> `0x6379b898`; timing caller `0x63d735f8` calls `0x6379ce58` at `0x63d73644` -> `0x635c8628` (`0xfc080028=0x00fffffc`, `0xfc0800f4`), `0x63d26acc` (`1120 = (H-1) | ((V-1)<<16)`, `1124 = V - 0x65`: Mode 1 `0x26b x 1940` -> `0x026a0793` / `0x0206`; Idle `0x348 x 1430` -> `0x03470595` / `0x02e3`), `0x637a4278` (`112c`, `1130[16]`, `1108[0]`, `1110[0]`), and `0x637a3f5e` / `0x63d267f2` (`1110[16]` RO active bit).
  - `0x63d25e24` / `0x63d25e4e` / `0x63d25e78` manage `0xfc080104` (W1C), `0xfc080108` (mask), and `0xfc080110/114` (`0x637a381c..0x637a3854`).
- **`DfeTop` Crossbar (`0x6379df58`, table `0x63f6760f`):**
  - Mode 1 routes `0x01 -> 0x1b`: `0xfc0a0150 = 0x02000000`, `0xfc0a0178 = 0x00020000`.
  - Mode 15 (`0x2f`) routes `0x03 -> 0x1c`: `0xfc0a0154 = 0x40000000`, `0xfc0a0180 = 0x00010000`.

---

## 3. Mode-1 Runner Changes Before the Cold-Only Test

Six divergences identified in `bayer_sensor_tables.h` and `senser_bayer_runner.c` have been corrected for Mode-1 bring-up (`bayer_test` compiled cleanly to `41116` bytes):

1. **Fixed stale `dfe_mode5_pll_phy_writes` (`MPHY/PHY`):** updated `0xfc02a008` (`0x1 -> 0x1101`), `0xfc02a06c` (`0x7c -> 0x0012007c`), `0xfc02a080` (`0x1 -> 0x0`), `0xfc02d00c` (`0x13 -> 0x11`), `0xfc02d010` (`0x0 -> 0x1`).
2. **`SyncSeq` pre-arm & Mode-1 period:** added `0xfc080100=0x1ff`, `0xfc080104=1`, `0xfc080108=2`, `0xfc080114=1`, `0xfc080028=0x00fffffc`, `0xfc0800f4=0x00012ac8`.
3. **`DfeTop` phased clock enable:** Phase 1 sets `0xfc0a0000 = 0x160` (`0x40|0x20|0x100`, without premature `0x8000`); Phase 4 sets `0xfc0a0000 |= 0x12` (`0x172`) before `0xfc0a0200 = 1; 0x10` (`0x11`).
4. **Preserved `0xfc0a0560/64 = 0xffff`:** replaced `dfe_mode5_setup_writes` (which wrote W1C `0xfc0a0564=0x1c0 -> 0xfe3f`) with `dfe_mode1_setup_writes` matching `regs_act.bin` Mode-1 `IFMT`/`CROP`/`Crossbar`.
5. **Removed mode mismatch (`Mode 1 / 5 / 15`):** added exact `imx284_mode1_upload_0/1/2` extracted from `stock-reg-diff-04/regs_act.bin` alongside Mode-1 `SGC0` and Mode-1 crossbar.
6. **Corrected `upload_2` causal ordering:** `run_full` now runs `mode1_upload_0/1`, starts `SyncSeq` + `SGC0` (`1110|=1`), and sends `mode1_upload_2` (`mode 0`) **after** `SGC0` starts, before enabling `DfeTop`/`IFMT`/`RdcW0`.

## 4. Standalone Mode-1 Hardware Test (2026-11-27)

The 42,688-byte static ARM runner completed the `--cold-only` path in
`.local/out/cold-warm-exp-05`. That path skipped the scenario preview commands.
The initial dump showed an idle RdcW0, a clear SGC0 start/status word, and
an empty Bayer buffer. The camera had already been up for about two hours
when the test started. These are results from a cold pipeline state.

| Stage | Observed on the camera |
| --- | --- |
| CRG2 | `0xf3400060` and `0xf3400260` were both zero at entry, latched `0x15` after the reset/clock writes, and retained `0x15` at P0 and after cleanup. |
| CRG0 and SLVS-CRG | Writing `0x0c` to `0xf3000014` and `0x02` to `0xf3120014` gave reset readbacks of `0x03` and `0x01`. Both `+0x38` registers use `0x00000100` during enable and returned `0x00010100` after cleanup. |
| DfeTop | Setting bits `0x12` on top of the existing core clocks yielded `0xfc0a0000 = 0x31fa` at P0. Writing the enable bits to `0xfc0a0200` yielded `0x11` at both aliases. The runner writes the clear alias `0xfc0a0204` during shutdown, and both aliases read zero after cleanup. |
| SyncSeq, SGC0 and SLVS RX | `0xfc080030` stayed at `0x00ee466c` despite `0xfc0800f4 = 0x00012ac8`. `0xfc0a1110` stayed at `0x00000001` through all polls, leaving bit 16 clear. `0xfc0f00b0` stayed zero and the frame-synchronous SPI burst timed out. |
| RdcW0 | The destination was `0x25200000`. The cursor stayed zero through five polls, and the cleared buffer contained zero nonzero pixels. |

The prior live P0 dump in `cold-warm-exp-04/log.txt` already showed the
SGC1/2 enables, Mode-1 crossbar pair `0x02000000` / `0x00020000`, and
SLVS pattern configuration `0080=0x0f`, `0098=0xaa`, `00a0=0x55`,
`00a8=1` before cleanup. The current runner also programs
`0xfc098808/0c = 0x003e0007` before starting the writer. The live FOP
readback still differs from active stock at `0xfc0ad608/18` even though
`0xfc0ad600` is enabled. Whether the FOP difference is downstream of the
missing input is unresolved.

The stock CRG2 switch case at `0x63a2660a` issues the same `1, 4, 0x10`
reset-then-clock sequence for the `0x60` pair. The diagnostic routines
around `0x63a24a80` and `0x63dbbd7a` did not establish a writer or
monitor mapping for `0xf340203c`. It remained `0x6978` in the test,
compared with `0xb4c6` in the stock warm references.

The harness initially rejected its sync and reboot commands before sending
them. The owner restarted the camera, and USB enumeration returned to
`PID_0D95`. The harness now registers the sync command and sends reboot
after sync succeeds. Subsequent sessions confirmed sync returned zero, and
the next sessions showed fresh camera uptimes after the reboot.

## 5. SyncSeq and DfeTimer Follow-up

The cold-only sessions in `.local/out/cold-warm-exp-06` through
`cold-warm-exp-13` recorded boot uptime and downloaded the live P0 dump.
The shortest completed run started at 20.53 seconds of uptime. Every
completed capture attempt returned zero pixels. Two attempts stopped in the
USB terminal before running the capture and were retried.

- Retool disassembly at file offset `0x75fde4` confirmed that the stock
  software pulse writes `0xfc080014 = 1`, `0xfc080028 = 0x40`, then
  `0xfc080014 = 0`. Trials before SGC0, after releasing CRG resets early,
  and with the frame-synchronous SPI burst queued all left `0xfc080030`
  at `0x00ee466c`. The programmed value at `0xfc080028` read back
  correctly. The experimental pulse and early reset ordering were reverted.
- A software-triggered final SPI upload raised the completion count from
  six to seven, while SGC0 bit 16 and SLVS RX lock stayed clear. The runner
  retains the frame-synchronous upload.
- The Mode-1 runner now uses the stock SyncSeq interrupt configuration
  (`0xfc080108 = 0`, auxiliary event bit 0 enabled), and stages the sensor
  GPIO at `0x7f` for the wake uploads before applying `0x77`. The live
  dump confirmed the stock SyncSeq mask and raw status. These changes
  did not make SyncSeq advance.
- Decompiled DfeTimer start and stop helpers (`0x637a4588`,
  `0x637a4594`, and `0x637a45ac`) confirm that `0xfc098808` sets
  bits and `0xfc09880c` clears them. The runner now clears its bits at
  shutdown. Experiment 13 read `0x00020001` at both aliases during capture
  and zero at shutdown. Active stock reads `0x003e0007` while the timer
  runs, and bit 17 of `0xfc098908` is set. The standalone run still read
  zero at `0xfc098908`.

## 6. SGC0 Reset, Timing Source, and RdcW0 Routing

Retool and the native instruction replay resolved the call after the
SyncSeq pulse at `0x6379cf40`. Stock disables SGC0, clears core enable
bit 8, toggles clock gate bit 6 at `0xfc021024`, and re-enables SGC0.
Experiment 14 reproduced that reset on the camera. SyncSeq stayed frozen.
Experiments 15–18 also reproduced stock's `0x3088 -> 0x309a` DFE masks,
held the software pulse for 25 ms, tried all six selector and flag
combinations accepted by `0x637a4278`, and tried starting SGC0 before the
wake uploads. None raised SGC0 bit 16. Experiment 19 preserved the
GPIO bit seen in the stock power trace and got the same result.
These experimental changes were reverted.

The DFE auxiliary image has an interrupt-enable path for `0xfc01e010`
and uses the adjacent `0xfc01e01c` register to acknowledge events. A
change in `0xfc01e010[21]` alone cannot establish a clock transition.

The Mode-1 setup table now uses the Ifmt-to-RdcW0 crossbar from native
resource `0x2f`. The previous preview route programmed
`0xfc0a0150/0178` and omitted the RAW route. The native replay writes
`0xfc0a0154 = 0x40000000` and `0xfc0a0180 = 0x00010000`.
The writer now derives its 3,992 active bytes, 40-byte gap, and
1,122 rows from the same constants as the host analyzer. The native
layout verifier programs `0x461` for 1,122 rows.

The final cold-only test (`.local/out/cold-warm-exp-21`, uptime
25.32 seconds) verified both crossbar writes and the four DMA geometry
words at P0, including destination `0x25200000`. The DMA cursor stayed
zero, and the post-run dump showed the writer disabled. Sync succeeded
before the harness sent reboot.

Standalone capture remains open. The live counter at `0xfc080030` is
the earliest measured divergence even when its configuration matches
stock. The remaining measurement is the sensor clock or frame-input
transition before the SGC0 active bit, ideally on a stock start and a
standalone start with the same initial state. The RdcW0 port cannot
verify the new route end to end until upstream data arrives.

## 7. Native Mode-1 Initialization Trace

Retool's `disasm` and its Rizin backend's Ghidra decompiler (`pdg`)
were checked side by side. The decompiler shows the branches and calls.
The Thumb instructions resolve register widths, literal addresses, and
call arguments where the decompiler's recovered types are unreliable.
Offline replay uses the IMX284 constructor and native Mode-1 parameter
lookup with OS and hardware responses stubbed. Live register
transitions come from the existing stock and standalone captures.

### DFE clock and SyncSeq defaults

`0x6379c994` loads the DFE init parameters and calls
`0x63d238b2(1, 1, 72)` for the CRG setup. `0x63d272d4` writes
`0xfc098800 = 2, 1` in sequence. `0x6379ed04` then selects the DFE pins.
`0x63d267a4` clears `0xfc021024[6]`, writes `0x100` to the DFE core
set alias at `0xfc0a0000`, and writes `0xfc0a1100 = 1`.

The next call is `0x63d26a42(0x6426ae54, 72, 3, 32, 4)`.
Its ordered writes in the replay, using offsets from `0xfc0a0000`, are
`1140=7`, `114c=4`, `1140=0x40007`, `1150=5`, `1150=0x250005`,
`110c=1`, `1198=0x10000`, and `1194=0x10000`. Several of the resulting
values come from read-modify-write operations.

`0x637a3858(72)` stores the clock at `0x6426b1e0`, writes `0x10` to
`0xfc08003c/54/6c/84/9c/b4/c4/d4/e4/f4`, clears only
`0xfc08001c[23:16]`, and writes `0xfc080020 = 0x00fffff0`. DFE IRQ
setup follows. The separate pin callback `0x639df964` with its second
argument set to 1 enables the auxiliary SyncSeq event through
`0x63d23300` and `0x63d25e4e`. That helper acknowledges the newly
enabled bit at `0xfc080110` before updating the mask at `0xfc080114`.

### SLVS-EC RX and sensor wake

The sensor rail sequence is in `0x637ad800`. In the subsequent wake
handler `0x637ad310`, the native wake profile enters `0x637aeae0` and
then `0x637aebd0` before the first sensor SPI FIFO upload.

| Order | Native code | Operations |
| --- | --- | --- |
| 1 | `0x63d2a15e` → `0x637a74e0` → `0x63d2a04a` | Bring up the ComboPHY, write `0xf292a074 = 0x100`, request a 100 µs wait, then configure the AFE. |
| 2 | `0x637ae818` | Write `0xfc02d00c = 0x13` and `0xfc02d010 = 0`, request a 1 µs wait, then write `0xfc02d00c = 0x11` and `0xfc02d010 = 1`. Both waits use synchronous OS service `0x910041`. |
| 3 | `0x63d2a240`, `0x63d2a274`, `0x637a7e78`, `0x637a7c34`, `0x637a7d70` | Set `0xfc02a008` from `0x101` to `0x1101`, configure both lane groups, stop the receiver and set the port and lane defaults. |
| 4 | `0x637aebd0` | Disable both ports, reprogram the lanes and release the receiver in stages. `0xfc0f0000` advances through `0x01000000`, `0x01030000`, `0x0103ff00`, and `0x0103ffff`. Then `0xfc0f0050` and `0xfc0f0150` are each written to 1. |
| 5 | `0x637ad310` | Acquire the PMIC interface, drive `0xfc029028` through `0x10 → 0x50 → 0x70`, and send the 37-byte wake burst twice. Wait 12 ms, send 25 and 169 bytes, wait 6 ms, drive `0x74 → 0x76 → 0x7e`, and wait 20 ms. |

All 166 pre-FIFO MMIO writes outside the P2S block matched
`imx284_wake_pre_writes` in order. The generator records only writes for
that table. It drops the two timed calls after writes 18 and 25, counting
from 1. The runner used a table walker with no explicit waits at those
points through experiment 21. Separately, the poll at `0x637a1b32..0x637a1b8c` on
`0xfc02a080[0]` is part of the MIPI-TX D-PHY PLL initializer. The stock
SLVS RX transition is observed at `0xfc0f00b0`.

### Mode selection and SGC0 start

The controller path through `0x63d735f8` packs a 24-byte timing request
and calls `0x6379ce58` from `0x63d73644`. The call at `0x638d16e0`
passes the source record at `0x643aa92c`, whose word at `+0x08` is
copied to request offset `+0x0c`. Inside `0x6379ce58`, the diagnostic
helper `0x6379bc7c` runs first. The programming calls then run in order
`0x635c8628` for SyncSeq, `0x63d26acc` for the SGC0 timing dimensions,
and `0x637a4278` for the SGC0 start request. The low nibble of
`0x640ba266` selects the start flag. A value of 1 forces it clear, 2
forces it set, and other values use whether request word `+4` is 1.

- `0x635c8628` writes `0xfc080028 = 0x00fffffc` and computes
  `0xfc0800f4`. With the native Mode-1 parameters, request flag 1, a
  clock of 72, and the override disabled, request word `+0x0c = 15621`
  yields `1201200 - 72 × 15621 = 0x00012ac8`. The alternate branch
  accepts a direct value from the low 31 bits at `0x640ba290` when
  bit 31 is set. The stock dumps contain the resulting MMIO value.
  The incoming request word and live override word were outside the dumps.
- The native parameter lookup supplies `+0x38 = 619` and
  `+0x3c = 1940`. The SGC0 writes match the stock snapshot
  (`0xfc0a1120 = 0x026a0793`, `0xfc0a1124 = 0x206`,
  `0xfc0a11a8 = 0x026b0001`, `0xfc0a11ac = 0x00110061`).
- The Mode-1 start path writes `0xfc0a112c = 1`, clears
  `0xfc0a1130[16]` and `0xfc0a1108[0]`, then sets `0xfc0a1110[0]`.
  The status getter reads bit 16 of `0xfc0a1110`. Stock subsequently
  reads `0x00010001` there. The standby-to-streaming SPI burst uses the
  frame-synchronous sequencer mode.
- The routine at `0x6379cf40` is a separate restart path. It pulses
  SyncSeq through `0xfc080014` and `0xfc080028`, stops SGC0, and
  cycles the SGC0 clock gate and core enable.

Through experiment 21, the runner's Mode-1 branch programmed the SGC0
clock and SyncSeq defaults after the first two Mode-1 SPI uploads.
Stock programs those defaults in DFE initialization and applies Mode-1
timing and start in the later controller call. Experiment 21 P0 has the
programmed values at
`0xfc080028` and `0xfc0800f4`, while `0xfc080030` remains
`0x00ee466c`, `0xfc0a1110` remains `0x00000001`, and `0xfc0f00b0`
remains zero. The stock trace shows the live counter moving and SGC0
becoming active before SLVS RX reports lock. The cause of the stalled
standalone counter remains unverified.

## 8. Standalone Mode-1 Sequence Retest

The runner now applies the native SGC0 clock writes and SyncSeq defaults
before the sensor wake, with Mode-1 timing and start still applied after
the first two Mode-1 uploads. The Mode-1 wake replay requests 100 µs after
`0xf292a074 = 0x100` and 1 µs after `0xfc02d010 = 0`, using the runner's
Linux sleep helper. Seven `MODE1_INPUT` snapshots capture the live
counter, programmed timing, SGC0, SPI and receiver status. The runner
buffers these samples and prints them after the final SPI wait.

| Capture | Change or condition | Result |
| --- | --- | --- |
| `cold-warm-exp-22` | Earlier initialization and two PHY waits, 1,425.15 s uptime | Six early SPI completions. Final SPI wait timed out. |
| `cold-warm-exp-23` | Same build after reboot, 21.07 s uptime | Reproduced experiment 22. |
| `cold-warm-exp-24` | Scratch-only variant seeded the stock EE standby timing before wake | `0xfc0800f4 = 0x004fbfde` and `0xfc0a1120 = 0x04eb1033` latched. Mode-1 start still stalled. |
| `cold-warm-exp-25` | Main runner also tears down both SLVS receiver ports | Reproduced the capture failure and verified the receiver disable in the post-run dump. |

In every run, `0xfc080030` stayed at `0x00ee466c` from DFE initialization
through the final link sample. `0xfc0a1110` latched the request as
`0x00000001` and remained there. The final SPI timeout was the only SPI
timeout, `0xfc0f00b0` stayed zero, and RdcW0 reported cursor zero and
zero nonzero pixels with the expected crossbar and writer geometry.

Experiments 22–24 stopped RdcW0 but left both SLVS receiver ports
enabled. Experiment 25 cleared `0xfc0f0000`, `0xfc0f0050`, and
`0xfc0f0150` along with RdcW0, DfeTop, SGC0, and the SyncSeq
auxiliary mask. The harness verified sync and sent reboot in each
experiment. The standby timing variant remains outside the main runner.

Stock EE-04 idle already had `0xfc098808 = 0x003e0007` and
`0xfc098908 = 0x00020000` before the Mode-1 transition. The fresh
standalone entry showed both words clear. These differences remain
candidates for tracing the clock and event-enable lifecycle around the
first change of `0xfc080030`. They do not establish its cause.

## 9. Behavioral Driver Audit

Experiment 26 used the behavioral headers and reached the SGC0 request
with the DFE timer words at `0x003c0006` and `0x00020000`. SyncSeq still
read `0x00ee466c`, only six SPI uploads completed, and the receiver
remained unlocked. That capture predates the following offline fixes.

- The MPHY path now treats `0xfc02a040` as global control and programs the
  two lane groups at `0xfc02a044/48/4c` and `0xfc02a054/58/5c`. It
  preserves unrelated fields, waits at lane release, and leaves
  `0xfc02a050` untouched. The ComboPHY checks for and tears down a
  previous native mode before startup. The MIPI-TX PLL checks its
  configuration readbacks and polls `0xfc02a080[0]`.
- CamCore SGC1 uses the Mode-1 external route, with timing `0x026a0793`,
  sync position `0x206`, start control `0x101`, and NLR words
  `0x026b0001` and `0x00110061`. The native IMX284 constructor replay
  verified init words `0x30005` and `3`. The associated CamCore
  initialization writes also match the stock dumps.
- Mode-1 startup enables RDC and AIF and brackets SIF0 setup with its
  reset bit. Teardown clears the corresponding core enables. The
  Mode-1 DfeTop error and IRQ masks follow the stock Mode-1 snapshot.
- PMIC SPI is released after rail setup, reacquired at wake, and
  released at power-off. The IMX284 wake GPIO enable ends at `0x77`
  on bank 2. Native replay with the camera Backup profile supplied
  the power-down sequence delays.

The corrected runner passed the ARM ELF build check. Experiments 27 and
29 then exercised that same build on the camera. Experiment 29 began at
43.31 seconds of uptime after reboot. Attempt 28 ran during USB
reenumeration and never reached the camera.

Both completed runs confirmed the corrected SGC1 timing and NLR words.
The CamCore route readbacks were `0xf3120038 = 0x101` and
`0xf3000038 = 0x10101`. SyncSeq still held at `0x00ee466c` after the
SGC0 start request, SGC0 bit 16 stayed clear, the seventh SPI transfer
timed out, and SLVS RX did not lock. The RdcW0 cursor stayed zero and
the captures yielded zero pixels. Both post-run dumps confirmed the
writer, SGC1 and both SLVS ports were stopped and both PMIC SPI clock
bits were clear. Sync succeeded and reboot was sent after each capture.

## 10. SyncSeq Stall Analysis

Retool Thumb disassembly, Rizin/Ghidra decompilation, and replay of the
original instructions were checked against the stock traces and
experiment 29. The traces sample groups of registers. Changes within
one sample have no established execution order.

| Native routine | Verified behavior |
| --- | --- |
| `0x637a3858` | Records the software clock rate, installs the ten slot defaults and initializes `0xfc08001c/020`. |
| `0x635c8628`, called by `0x6379ce58` | Writes `0xfc080028 = 0x00fffffc`, computes the timing and writes `0xfc0800f4 = 0x00012ac8` for the replayed Mode-1 request. The remaining slot and delay writes also reproduce the runner's values. |
| `0x63d25de4` | Writes `0xfc080014 = 1`, `0xfc080028 = 0x40`, then `0xfc080014 = 0`. The controller reset wrappers at `0x63d73b26` and `0x63d73b68` reach it through `0x63d736de` and `0x6379cf40`. The same path then restarts SGC0. |
| `0x63d25dfc` / `0x63d25e10` | Read and acknowledge the two interrupt status banks at `0xfc080104` and `0xfc080110`. The mask helpers update `0xfc080108/114` under OS lock `0x27`. |
| `0x63d26acc` and `0x637a4278` | Program SGC0 timing and request start at `0xfc0a1110[0]`. The separate getter at `0x637a3f60` extracts active bit 16. |

None of those paths stores to `0xfc080030`. In particular, the literal
in the writer at `0x637a37f8` is `0xfc0800f4`. The reset pulse and
Mode-1 timing replay leave the emulated `0xfc080030` word unchanged.
The replay records CPU stores and does not model peripheral transitions.

The experiment 29 P0 snapshot differs from active stock in only one
of the 80 SyncSeq words (`+0x030`) and one of the 64 SGC0 words
(`+0x010[16]`). All 64 DFE PLL/CRG words at `0xfc021000..ff` match.
The before-start mailbox log also shows the coprocessor reached its
run-state criterion and the timer values `0x003c0006` and
`0x00020000` seen before stock start. Matching these readbacks cannot
establish a running clock or valid frame signal.

In stock EE-02, `0xfc080030` first takes the programmed reload
`0x00fffffc` in the 682.554 ms sample, with SGC0 already active in
that sample. In EE-04 the first reload is present at 1,024.715 ms
while `0xfc0a1110` still reads `1`. EE-02 then records the first
frame-length value `0x0012542e` at 694.125 ms, when its primary SLVS
status first shows 1. Across the remainder of active EE-02, the sync
word falls between `0x0012542b` and `0x0012542d`, close to the
`0x00125430` ticks calculated from the native frame timing. This
pattern is consistent with a latched frame interval. It does not
identify the physical input that updates the readback.

Historical standalone Senser experiments 44–47 and 49–50 reached
`0x00fffffc` at P0 while SGC0 remained at 1. Those were older runner
variants and establish that reaching the reload value alone is
insufficient for frame sync. In the current Mode-1 run, the word
never leaves its pre-start value and the frame-synchronous SPI
transfer times out. The missing transition is at the SGC0/SyncSeq
hardware event boundary. The available traces cannot distinguish an
inactive timing clock, reset or gating, or an absent qualified sync
input. A synchronized trace spanning the first start request and
first frame should sample `0xfc080030`, `0xfc0a1110[16]`, SGC0 status
`0xfc0a1118`, the native IRQ status banks and SPI status, with an
XVS/XHS measurement if available.

## 11. Native Mode-1 Builders and Counter Probe

The standalone Mode-1 path calls the register-command builders for
wake, mode preparation, and stream arm. Native functions
`0x63d2aa56`, `0x63d2aa8a`, and `0x63d2a31e` establish the packet
format. A block holds a tag, a body length, the write command, the
16-bit register address in big-endian order, and one or more values.
The native builder starts a new block at an address page boundary.
The encoder now follows that rule and appends the end marker. A host
build of the actual C encoder reproduced all seven stock transactions
(including the repeated wake burst), and passed boundary and capacity
checks using a generated pair of adjacent register writes.

The runner now queues the final command for the frame trigger before
requesting SGC0 start and defers the CamCore route change until after
the first SPI wait. In stock EE-02, receiver lock is first sampled at
694.125 ms and the first observed CamCore route change is at 732.780 ms.
The instruction trace also establishes that native SGC0 timing uses
separate field writes for H, V, and the fractional timing fields.
Those writes now preserve adjacent bits.

Experiments 30 and 31 confirmed the reordered start, including a run
55.72 seconds after reboot. SyncSeq stayed at `0x00ee466c` and both
runs completed six early transfers, timed out on the frame-triggered
seventh, and recorded zero Bayer pixels. The ordering changes did not
restore sensor timing.

The native diagnostic at `0x637a4324` labels the counter reads HVcnt
and Fcnt. `0x63d26a24` writes `0xfc0a1114` before reading
`0xfc0a1118`. `0x63d269fa` pulses bit 0 at `0xfc0a111c` and reads
the low byte of `0xfc0a1128`. Experiment 32 took two snapshots through
those accessors after the final SPI wait. Both returned HV
`0x3fff3fff` and frame count `0x78`, with SGC0 inactive. The
standalone path has yet to produce evidence of an advancing SGC0
timing generator. This probe does not identify the physical gating
or clock source responsible.

The final build passed the ARM compiler and the encoder checks.
Experiment 33 could not connect after experiment 32 rebooted the
camera, so the final build and longer counter interval were not
exercised on hardware.

## 12. Current Runner Versus Native Mode-1 Sequence

Sources are the original Thumb instructions in `av-cam.bin`, selected
Rizin/Ghidra decompilations, the saved Backup-profile native replay,
stock EE-02 and EE-04, and the experiment 32 dumps. Experiment 32
predates the final page-boundary encoder change. Its Mode-1 packets
are identical to the current builder's output.

### Verified matches

- Mode-1 SyncSeq and DrvSGC0 programming match the native request,
  including the split timing-field writes, trigger selector 1,
  calculated window `0x12ac8`, and SGC0 start request bit. P0 matches
  the active stock dump in 79 of 80 SyncSeq words and all 64 words of
  the sampled DFE PLL/CRG range. The one SyncSeq difference is the
  live readback at `0xfc080030`. In the SGC0 range, the only three
  differences are the active bit and the two latched diagnostic
  outputs. The stock dump was taken without the same counter probe.
- The current builder emits the saved live command packets, with
  the same register addresses and counts as the native Mode-1
  replay. The first six physical transfers complete. The run-mode
  sequence of two software-triggered mode uploads followed by a
  frame-triggered upload matches `0x637ad06c` → `0x63d2ab0a`.
- At the first stock frame in EE-02 the two SoC clock readbacks
  `0xf2a30030/60` equal experiment 32 P0 (`0x147fffff` and
  `0x91071111`). The `0x00100000` bit at `0xf2a30060` that differs
  in EE-04 belongs to native clock ID `0x3a`. EE-02 starts and locks
  without it.

### Remaining differences

| Area | Native behavior | Standalone difference and evidence |
| --- | --- | --- |
| Sensor mode state and ready event | The observed imager pointer at `0x6426b7b8` is `0x6426b384`. `0x637acd98` writes requested mode at object `+0x11c`. After readout, `0x637ad06c` shifts current to previous at `+0x124`, writes requested mode to current at `+0x120`, and copies the profile byte from `+0x128` to `+0x129`. Wake sets object `+0x430 = 1` and event group `0x18` bit `0x100`; `0x637ab558` waits for that event. | The runner follows one fixed cold-Mode-1 sequence. Its register builder reproduces the live stock packets while using captured register values. Native default replay uses the same 110, 14, and 48 ordered register writes, with 9, 1, and 13 differing encoded bytes. For example, native `0x637abea4` computes the stream-latch value from a provider record and a runtime setting, while our fixed profile supplies the captured writes. A reference replay of the live controller inputs would be needed to replace that fixed profile with native-style request construction. |
| DFE mailbox and callbacks | `0x639dfa3c` constructs the host context and attaches callbacks through `0x639df964` before calling the mailbox start routine `0x63da03f2`. The start routine qualifies the reply with `0x63da0276`. Its busy-entry branch runs `0x63da02ce` and reports failure for the initial busy condition. | The runner sets MMIO masks and vectors and polls the mailbox and P2S completion. Its busy path can proceed after an abort and it does not construct the native host callback records. Run 32 entered the nonbusy branch and reached state `0xff` with the expected timer gates, so the busy-start difference is outside this failure. |
| SoC power requests | In EE-02, `0xf290e004/008` remain 1 through SGC0 active and SLVS lock. Their first observed transition to 0 is at 1082.583 ms. | The runner clears both in `psave_imager_wake()` before DFE startup. The owning native service and effect on the SGC0 clock remain unresolved. This is an observed early MMIO difference. |
| Sensor delays | `0x637ad794` uses channel `0xb` via `0x63a92bb0` and `0x63a92c04`, then waits on completion. `0x63a92520` programs the timer at `0xf2403000 + (channel << 8)`. EE-02 samples the requested 9.4, 12.4, 12, 6, and 20 ms durations at `0xf2403b08`. | Senser uses Linux sleep calls. The timer-bank difference for channel `0xb` belongs to the delay implementation. Channel `0xa` also differs, with its ownership still unverified. |
| Frame and RAW output | The stock EE trace reaches the SGC0 active bit, SyncSeq frame interval, and receiver lock before enabling the preview crossbar. | The run 32 hardware counters do not advance between the two native latch samples. The RAW resource uses another crossbar pair and a standalone DMA buffer. Those intentional output differences occur after the stalled frame event. |

The strongest unexplained differences before the frame are the
power-request lifecycle and the missing native host state and event
handoff. Neither has been shown to cause the stopped SGC0 timing.
No runner changes or hardware sessions were made during this comparison.


## 13. Mode-1 startup changes after the firmware comparison

- The stock kernel's `upm.ko` clears PMU `+0x210`, `+0x08`, and
  `+0x04` at `.text` offsets `0x1060c`, `0x10624`, and `0x10654`.
  The surrounding DDR transition includes outer-cache synchronization
  and an OSAL request. Standalone Mode 1 leaves the DDR-B transition
  and its PMU requests to the kernel. It samples both requests at
  entry, before arming the frame trigger, and after the receiver wait.
  The existing Mode-37 path still calls its power-save wake routine.
- The DFE mailbox now reports busy entry as a start failure even when
  an abort and restart produce state `0xff`. The native command
  accessor at `0x63da0880` reads and clears the command latch. The
  runner does the same at entry and when a state wait times out. It
  unwinds a failed start before programming the DFE clocks and PHY.
  The standalone runner still polls the device. The native software
  IRQ callback table and its dispatcher remain outside this path.
- The four software-triggered sensor wake transfers and the two
  Mode-1 configuration transfers must each report SPI completion
  before the runner queues the frame-triggered transfer. Linux
  nanosleep resumes the remaining interval after an interruption.
  The wake path reports failure if the 12, 6, or 20 ms delay cannot
  complete. This implements the synchronous wake dependency using
  Linux and leaves the stock RTOS timer and ready event to their
  native owners.
- The Mode-1 frame-triggered register list at `0x645bc738` references
  `0x646187de` twice, then takes the third `0x0832` write from
  `0x646186fa`. Native `0x637abea4` sets the repeated record to 3
  when the provider link mode is 3 and the setting byte is `0xff`.
  The standalone builder implements that rule and passes the
  resulting three register writes through the P2S encoder. The rest
  of the register profile still uses the live Mode-1 settings.
  Rebuilding those settings from the controller's full runtime
  request and replaying its software event handoff remain open.

The standalone ARM ELF built successfully. Host checks matched all seven
generated packets against the captured packets, verified both latch disable
conditions, and exercised sensor transfer and sleep failures and mailbox
busy and timeout handling. The camera was absent from USB enumeration.
SGC0 activation, SLVS lock, and Bayer DMA after these changes remain unverified.


## 14. Runs 34–35, SGC0 Bit-Field Decoding, and Omitted Controller Writes (2026-11-27 Codex Session)

Follow-up experiments and instruction/bit-field tracing from the 27 November Codex session isolated the stall further inside `DrvSGC0`:

- **`cold-warm-exp-34`:** Kept PMU `0xf290e004/008 = 1` under kernel control, reached DFE mailbox state `0xff` (`0xfc098808=0x003c0006`, `0xfc098908=0x00020000`), completed all 6 software SPI uploads (`I=6`), latched `0xfc0a1110 = 1`, and read back Mode-1 timing `026a0793:00000206:026b0001`. Both `SGC0` diagnostic latches stayed frozen (`HVcnt=0x3fff3fff:0x3fff3fff`, `Fcnt=0x7c:0x7c`), `0xfc080030` stayed `0x00ee466c`, SPI #7 timed out (`T=1`), `SLVS-EC` stayed unlocked, and `RdcW0` captured zero pixels.
- **`cold-warm-exp-35`:** Removed the two extra `0xfc080104` / `0xfc080108` SyncSeq acknowledge/mask writes before start; reproduced the exact same stall as Run 34.
- **Decoded `DrvSGC0` bitfields (`0x63d26a42`, `0x63d26acc`, `0x637a4278`, `0x637a4324`):**
  - `0xfc0a1140`: `[2:0]` VD selector (`7` when VD width > 0, `6` when 0); `[18:16]` HD selector (`4`).
  - `0xfc0a114c[13:0]`: VD pulse width (`4`).
  - `0xfc0a1150`: `[13:0] = SensHDTim + 2 = 5`; `[29:16] = 5 + hd_width(32) = 37 (0x25)`.
  - `0xfc0a110c`, `0xfc0a1194[16]`, `0xfc0a1198[16]`: output config commit writes (`1`, `0x10000`, `0x10000`).
  - `0xfc0a1120`: `(V-1)<<16 | (H-1) = 0x026a0793` (`619 x 1940`); `0xfc0a1124 = V - 101 = 0x206`.
  - `0xfc0a11a8`/`11ac`: fractional NLR enable (`1`) + alternate V (`0x26b = 619`) and numerator/denominator (`17/97` = `0x00110061`) -> `1,201,200` (`0x125430`) 72 MHz timing clocks/frame.
  - `0xfc0a112c[0]`: `rpt` (repeat enable); `0xfc0a1130[16]`, `0xfc0a1108[0]`, `0xfc0a1110[0]` implement start selectors `0`/`1`/`2`; `0xfc0a1110[16]` is HW active status. (`DrvSGC0` virtual slot `+0x08` -> `0x63d269f2` uses selector `1`, `rpt=0`.)
- **Two omitted pre-start controller writes:** `0x63d736ec -> 0x6379cf04` clears VD0 mask `0xfc0a113c[0]`, and `0x63d736e6 -> 0x6379cedc` clears `0xfc0a119c[16]` on the synchronous start path (both already read `0` at entry in standalone dumps).

## 15. Passive Stock Capture & Linux-to-RTOS Dispatch Trace (`sgc0-factory-passive-01`)

A passive Senser capture (`sgc0-factory-passive-01`: `594` polls, `9,304` events) recorded stock `CAMERA_SCN_EE_START_STOP b:1 b:0` preview followed by `adjstctl.elf 0x404 0x4e` factory RAW capture, then clean stop:

- **No PLL / divider / reset change on start:** Stock started `SGC0` in LiveView and restarted it for factory RAW with **zero sampled change** in the three PLL lock bits, PLL dividers, or `0xfc021024` reset.
- **Timing from request to DMA:** During the still restart, hardware reported `SGC0` active (`0xfc0a1110[16]=1`) and `SyncSeq` updated **~6 ms** after the start request; **~20 ms later**, `SLVS-EC` locked and `ISP0 AIF3` (`0xf3002380`) swept `0x0b16b3c0..0x0d8d6480` into retained DMM buffer `0x0b000000` (extent `0x03000000`).
- **Two distinct `SGC0` paths in `av-cam.bin` (Rizin `pdg` + Thumb disassembly):**
  - **Still preview (`SetEE 0x3003`):** OSAL `0x00030001` -> `0x63916a74 -> 0x639196b8` -> `0x000302d9` (cmd `2`) -> `0x6391a25c -> 0x63d8d6e2 -> 0x639152d0` -> `SyncTask` HS callback `0x635ce230 -> 0x638d15c4` (repeating `rpt=1`, `0xfc0800f4=76,488 = 0x12ac8`).
  - **Factory RAW (`C_RAWDATA_CAP` `0x404`/`0x4e` -> mode `0xa00a`):** OSAL `0x000301d7` -> `0x6391cd28 -> 0x6391c660 -> 0x63af4890 -> 0x639152d0` -> lane 2 wait + two lane 0 waits -> still worker `0x638ff67c` -> `0x638ffa54 -> 0x63907474 -> 0x638d146c` (one-shot `rpt=0`, `0xfc0800f4=0`; activates `SGC0` twice with low cycle field `285` then `4,148` ticks and upper field `1,260`, then restores preview).

## 16. Sony a6400 (`ILCE-6400`) Firmware Cross-Check (2026-11-28)

Cross-checking `6400a/nflasha3.bin` against ZV-E10 firmware confirmed near-complete hardware/driver identity:

- **Bit-identical binaries:** `DFE_DAT.BIN` (`65,536` B, SHA-256 `703f457a480eee74...`), `BONOBO.BIN` (`172,144` B), and `LIF_APP.BIN` (`6,716` B) are **100.00% byte-identical**. `AV-CAM.BIN` shares the `ORIL` header and `0x635c6000` load base (`16,822,380` B vs ZV-E10 `17,289,388` B).
- **Identical `CXD90057` / `IMX284` tables:** Identical MMIO literal counts (`COMBOPHY 0xf292a000`, `AFE 0xf2931000`, `SGC1_TOP 0xf3120000`, `DFE_CRG 0xfc020028`, `DFE_MPHY 0xfc02a040`, `SLVSEC_0/1 0xfc0f0000/100`), identical SLVS PHY termination constants (`0x0e0c350b`, `0x0f0d170a`), verbatim `imx284_wake_regs_0/1/2` and Mode-1 timing tuple `(619, 1940, 1, 97, 17)`, and 79–100% shifted driver matches (`SocCrgEn` `100%`, `DfePll::Init` `95.3%`, `SlvsPhyInit` `94.5%`, `AfeEn`/`SlvsecInit` `93.0%`, `Sgc1::Start` `91.4%`).
