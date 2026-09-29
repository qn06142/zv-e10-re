# The scenario plugins: the camera's command vocabulary, decoded

`/usr/scenario/` holds 35 shared objects totalling 543 KB. Each exports one
function, `scenario_run`, and each is a worked example of a real call into a
real subsystem. They matter because they are the **only surviving readable
description of what the scenarios do** — the service loader that would run them
is not present, but the plugins themselves are, and they are ordinary ARM
ELFs with full symbol tables.

Two RPC frameworks appear, and that split is itself a finding:

| framework | plugins | shape |
|---|---:|---|
| `DataflowInfra*` | 18 | raw OSAL messages; `SendASync(unsigned int, DataflowInfraMsg*)` — destination id is an argument |
| `MWF::*` | 8 | the object/message framework: `ObjIf`, `ObjMsg`, `EventSender`/`Receiver`, pins, signals |
| neither (thin) | 9 | dispatch to the above, or straight to `libtestcmd`/`libIMDB` calls |

The AVBB/CAMERA plugins are `DataflowInfra`; the MPR ones are `MWF`. The two
families do not share a vocabulary, which is consistent with `MWF` being the
media pipeline and `DataflowInfra` the audio/HDMI dataflow.

## The ids are in the code, not in any table

The obvious approach — look for a name→id table — finds nothing, and that is
the point. The ids are **immediates built by `movw`/`movt` pairs** and passed
to the RPC entry points, so they have to be read out of the disassembly.
`research/firmware/scenario_vocab.py` sweeps them across all 35 plugins.

The result is a structured 16-bit namespace, 96 distinct values:

| group | uses | values |
|---|---:|---|
| `0x0___` | 139 | `0x101` `0x105` `0x115`(6) `0x141`(4) `0x295`(4) `0x301`(16) `0x303`(8) `0x313`(12) `0x331`(4) `0x3d7` `0x401`(12) `0x4a1`(4) `0x501`(4) `0x603`(3) … |
| `0x1___` | 54 | `0x1001`(10) `0x1002`(8) `0x1005`(4) `0x1102`(5) `0x1106`(6) `0x1317`(2) `0x1388` |
| `0x2___` | 93 | `0x2001`(17) `0x2004`(**76**) |
| `0x3___` | 10 | `0x3001`(2) `0x3003`(5) `0x3006` `0x3023` |
| `0x8___` | 55 | `0x8001`(7) `0x8102`(10) `0x8301`(7) `0x8313`(6) `0x8401`(6) `0x84a1`(2) |
| `0x7___`, `0xc___` | 5 | `0x7bf0`(2) `0xc350`(3) |

`0x2004` alone is 76 uses, and `0x2001` 17 — together they are the common
dataflow path that nearly every scenario takes before doing anything specific.

## The ids are anchored by the type names

The numbers alone would be a guess. Five C++ template instantiations carry a
message id as a literal **in the mangled name**, and each is *defined* (not
imported) in exactly one plugin, which gives a fixed set of ground truth to
check the vocabulary against:

    HDMI::PAYLOAD<HDMI::MSG_PARAM_SET_RESOLUTION<257,1>>   0x0101  in START_HDMI
    HDMI::PAYLOAD<HDMI::MSG_PARAM_SET_DEFINITION<266,1>>   0x010a  in START_HDMI
    HDMI::PAYLOAD<HDMI::MSG_PARAM_SET_3D_FORMAT<268,1>>    0x010c  in START_HDMI
    HDMI::PAYLOAD<HDMI::MSG_PARAM_SET_3D_MODE<269,1>>      0x010d  in START_HDMI
    HDMI::PAYLOAD<HDMI::MSG_PARAM_SET_OUTPUT<272,1>>       0x0110  in START_HDMI_INPUT

Checked against the `movw` sweep, **2 of the 5 match and 3 do not**:

| template id | plugin | that id present as an immediate? |
|---|---|---|
| 257 `0x101` SET_RESOLUTION | `START_HDMI`, `START_HDMI_INPUT` | **yes**, in both |
| 269 `0x10d` SET_3D_MODE | `START_HDMI` | **yes** |
| 266 `0x010a` SET_DEFINITION | `START_HDMI` | no |
| 268 `0x010c` SET_3D_FORMAT | `START_HDMI` | no |
| 272 `0x0110` SET_OUTPUT | `START_HDMI_INPUT` | no |

`0x101` and `0x10d` are also *not* present in unrelated plugins — `0x10d` does
not appear in `START_AUDIO`, which uses none of the HDMI types — so the two
matches are specific rather than a coincidence of a dense vocabulary.

The three non-matches are **not** evidence against the mapping. Those messages
are set by a helper called with a value rather than an immediate: in
`SndDataFlowMsgAsync` the id arrives in `r1` from the caller, and at the
`SetCableHDMI` call site it is loaded indirectly (`ldr r1, [r3]` where
`r3 = [r4 + off]`) — a runtime struct field. So whether a given id appears as a
literal depends on whether that call site had it to hand, not on whether the
mapping is right.

What the comparison does establish: the low 12 bits of the vocabulary are real
message ids, they are shared across plugins (`0x101` in two of them), they
group by subsystem, and the type names in the symbol table are the key to them.

## Per-plugin

Grouping ids by plugin lines the vocabulary up with the audio/HDMI topology:

| plugin | ids | message types it names |
|---|---|---|
| `START_HDMI` | `0x101 0x10d 0x143 0x263 … 0x810a` | `MSG_PARAM_SET_{RESOLUTION,DEFINITION,3D_FORMAT,3D_MODE}`, `PIN_{GET,REQUEST_CONNECT,REQUEST_DISCONNECT}` |
| `START_HDMI_INPUT` | `0x101 0x105 0x11f 0x143 0x195 …` | `MSG_PARAM_SET_{OUTPUT,RESOLUTION}` |
| `START_HDMI_{SUB,INPUT_SUB}` | `0x203 0x2b7 0x2c9 0x2fa 0x301 0x303` | `ADF_OUTPUT_{DETECT_JACK,SET_*,...}` |
| `START_{MIC,MICSENSE}` | `0x301 0x401 0x4a1 0x2004 0x8102 0x8401` (+`0x8301 0x84a1` for MIC) | `ADF_INPUT_SET_{INPUT,ADJ_THROUGH}` |
| `START_{AUDIO,VIDEO}` | `0x313 0x2004 0x8102 0x8313` / `0x501 0x1106 0x2001` | `ADF_OUTPUT_SET_ANTI_CLIPPING` |
| `START/STOP_PANELEVF` | `0x117 0x141 0x151 0x175 0x1a9 0x1b9 0x301 0x302 0x317 0x501 0x1102 0x1317 0x2001` | — (pan/level, no dataflow types) |
| `EE_{START_STOP,SETUP_START_STOP}` | `0x3003` / `0x3003 0x3006 0x3023` | `PIN_REQUEST_{CONNECT,DISCONNECT}` |
| `MOVIE_REC_START` | `0x1388 0x3001` | — |
| `MPR_FORMAT` | `0x1001 0x1002 0x1003 0x1004 0x1005 0x1006 0x1022 0x1023 0x1024 0x1027 0x1057 0x3002 0xc350` | (MWF object framework) |
| `MPR_GET_CONTENT_COUNT` | `0x1001 0x1004 0x1005 0x102a 0x1102 0x1103 0x1104 0x1105 0x110d` | (MWF) |
| `MPR_GET_TOTAL_LOG` | `0x1002 0x7bf0` | (`MonQueue` only) |
| `MPR_INSTALL_MAP_DEMOMOVIE` | `0x115 0x1ff 0x603 0x6bc 0x6bd 0xd01 0x1001 0x1002 0x1005` | (MWF + `ObjIfWrapper`, `AdjLog`) |

The naming conventions fall out of the ids: `ADF_*` and `PROC_*` are the audio
dataflow and processor routing (`PinConnect_VDF_to_HDMI`,
`PinConnect_ADF_to_HDMI`, `CheckPinUnConnectADF_to_HDMI` are all imported by
name), `PIN_*` is the pin graph, and the `0x8xxx` group tracks the audio path
across the `START`/`STOP` pairs.

## These are not the bus ids

Worth being explicit, because it is where the earlier work stalled. The one
`osal_id` known to be accepted, `0x00dc0000`, is an **endpoint** — the address
the bus delivers to. These ids are **commands carried inside** the message, to
a subsystem that endpoint fronts. Two layers:

```
  0x00dc0000  bus endpoint  (liro / RTOS)      <- what sndcmd.elf addresses
      |
      +-- 0x2004, 0x0101, 0x0301 ...           <- what the plugins put in the
          command id field of the message          message.  THIS paper.
```

So the earlier question — "which `osal_id` reaches the display" — was asking
for the outer layer while the interesting vocabulary is the inner one. Both are
now described, and the inner one names what the camera can be *asked* to do.
It is a vocabulary rather than a working interface: `scenario.elf` still cannot
deliver a message, because the peer that would `dlopen` the plugin and the
`DataflowInfra`/`MWF` libraries are not loaded in service mode.

## How this was read

Straightforward once the tooling is right, and the tooling had four bugs worth
recording — see `docs/RE_METHOD.md`. The one that cost most: resolving a PLT
stub to its symbol. The obvious test is to match the encoding against
`0xE5BCC000`, but that constant pins the register field as well as the
instruction, so it rejects the common `e5bcf...` encoding (Rn = ip) and
returns **an empty map with no error**. Getting it right — testing P/U/W/L by
bit position and checking Rn and Rt separately — took `plt_map` from 0 entries
to 122 on a single plugin.

That mattered: with the PLT unresolved, no call site could be identified, so
`SendASync` and friends were invisible and the whole sweep came back with zero
ids. A silent empty result read as "the ids are not immediates", which would
have been the wrong conclusion entirely.

`scenario.elf` itself remains unusable as a path in: it sends the name over the
bus and the peer that would `dlopen` the plugin is not loaded in service mode.
The plugins are readable; the runner is not.
