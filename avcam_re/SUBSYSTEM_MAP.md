# Decode vs encode — subsystem map (2026-09-26)

Answers "which code is decode and which is encode" across the whole image.
Method and limits stated up front, because a 1.8% sample should not be
mistaken for a full audit.

## Method

Each function is labelled by the **strings it references**. That is evidence,
not inference: a function that logs `DEC_FULL_WAIT_CHG_COMP_V` is decoder code.
`retool.subsys` resolves every PC-relative reference, reads the string at its
target, and labels the referencing function from that vocabulary.

Attribution uses the nearest preceding *trusted* function start, capping
trusted size at 64 KB, because rizin emits 2,246 bogus functions larger than
that (one spans 7.6 MB) which would otherwise smear attribution image-wide.
Every label is auditable — `retool subsystems` prints the string that justified
each one.

## Coverage, and what was rejected

**1,137 of 64,559 trusted functions (1.8%) reference a string directly.** The
rest call helpers that do. So the percentages below describe the
string-logging surface, which is the codec cores, not the whole pipeline.

Nearest-neighbour propagation to the remaining 98% was implemented and
**deliberately not reported**: median distance from a function to its
string-identified seed was 9 KB (p90 63 KB), and propagation *inverted* the
decode:encode ratio from 1.26:1 to 0.43:1. It was reporting where seeds happen
to sit. The numbers below are the directly-evidenced ones.

## Direct classification (1,137 functions)

| subsystem | n | share |
|---|---|---|
| DECODE | 225 | 19.8% |
| CONTROL_MSG | 209 | 18.4% |
| AUDIO | 189 | 16.6% |
| ENCODE | 179 | 15.7% |
| MEMORY_DMM | 138 | 12.1% |
| LENS | 112 | 9.9% |
| ISP_IMAGE | 50 | 4.4% |
| PLAYBACK | 16 | 1.4% |
| SENSOR_EXPOSURE | 16 | 1.4% |
| RECORD_MODE | 3 | 0.3% |

**decode : encode = 225 : 179 = 1.26 : 1** on direct evidence.

## The two codecs occupy separate, identifiable regions

This is the solid result — the separation is not marginal:

| 64 KB block | dominated by | decode | encode | labelled |
|---|---|---|---|---|
| `0x0a0000` | **DECODE** | 71 | 0 | 96 |
| `0x0b0000` | **DECODE** | 84 | 0 | 94 |
| `0x0c0000` | mixed (AUDIO 38) | 21 | 7 | 66 |
| `0x0d0000` | **ENCODE** | 1 | 24 | 30 |
| `0x0e0000` | **ENCODE** | 4 | 38 | 48 |
| `0x080000` | ENCODE | 3 | 16 | 66 |
| `0x090000` | AUDIO 40 | 5 | 0 | 47 |
| `0x320000`–`0x360000` | ENCODE | 0–1 | 6–13 | 10–19 |
| `0x430000`–`0x580000` | ENCODE | 0 | 3–18 | 6–35 |

So: **decoder ≈ `0x0a0000`–`0x0b0000`** (155 decode functions, **zero**
encode), **encoder ≈ `0x0d0000`–`0x0e0000`** (62 encode, 5 decode). This also
settles the earlier question: neither codec touches the mode table at
`0x89DADE`, whose only consumer is the DMM memory manager.

## State-machine evidence

**Decoder: 116 distinct `DEC_*` log tags**, a full vocabulary —
`DEC_IDLE`, `DEC_ISSUE`, `DEC_FULL`, `DEC_OPEN`, `DEC_CLOSE`, `DEC_CANCEL_START`,
`DEC_EMERGENCY`, `DEC_FATAL_ERROR`, `DEC_BEST_EFFORT_A_RUN`, `DEC_FULL2SLOW_PAUSE`,
`DEC_DOWNSHIFT`, `DEC_WAIT_CHG_COMP_V`, and so on. Source files confirm it:
`dec/sfmc_dec_output.cpp`, `dec/sfmc_dec_timing_sm.cpp`,
`dec/sfmc_dec_output_audio.cpp`.

Top decode functions by `DEC_*` tag count:

| tags | function | addr | size |
|---|---|---|---|
| **17** | `fcn.000bb63c` | `0xbb63c` | 180 |
| 5 | `fcn.000baf28` | `0xbaf28` | 84 |
| 2 | `fcn.000bb748` | `0xbb748` | 470 |
| 2 | `fcn.000e5b08` | `0xe5b08` | 204 |

`fcn.000bb63c` is the decoder's state dispatcher — 180 bytes switching on 17
distinct states.

**Encoder: 63 distinct `ENC_*` tags** — `ENC_IDLE`, `ENC_OPENING`, `ENC_OPENED`,
`ENC_ENCODING`, `ENC_POSTPROC`, `ENC_FINALIZE`, `ENC_CUT`, `ENC_INFRA_STOP_WAIT`,
`ENC_ENCODE_PICTURE_FINAL`, `ENC_CLOSING`, `ENC_FATAL_ERROR`, `ENC_MVC`, …

| tags | function | addr | size |
|---|---|---|---|
| **11** | `fcn.0008f888` | `0x8f888` | 1070 |
| 8 | `fcn.000dd7d8` | `0xdd7d8` | 56 |
| 4 | `fcn.000e2ad0` | `0xe2ad0` | 298 |
| 4 | `fcn.000e2980` | `0xe2980` | 310 |
| 4 | `fcn.000da9e8` | `0xda9e8` | 292 |

`fcn.0008f888` is the encoder's state machine proper — 1,070 bytes against the
decoder's 180, i.e. the encode path is roughly 6x more code.

## The state-name getter family

`0x8f1a4`–`0x8f888` is a family of same-shaped functions (`add rX, pc` / `bx lr`
tables) returning a state or mode name for an id. Confirmed members:

| addr | name for |
|---|---|
| `0x8f5f8` | recording mode — `SD_SAKUHINKA`, `GEARED_ENC`, `HILGT_PB_NOAUDIO`, … |
| `0x8f7e8` | `DEC_MVC` |
| `0x8f888` | the 11 `ENC_*` encode states |

So the enum→name getters are themselves the codec state machines' names, and
`fcn.0008f888` doubles as both a name table and the encode state entry.

## What this does not establish

- Only 1.8% of functions are directly classified. The codec cores are well
  covered, but the 98% that call them (buffers, DMA, glue) are not classified
  at all.
- Region boundaries are 64 KB granularity from a 1.8% sample. `0x0c0000` is
  genuinely mixed (AUDIO 38 / DECODE 21 / ENCODE 7) and should not be called
  either.
- No call-graph analysis. Which decoder functions are reachable from the
  playback path, and which encoder functions from the record path, is not
  established.
- The OpenGate question is unaffected: the mode table's consumer is the memory
  manager, which is neither codec, so editing its height was never going to
  change encoder *or* decoder output.

## Reproducing

```
retool.cmd subsystems avcam --blocks
retool.cmd xrefs avcam 0x9585a0          # a decoder string, for reference
retool.cmd disasm avcam 0xbb63c -n 60    # decoder state dispatcher
retool.cmd disasm avcam 0x8f888 -n 120   # encoder state machine
```
