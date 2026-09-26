# Module contract and custom-firmware feasibility (2026-09-26)

Assessment of whether `av-cam.bin` can be replaced with custom code, based on
what static analysis establishes. Stated with its limits, because the honest
answer is "not a full replacement, and here's why".

## What makes replacement *possible* at all

- The module is **plaintext and unsigned**. A string patch survived a reboot in
  an earlier session, so the loader accepts arbitrary bytes.
- Its exception vectors are **self-contained**: the eight pointers at
  `0x10..0x2c` are runtime addresses inside its own load window
  (`0x635c6058`, `0xb4`, `0x68`, `0x78`, `0x88`, `0x98`, `0x9c`, `0xa0` →
  file offsets `0x58`, `0xb4`, `0x68`, `0x78`, `0x88`, `0x98`, `0x9c`,
  `0xa0`). It carries its own handlers rather than depending on the RTOS to
  install them.
- Header: `b 0x30` at `0x0`, `"ORIL"` magic at `0x4`.

So the file is a self-contained loadable unit. That is the necessary condition,
and it holds.

## The hardware control surface is small

`ISP_WriteRegister` (`0x7e8e88`) is the universal register-write entry point.
It has **1,983 `bl` call sites** (the earlier 4,220 figure counts data
references too). Recovering the first argument — the register block id — from
the instruction stream:

| register block | call sites | share |
|---|---|---|
| **0x57** | 1,168 | 59% |
| **0x68** | 747 | 38% |
| 0x26 | 13 | <1% |
| 35 others | 1–2 each | <1% |

**97% of all register programming goes through two blocks.** Per the notes,
`0x57` is the ISP stage-write family and `0x68` is the DFE container. Everything
else is a singleton.

This is the most encouraging finding for feasibility: driving the hardware does
**not** require reimplementing 37 subsystems. It requires reimplementing the
*callers* of one function with two block ids.

## The rest of the surface

| subsystem | location | notes |
|---|---|---|
| Decoder | `0x0a0000`–`0x0b0000` | 116 `DEC_*` state tags; dispatcher `fcn.000bb63c` (180 B) |
| Encoder | `0x0d0000`–`0x0e0000` | 63 `ENC_*` state tags; state machine `fcn.0008f888` (1070 B) |
| Audio | `0x090000`, `0x0c0000` | 189 string-identified functions |
| ISP / DFE | scattered; strings at `0x1d8xxx` | DFE DDR3 init, AWB, shading, tuning |
| Memory (DMM/OSAL) | caller at `0x3ab074` | sizes units by mode id |
| Control plane | ADF / Biz / Avio | `[ADF]` tags; message broker |

Decoder and encoder touch **no data tables**; their whole configuration arrives
as literals at each call site, through the two register blocks.

## Why a full replacement is not realistic

1. **The tuning data is vendor per-sensor.** The image carries 17,771 runs of
   ≥16 float32 and ~6,310 coefficient tables (AWB matrices, exposure/ISO/gain
   ramps, shading). The ISP is not a pipeline of algorithms you can rewrite —
   it is that pipeline *plus* a per-unit calibration you cannot derive. A
   replacement would have to reproduce Sony's tuning or the output is wrong.
2. **The module is a real-time participant.** It answers OSAL message traffic
   continuously. A module that responds late or not at all does not degrade
   gracefully; the camera hangs or the UI stalls. This is a hard real-time
   contract that is not documented anywhere and must be inferred message by
   message.
3. **Hardware bring-up is undocumented.** DDR frame buffers, the DFE's DDR3
   init, ISP FIFO line limits, and the sensor readout sequence are all
   register pokes whose semantics exist only in this binary and in the
   hardware. There is no datasheet.
4. **Effort.** 66,805 functions, 1.8% of them directly classifiable from
   strings. There is no shortcut to "end to end" here; it is measured in
   months, and the parts that matter most (the tuning semantics and the
   message contract) are the parts static analysis is worst at.

## What *is* realistic

Ordered by value per unit of effort:

1. **A passive module** — a replacement that satisfies the loader, answers the
   minimum message set, and logs. Proves the load/contract path end to end
   without touching the pipeline. This is the correct first project.
2. **A single-function interception** — using the register-block map, divert
   one `0x57` or `0x68` write and observe the argument stream. The block map
   is now known, so this is a bounded, well-defined task.
3. **One codec path reimplemented** — plausible for playback (decoder is the
   smaller side at 180 B of state logic) *if* the tuning data can be reused
   rather than regenerated.

Patching the existing binary, which is what has been attempted, remains far
cheaper — but the two failed patch attempts both show the failure mode: the
obvious constants are not the control points, and the real ones sit behind
state ids and register writes that have to be traced individually.

## Reproducing

```
retool.cmd subsystems avcam --blocks
retool.cmd xrefs  avcam 0x7e8e88          # the register-write primitive
retool.cmd disasm avcam 0x7e8e88 -n 40    # its block dispatch
retool.cmd disasm avcam 0x8f888 -n 120    # encoder state machine
retool.cmd disasm avcam 0xbb63c -n 60     # decoder state dispatcher
```
