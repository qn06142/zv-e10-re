# Sony ZV-E10 E-mount / CAIF Lens Protocol — RE Map

> Scripts mentioned below by bare filename now live under `research/`;
> see `research/README.md` for the index.

Extracted from `av-cam.bin` string table (firmware 2.02/2.03). This is the lens
communication architecture. The PC cannot speak CAIF directly; it goes through the
camera, which relays over the E-mount electrical interface.

## Layered model (PC -> lens)

```
PC --USB tunnel--> Camera host bridge (sony_cmd.py: USBC/CBW, 68B "cam_struct")
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
- **LC<->LENS** (lens link): `GyroStart`, `GyroStop`, `MoveFcCap`, `SetLensParam`.
- **CA<->EN** (CAIF): the camera<->E-mount relay that carries lens commands.

## Key CAIF / LIF opcodes (from strings)

Lens firmware & identity (read-only, safe to query):
- `GetLensVersion`  -> read lens FW version (`LIF: [BL]GetLensVersion Error`)
- `FirmUpReq`       -> lens firmware update request (`LIF: [BL]FirmUpReq Error`)
- `CASND LUPDT_INFO` / `CASND LUPDT_DATA` -> update info / data send
- `LENS_TYPE_UNKNOWN` / `LENS FIRMERR` / `LENS UNKNOWN` -> mount-state errors

Lens actuator command IDs (BL = Base/Lens, the real E-mount cmd set):
- `ID_BL_CMD_POS_CYCLE_A`      focus position cycle
- `ID_BL_CMD_FC_DRIVE_CYCLE`   focus drive cycle
- `ID_BL_CMD_MOVE_FC_2`        focus move (variant)
- `ID_BL_CMD_MOVE_FC_CAP2`     focus cap move
- `LENS_DRIVE_FREQUENCY_A`     drive frequency
- `MOVE_IRIS_A` / `SWITCH_IRIS` / `L2B_MOVE_IRIS_A`  iris move / switch
- `LENS_TRANS_ERR_CNT`, `LAST_LENS_ERROR` (2-byte error codes)

## LIF (low-level lens UART) framing
- Default baud **750k** (`LIF: Baud rate %x is NOT supported!! Fallback to 750k.`)
- Packet framing validated: `HEADER_NG`, `FOOTER_NG`, `CHECKSUM_NG` (start/size/mark/sum).
- **DividedInfo** protocol: large lens data (cam-curve, fno-correct, iris-drivability,
  eclipse) is split into vsync/queued chunks: `Mount_DividedInfo.cpp`,
  `Mount_DividedInfo_CamCurveData.cpp`, `Mount_DividedInfo_FnoCorrectAbility.cpp`,
  `Mount_DividedInfo_IrisDrivabilityData.cpp`.

## Lens data model (camera-side vars)
- `b32_lens_serial_no`   lens serial number
- `uc_LensAttach`, `uc_LensMountStatus`, `b8_lens_power`
- `lens_id` (per `/lens/VX<id>_lensfile.bin` ISP calibration table)
- Mount flow: `NotifyLensAttach` -> mount -> `GetLensVersion` -> load
  `/lens/VX<id>_lensfile.bin` (see `verify/lensfile_parse.py` for format: `LF`
  magic, version, lens_id @+14, `ED` block of int16 coeff sections).

## USB host tunnel (how the PC reaches the lens)
- `sony_cmd.py` defines the raw tunnel: `USBC` CBW header + 68-byte `cam_struct`
  (command `code` at struct offset 0x0b, payload length at 0x1c).
- Code `0x12` = a query. Certain codes flip the camera PID to **0x994** (updater mode)
  — that is the lens-firmware-update entry point that drives `FirmUpReq`/`CASND LUPDT_*`
  over CAIF. See `scan_lensfirm2.py` (struct-code scanner 0x00..0xFF for PID flip).
- `zve10.py` is the AUTHENTICATED bridge (MSC PID 0x0d95 -> service PID 0x0336 via
  `senserShellCommand`); it is for filesystem/shell ops, NOT direct lens comms.

## Concrete next step (when camera is on USB bus)
Build `lens_query.py` (reuses `sony_cmd.py` tunnel): enter updater mode (PID 0x994),
send `GetLensVersion` over the relay, read back lens FW version + lens_id + serial.
This is READ-ONLY (no flash, no brick). The exact host-tunnel command code that maps
to `GetLensVersion` is not yet known statically — determine it live by trying the
updater-entry codes and dumping responses (see `lens_query.py`).

## Status
- Protocol architecture: MAPPED (this file).
- Exact host->camera USB code for GetLensVersion: UNKNOWN (needs live bus test).
- Live test pending: camera currently OFF BUS (E: unmounted, no USB device).
