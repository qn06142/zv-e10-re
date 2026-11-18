# RAW Pipeline Stage Audit & Gating Resolution — 31 October 2026

Offline only. No live camera access, flashing, reboot, or modification.
Binary analyzed: `dumps/firmware/av-cam.bin` (MD5: `cdcae9d4fdbf66a33704a4c7564e346d`, base `0x635c6000`).

## 1. Critical Correction: Global Debug Gate `0x63d893f4`

Previous report `native-dump-20261031/REPORT.md` stated:
> "Global dump gate 0x63d893f4 checks whether 0x6396e358(1)!=9."

**Correction:**
Decompilation and original-instruction Unicorn emulation (`verify_raw_gates.py`) definitively prove the inverse:
```arm
63d893f4: push      {r3, lr}
63d893f6: movs      r0, #1
63d893f8: bl        #0x6396e358
63d893fc: sub.w     r2, r0, #9
63d89400: rsbs      r0, r2, #0
63d89402: adc.w     r0, r0, r2
63d89406: pop       {r3, pc}
```
Arithmetic:
- When `r0 == 9`: `r2 = 0`. `rsbs r0, 0, #0` sets Carry=1 (borrow=0). `adc r0, 0, 0` yields `1`.
- When `r0 != 9`: `r2 != 0`. `rsbs r0, r2, #0` sets Carry=0 (borrow=1). `adc r0, r0, r2` yields `(-r2) + r2 + 0 = 0`.

Thus, `0x63d893f4` returns `1` (gate OPEN) **strictly when `0x6396e358(1) == 9`** (reading `*(uint8_t*)0x644b8f11 == 9`). For all other return values (0..8, 10..), it returns `0` (gate CLOSED).

## 2. Discovery: Master RAW Allocation Decision Function `0x638f3adc`

In the DFE transfer stage (`0x638f647c`, `0x638f6800..0x638f6e00`), every call to `AllocMem_Raw_Snr` `0x638d9ff4` is gated by `0x638f3adc`:

```arm
638f3adc: push      {r3, r4, r5, lr}
638f3ade: mov       r4, r0
638f3ae0: ldr.w     r3, [r0, #0x790]
638f3ae4: ldr       r5, [pc, #0x5c]     ; GOT base 0x64638120
638f3ae6: cmp       r3, #2
638f3ae8: add       r5, pc
638f3aea: beq       #0x638f3b38         ; if mode == 2 -> returns 0
638f3aec: ldrb.w    r3, [r0, #0x841]
638f3af0: cbz       r3, #0x638f3afa
638f3af2: movs      r0, #0x6c
638f3af4: bl        #0x63d89408         ; CheckDumpEnabled(tag=0x6c)
638f3af8: cbnz      r0, #0x638f3b3c     ; if enabled -> returns 1
638f3afa: add.w     r2, r4, #0x6800
638f3afe: ldr       r3, [r2, #0x58]     ; capture mode [r4 + 0x6858]
638f3b00: cmp       r3, #2
638f3b02: beq       #0x638f3b28         ; mode 2: checks [r4 + 0x685c] == 1
638f3b04: cmp       r3, #3
638f3b06: beq       #0x638f3b0c         ; mode 3 or 1:
638f3b08: cmp       r3, #1
638f3b0a: bne       #0x638f3b40         ; other modes -> returns 0
638f3b0c: ldr       r3, [pc, #0x38]     ; GOT + 0x4b04 -> config 0x643bf438
638f3b0e: ldr       r3, [r5, r3]
638f3b10: ldrb.w    r0, [r3, #0x6c]     ; config[0x6c]
638f3b14: cbz       r0, #0x638f3b42     ; if config[0x6c] == 0 -> returns 0
638f3b16: add.w     r4, r4, #0x6800
638f3b1a: ldrb.w    r0, [r4, #0x5c]     ; [r4 + 0x685c]
638f3b1e: rsbs.w    r0, r0, #1
638f3b22: it        lo
638f3b24: movlo     r0, #0
638f3b26: pop       {r3, r4, r5, pc}    ; returns 1 if [r4 + 0x685c] <= 1
```

### Allocation Activation Pathways
1. **Debug Dump Path**:
   `[context + 0x841] != 0` AND `CheckDumpEnabled(0x6c)` returns 1.
   Requires:
   - Global gate `0x63d893f4`: `0x644b8f11 == 9`
   - Selection gate `0x6390878c`: Tag `0x6c` (108) configured in `0x6451d90d +0xf1..+0xf5` or profile `+0xf0`.
2. **Normal Still Capture Path**:
   `[context + 0x6858]` is 1 or 3, AND `configstorage 0x643bf438 + 0x6c != 0`, AND `[context + 0x685c] <= 1`.

## 3. Discovered Camera Pipeline Stage Architecture

Tracing all calls to the execution logger `0x63909338` mapped the Sony camera pipeline stages:

| Stage Address | Trace String | Subsystem / Purpose |
|:---|:---|:---|
| `0x638d9892` | `Wai>GetMmIdtRaw` / `Wai<GetMmIdtRaw` | Immediate RAW Memory Unit `0x20500` acquisition |
| `0x638d9906` | `Wai>GetMmPreRvw` | Preview Review Memory acquisition (`0x1b9` / `0x509`) |
| `0x638f4074` | `Stg>ReadEndBase` | Post-readout completion & native dump caller |
| `0x638f4b22` | `Stg>ReadEnd` / `Stg<ReadEnd` | Sensor frame readout completion stage |
| `0x638f4d36` | `Stg>TDReadEnd` / `Stg<TDReadEnd` | Time-domain / tracking sensor readout end |
| `0x638f5674` | `Wai>CamStart` | Sensor start synchronization barrier |
| `0x638f5ee2` | `ReadKickLv` | Continuous LiveView readout trigger |
| `0x638f6422` | `Stg<ReadExeBase` | Sensor readout execution base |
| `0x638f6ae2` | `Stg>ReadExe` / `Stg<ReadExe` | Sensor readout execution stage |
| `0x638f7302` | `Stg<ExpIniLv` | LiveView Exposure Initialization |
| `0x638f7396` | `Stg>ExpWaitBase` / `Stg<ExpWaitBase`| Exposure timing wait stage |
| `0x638f7782` | `Stg>ExpWaiAftLv` / `Stg<ExpWaiAftLv`| LiveView post-exposure wait stage |
| `0x638f8506` | `Wai>ExpEndWait` / `Wai<ExpEndWait` | Hardware exposure end fence |
| `0x638f8820` | `Stg<ReadExeLv` | Continuous LiveView sensor readout execution |
| `0x638f9320` | `Stg>ExpWai1stLv` / `Stg<ExpWai1stLv`| First-frame LiveView exposure wait |
| `0x638ffe44` | `Stg>CapIni` / `Stg<CapIni` | Capture subsystem initialization |
| `0x6390a03e` | `Utl>StrtRdrawRd` / `Utl<StrtRdrawRd` | Start RAW DFE DMA readout |
| `0x6390b96e` | `Utl>DfeAcqSet` / `Utl<DfeAcqSet` | DFE hardware acquisition register setup |
| `0x6390d082` | `EC:CapRawCapIni` | Exposure Control: RAW capture initialization |
| `0x6390d31a` | `EC:CapRawExpIni` | Exposure Control: RAW exposure start |
| `0x6390d398` | `YC:CapRawExpIni` | YC Processor: RAW exposure setup |
| `0x6390d578` | `EC:CapRawExpWai` | Exposure Control: RAW exposure completion wait |

## 4. RAW Dump Dispatch Mechanism in `ReadEndBase` `0x638f4018`

At the end of sensor readout in `ReadEndBase`:
```arm
638f40cc: mov       r0, r7              ; r7 = [context + 0x6d54]
638f40ce: bl        #0x63d7937a         ; dereference
638f40d2: ands      r7, r0, #0x20
638f40d6: bne       #0x638f4142         ; if bit 0x20 is SET -> SKIP dump
638f40d8: mov       r0, r6              ; r6 = [context + 0x6d60]
638f40da: bl        #0x63d7937a
638f40de: tst.w     r0, #0x10
638f40e2: beq       #0x638f4142         ; if bit 0x10 is NOT SET -> SKIP dump
638f40f2: ldr       r2, [pc, #0x68]     ; config object 0x643bf438
638f40f4: ldr       r2, [r5, r2]
638f40f6: ldrb.w    r0, [r2, #0x6c]     ; read config[0x6c]
638f40fe: cbz       r0, #0x638f411a
638f4100: ldrh.w    r1, [r3, #0xb6]     ; r1 = RAW handle [context + 0x67b6]
638f4104: movs      r0, #1              ; Tag = 1
638f4106: mov       r3, r4              ; context
638f4108: str       r6, [sp]            ; 0
638f410a: bl        #0x6390897c         ; call MemAreaMSDebug_RAW
```

Inside `MemAreaMSDebug_RAW` `0x6390897c`:
1. Validates `0x63d893f4` (global gate `0x644b8f11 == 9`).
2. Validates `0x6390878c` (selection gate: Tag 1 in `0x6451d90d`).
3. Calls `Capture_MemOpen` `0x63d8a42a` on handle `[context + 0x67b6]`.
4. Checks `configstorage 0x6451d90d + 0xf6`: if 0, bypasses decompression, keeps raw sensor bytes.
5. Dispatches 24-byte packet `(op=1, tag=1, address, length, mode=0)` to Linux endpoint `0x012802f1`.
6. `CameraOnDemandSaver.so` thread receives the message.
7. Hooked by `raw_receiver_v01` (`raw_capture_v01.so` at GOT `+0xa18c`), saving frame to `/log/raw_capture_v01/{request.bin, frame.bin, complete.bin}`.
8. Closes handle via `Capture_MemClose` `0x63d8a480`.

## 5. Path to Raw Video

For video applications:
1. **Continuous / Burst RAW video**:
   In burst modes (up to 11 fps full-sensor on ZV-E10), `ReadEndBase` is invoked per frame. Enabling the dump gates routes sequential full-resolution Bayer RAW frames directly to `/log/raw_capture_v01/` or a custom FIFO/USB spooling daemon.
2. **LiveView Continuous Sensor Feed**:
   LiveView stages (`ReadExeLv`, `ReadKickLv`, `ExpIniLv`) continuously cycle without entering still `ReadEndBase`. Sensor Bayer acquisition directly from the DFE ring buffer before BIONZ demosaicing bypasses the SDF/resizer limitations.
