# Hardware topology reachable from av-cam.bin (2026-09-26)

What this module reveals about the camera's hardware, and — equally important
— what it does **not** reveal, and why.

## The key structural finding: there is no direct register map

A scan for memory-mapped addresses (PC-relative references resolving outside
the 17 MB image) returns **13 references, every one of them garbage** — odd low
bits, one per page, scattered randomly. There is no MMIO map to be had this
way.

That is not a tooling failure, it is a property of the firmware: **the module
never names hardware addresses.** It reaches hardware through an abstraction —
`ISP_WriteRegister(0x7e8e88)` with a block id — which is why:

- the block map is the real hardware interface: **0x57** (1,168 calls) and
  **0x68** (747 calls) account for 97% of all register writes
- the destinations of those writes are computed at runtime from a base the
  module obtains elsewhere, so no literal ever names them
- a "hardware address" recovered from this binary is always an artifact

Two of my own earlier outputs were this artifact and are withdrawn: a page
histogram naming `0xda2e9000`, `0xf1f000`, `0xf4f000` as "most referenced
pages" came from a resolver bug (see below) and is not evidence of anything.
The cause was an unbounded `ldr`→`add` pairing window in `retool.xrefs`, which
let a distant `add rX, pc` reuse a stale literal-pool slot and fabricate
references that look exactly like register addresses. Fixed, and the fixed
resolver is what produced the 13-reference result above.

So: to obtain the true register map, `ISP_WriteRegister` and its callers'
subcommand encoding must be reversed. That is the real remaining work, and it
is bounded (one function plus 1,983 call sites) but it is not what this pass
did.

## What the strings do establish

The peripheral inventory is legible from the module's own log strings.

### Sensor input
- **MIPI CSI-2** receiver — `IMG:CSI-2 Rx Link LaneEnable Unknown num_lanes`,
  `IMG:MIPI CSI-2 unknown id`, `IMG:MIPI D-PHY unknown id`, `IMG:MIPI Tx %d %d`
- **ComboPHY** with **SLVS-EC** — `IMG:ComboPHY SLVS-EC PLL Lockup`,
  `IMG:ComboPHY MIPI LaneStart`, lane count / lane-select / bandwidth registers
  (`IMG:CLK%x XRST%x ILANE_EN%x … ILANESEL%x … ICONFIG4LANE%x`)
- Two sensor paths coexist: MIPI and SLVS-EC, selected per model.

### Image front end
- **DFE** (Digital Front End) — `IMG:DFE DDR3 Init`, `IMG:dfe_int_handler0`
- **DFE has its own DDR3** and a power rail: `FW: No Read. cause:waiting for
  DFE DDR power supply`, `waiting for DFE DDR power supply`
- **APL** (application layer) unit management — `FW: [APL] Calloc InputPrm Err`,
  `[APL] Close Err1..Err7`, `[APL] GetZimaNo Err`, and DDR moves with an
  `apl_mov_set_aic` register (`R0(DDR)`, `W2(DDR)`, `R2(DDR)`)

### Codec
- **ZIMA** is the dedicated video codec engine: `ZIMA DVENC` (99 tagged
  strings), `ZIMA DVDEC` (121), `ZIMA_AVC`, `ZIMA JPEG`, `ZIMA_LPCM_DEC`
- It exposes per-instance numbering (`GetZimaNo`) and JPEG report
  synchronisation (`ZIMA JPEG ERR: decode_sync CallBack`)

### Timing and synchronisation
- **Genlock** — multi-processor frame sync (`[GENLOCK D]osal_valloc_msg`,
  `GenlockInitializer::GetInstance()`)
- **DFS** dynamic frame rate / clock change — `FW: DFS CLK CHANGE LATE!:
  fdt(%d), camout(%d), cmp(%d), dsp(%d)`, `DFS CMD CLK PRE REQ ERR`
- **SGC1** imager power save (`Too many SGC1 kick for Imager power save`)

### Lens
- **LIF** lens interface with **BL / HS** power stages — `LIF: [BL][HS]POWER
  OFF SEQ TIME OUT`, `LIF: [BL]CA LOGIC POWER RES ERR`
- Per-model lens tables on the filesystem: `/lens/VX8900_lensfile.bin` …
  `VX8916…`, `LensAberrationData.bin`

### Memory
- System **DDR**; unit allocation by mode id (the DMM consumer at `0x3ab074`)
- **uc_SRAM** — a microcontroller-side SRAM used to stage 3D LUTs
  (`CC: Copy3DLUT uc_SRAM=[%d], SRAM addr=0x[%X]`)
- **Audio Frontend** listed as a DDR message-buffer path (`arg1:path
  [0: NULL, 1: Audio Frontend, 2: DDR]`)

## Internal module decomposition

Log-tag prefixes are subsystem markers and give a clean internal split:

| prefix | strings | what it is |
|---|---|---|
| `[ADF]` | 1585 | AV Data Framework — the control plane, largest single component |
| `[SDF]` | 490 | sensor/stream data framework |
| `[IDT]` | 401 | — |
| `[TRK]` | 355 | tracking |
| `[STATE]` | 211 | generic state |
| `[IMLENCSTAT]` | 189 | **image-module encoder state machine** |
| `[ENCHANDLER]` | 185 | encode command handler |
| `[VDF]` | 182 | video decode framework |
| `[STATECACHE]` | 160 | — |
| `[IMLDECSTAT]` | 158 | **image-module decoder state machine** |
| `[VEF]` | 149 | video encode framework |
| `[CODEC V]` | 122 | video codec wrapper |
| `[ZIMA DVDEC]` | 121 | ZIMA video decode |
| `[TSKVIDENC]` | 118 | video encode task |
| `[AVIO]` | 115 | AV I/O |
| `[SA AUD DRV]` | 100 | audio driver |
| `[ZIMA DVENC]` | 99 | ZIMA video encode |
| `[CODEC A]` | 86 | audio codec |
| `[DECHANDLER]` | 63 | decode command handler |

This corroborates the code-region split from string evidence: the encoder and
decoder are separate subsystems with separate frameworks (`VEF`/`VDF`), separate
state machines (`IMLENCSTAT`/`IMLDECSTAT`), separate handlers
(`ENCHANDLER`/`DECHANDLER`) and separate hardware engine paths
(`ZIMA DVENC`/`ZIMA DVDEC`).

## Topological summary

```
  sensor  ──MIPI CSI-2 / ComboPHY SLVS-EC──▶  DFE  ──own DDR3──┐
                                                               │
  uc_SRAM (3D LUT staging) ─────────────────────────────────▶  APL ──▶ ZIMA
                                                               │      DVENC / DVDEC
  system DDR ◀── DMM unit allocation by mode id ────────────────┘
                                                                │
  Genlock · DFS clock · SGC1 power  ◀── timing/power plane ──────┘

  LIF (lens, BL/HS power)      SA AUD DRV (audio)     ADF (control plane, 1585 tags)
```

## Confidence

- **High:** the peripheral inventory and module decomposition. These come from
  the module's own diagnostic strings, which name the hardware explicitly, and
  the encode/decode split is independently corroborated by code regions.
- **None / withdrawn:** any specific register address, register map, or MMIO
  page. The 13 out-of-image references are artifacts, and the earlier
  "hardware page histogram" was a resolver bug. Do not use either.
- **Unknown:** register semantics, bit fields, and the encoding of the
  `ISP_WriteRegister` subcommand space. That is the gap between knowing the
  hardware *exists* and being able to drive it.

## Reproducing

```
retool.cmd subsystems avcam --blocks   # encode/decode region split
retool.cmd xrefs avcam 0x7e8e88        # the register-write primitive
retool.cmd disasm avcam 0x7e8e88 -n 40 # its block dispatch -- start here
```
