# 08 — Talking to the camera: USB, the shell bridge, testcmd, and the lens bus

Every route in and out of the device, and what each one is good for. The
internal message vocabulary is in [04-messaging.md](04-messaging.md); the
modifying routes are in [07-modification.md](07-modification.md).

## USB modes

| PID | mode |
|---|---|
| `0x0d95` | mass storage — the entry point |
| `0x0336` | service mode, after `senserShellCommand` |
| `0x994` | **updater mode** — triggered by certain host-tunnel codes; drives `FirmUpReq` / `CASND LUPDT_*` over CAIF |
| `0x05dc` | PTP |

The transition `0x0d95` → `0x0336` is the authentication handshake that yields
the root BusyBox shell. `zve10.py` implements it and is the **authenticated
bridge**: it is for filesystem and shell operations, **not** direct lens
communication.

## The authenticated shell bridge — `zve10.py`

The only supported way in. One command per argument; a run is accepted only when
a prompt returns. Logs to `zve10_shell.log` in the repo root — **read that, never
the truncated console.**

The device link itself is `research/device/zve10_retry.py`. It reports
`No devices found. Please make sure that the camera is connected.` and
`*** link never came up after every attempt ***` when the camera is absent. That
currently gates all device work.

## The raw host tunnel — `sony_cmd.py`

Unauthenticated USB Control Bulk Transfers: `USBC` CBW header plus a 68-byte
`cam_struct`.

- command `code` at struct offset **`0x0b`**
- payload length at struct offset **`0x1c`**
- code `0x12` = a query

This is the transport the lens protocol runs over. It is separate from the
authenticated bridge and does not require it.

## The lens protocol (E-mount / CAIF)

The PC cannot speak CAIF directly. It goes through the camera, which relays over
the E-mount electrical interface.

```
PC --USB tunnel--> Camera host bridge (USBC/CBW, 68B "cam_struct")
        |
        v
Camera LensFirmUpdate / Lens handler (av-cam.bin)
        |
        v   CAIF  (Camera Link Internal Appli/Firmware interface)
Camera [CA->EN] / [EN->CA]  (CAIF Send / Recv relay)
        |
        v   LIF  (Lens Interface low-level UART, default 750k baud)
Camera LIF layer (HEADER/FOOTER/CHECKSUM framing, DividedInfo chunks)
        |
        v   E-mount serial
Lens [LC->LENS] / [LC<-LENS]   (Lens Controller <-> Lens)
```

Two physical links inside the camera:

- **LC<->LENS** (lens link): `GyroStart`, `GyroStop`, `MoveFcCap`,
  `SetLensParam`.
- **CA<->EN** (CAIF): the camera<->E-mount relay carrying lens commands.

### CAIF / LIF opcodes

Lens firmware & identity (read-only, safe to query):

- `GetLensVersion` — lens FW version (`LIF: [BL]GetLensVersion Error`)
- `FirmUpReq` — lens firmware update request (`LIF: [BL]FirmUpReq Error`)
- `CASND LUPDT_INFO` / `CASND LUPDT_DATA` — update info / data
- `LENS_TYPE_UNKNOWN` / `LENS FIRMERR` / `LENS UNKNOWN` — mount-state errors

Lens actuator command ids (`BL` = Base/Lens, the real E-mount command set):

- `ID_BL_CMD_POS_CYCLE_A` — focus position cycle
- `ID_BL_CMD_FC_DRIVE_CYCLE` — focus drive cycle
- `ID_BL_CMD_MOVE_FC_2` — focus move (variant)
- `ID_BL_CMD_MOVE_FC_CAP2` — focus cap move
- `LENS_DRIVE_FREQUENCY_A` — drive frequency
- `MOVE_IRIS_A` / `SWITCH_IRIS` / `L2B_MOVE_IRIS_A` — iris move / switch
- `LENS_TRANS_ERR_CNT`, `LAST_LENS_ERROR` — 2-byte error codes

### LIF framing

- Default baud **750k**
  (`LIF: Baud rate %x is NOT supported!! Fallback to 750k.`)
- Framing validated: `HEADER_NG`, `FOOTER_NG`, `CHECKSUM_NG`
  (start / size / mark / sum).
- **DividedInfo** protocol: large lens data (cam-curve, fno-correct,
  iris-drivability, eclipse) is split into vsync/queued chunks. Four source
  files name it: `Mount_DividedInfo.cpp`,
  `Mount_DividedInfo_CamCurveData.cpp`,
  `Mount_DividedInfo_FnoCorrectAbility.cpp`,
  `Mount_DividedInfo_IrisDrivabilityData.cpp`.

### Camera-side lens data model

```
b32_lens_serial_no   lens serial number
uc_LensAttach, uc_LensMountStatus, b8_lens_power
lens_id              per /lens/VX<id>_lensfile.bin ISP calibration table
```

Mount flow: `NotifyLensAttach` → mount → `GetLensVersion` → load
`/lens/VX<id>_lensfile.bin`.

## `sndcmd` / `rcvcmd` / `testcmd` — the in-camera message client

These are Sony's own supported command tools, in `/usr/bin` and `/usr/lib`:

| file | size | role |
|---|---:|---|
| `sndcmd.elf` | 5,380 | send a message |
| `rcvcmd.elf` | 5,024 | receive a reply |
| `testcmd.elf` | 5,172 | combined |
| `libtestcmd.so` | 10,128 | the implementation |
| `libosal_uipc.so` | — | the uipc transport |

Ordinary ARM EABI **Thumb** shared objects / executables (GCC 4.5.1, glibc 2.4).
Unlike `av-cam.bin` they carry full section headers and **disassemble offline
with no camera involvement at all.** `libtestcmd.so` is version 1.7, built
Mar 15 2025.

### The command line, verbatim from `sndcmd.elf`'s strings

```
<options> [osal_id] [size]:[data] ...

  --ver      show version number of testcmd module
  --ifile    payload text filename to input
  --ibfile   payload binary filename to input
  --obfile   payload binary filename to output
  --ulogio   invoke osal_printf instead of fprintf
  --sync     invoke sync msg instead of async msg
  --sid      source OSAL_ID (default: 0x00dc0000)

  size   b | w | d | digit
  data   decimal or hex(0x) or string
```

`rcvcmd.elf` takes `--ifile`, `--tmo <ms>`, `--sync`.

### The payload grammar

A payload file is **`key:value` fields, hex-encoded**, read until the requested
byte count is satisfied. From `cmdline_read_data_from_file` (Thumb, `0x1908`):

```
0x1910  ldr  r1, [pc, #0x60]     ; "rb"
0x191A  bl   0x1534              ; fopen
0x1928  bl   0x18D0              ; next token from the line
0x1932  rsb  r2, r4, r8          ; bytes still wanted
0x1936  bl   0x16D8              ; convert one field to bytes
0x1946  adds r6, r6, r0          ; advance output
0x194A  cmp  r4, r8              ; until `size` bytes are read
0x1950  movs r1, #0x40           ; 64-character lines
0x1954  blx  0xDC0               ; fgets
```

The separator is decided at `0x16D8`, where `cmp r2, #0x3a` is `':'`; the same
separator appears in `.rodata` as `"%s:%s"`.

The header is a 32-bit little-endian word with the total length at offset
**`0x2c`** (`cmdline_get_size`, Thumb `0x1CB0`).

### What the client is for

Every route to the `ldec` driver code was closed: `PA 0x5F00A000` returns 0
bytes through `/dev/mem`, the kernel text mapping is unreachable,
`swapper_pg_dir` is not exported, and `/proc/self/pagemap` returns all zeros
even for our own heap. This interface sidesteps that entirely — it is a
**documented userspace path** into the camera's message bus, with a grammar
recoverable offline. No kernel memory reads, no driver poking, no invented
struct layouts.

`libtestcmd.so` has also been used as the **code-execution vehicle**: a Thumb-2
raw-`svc` payload injected into `cmdline_show_revision`. See
[07-modification.md](07-modification.md).

## The camera's own network stack

It runs a WiFi Direct group owner on **`192.168.122.1`**; Sony cameras expose an
HTTP control API on that link. Zero risk, and it is the main firmware's own
interface rather than a side door. Not yet reachable because the PC is not
associated with that radio.

## PTP on the W830 — a different camera

`90-session/RE_NOTES.md` is PTP/MTP reverse-engineering for a **Sony DSC W830**,
kept because the transport lessons transfer. It is not ZV-E10 material.

## Tools

```powershell
# the only camera link; logs to zve10_shell.log
& ".venv\Scripts\python.exe" -B research\device\zve10_retry.py <cmd...>

# offline lens host-tunnel scanners
& ".venv\Scripts\python.exe" -B research\firmware\scan_lensfirm2.py   # 0x00..0xFF struct-code, PID flip
& ".venv\Scripts\python.exe" -B research\firmware\lens_query.py        # read-only GetLensVersion

# offline testcmd parsing
& ".venv\Scripts\python.exe" -B research\firmware\testcmd_elf.py      # ELF32 parse, 24 named functions
& ".venv\Scripts\python.exe" -B research\firmware\testcmd_thumb.py    # Thumb + PLT + .rodata annotation
```

## Open

1. **The host-tunnel command code for `GetLensVersion` is unknown.** It must be
   determined live, by trying the updater-entry codes and dumping responses.
   Read-only when done, so it is low risk.
2. **The WiFi Direct link is unassociated** — the cheapest untried route.
3. **The RTOS message format** — what `sndcmd` speaks to the far side. See
   [04-messaging.md](04-messaging.md) and the open items in
   [03-binaries.md](03-binaries.md).
