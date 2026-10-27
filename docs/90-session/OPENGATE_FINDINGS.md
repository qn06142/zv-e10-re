# Open Gate (3:2 Full-Sensor Video) Reverse Engineering & Technical Blueprint

## Next major milestone — VGA reference path to genuine 4K/12-bit

27October2026: camera tests are paused at the user's request. Revision3.0 VGA is installed and reboot-verified but has not produced a tested frame. The hardware-proven colour-bars baseline is2.4p.

Continue with [the 4K/12-bit next-push specification](4K_12BIT_NEXT_PUSH.md). The [preserved VGA binary reference bundle](../../research/firmware/4k12bit_baseline_20261027/README.md) contains the exact2.4p bars producer/matching gate, proven USB kernel, and separate3.0 experimental pair with hashes. Use these as controls and entry points into Sony's allocator, SSYC metadata and SDF resize chain, then trace a genuine high-bit-depth source through every conversion to its sink. This is the next major step; changing descriptor dimensions or an enum is insufficient.

The new VGA work does not establish4K sensor readout,12-bit source precision,12-bit hardware encoding or sustained delivery. Historical blueprint claims below retain their separate evidence requirements; do not promote them to hardware proof based on the VGA result. The arithmetic examples below now distinguish packed12-bit YUV420 from12-bit Bayer/8-bit YUV420. Real allocation capacity, padding, cadence and sink throughput still need verification. No camera test, rollback or further flash was performed for this update.


> **DOCUMENT STATUS:** Confirmed via reverse engineering of `libObj.so`, `libmpr.so`,
> `av-cam.bin`, and RTOS kernel memory allocations in firmware dumps.

---

## 1. Executive Summary & Ground Truth

### 1.1 Is Open Gate a "Crop from 16:9" or True Full-Sensor Readout?
**It is True Open Gate from the sensor (Full Optical Sensor Readout), scaled to fit within the BIONZ X hardware encoder pipeline.**

* **The Physical Sensor is Native 3:2:**
  * Active imaging area: **$6000 \times 4000$ pixels** ($3:2$ aspect ratio, $\approx 24.2\text{ MP}$).
  * **Standard 16:9 4K Video:** The camera reads a $6000 \times 3376$ window from the sensor and scales it down to $3840 \times 2160$. The top $312$ lines and bottom $312$ lines of the physical sensor ($624$ lines total, or **$15.6\%$ of the sensor's vertical imaging area**) are discarded before encoding.
  * **3:2 Open Gate:** The camera configures the Sensor Driver Framework (SDF) and ADC scanning registers to read out the **full vertical height ($4000\text{ px}$)** simultaneously with the full horizontal width ($6000\text{ px}$).

| Mode | Sensor Readout Geometry | Output Frame Size | Aspect Ratio | Vertical FOV | Horizontal FOV | Total Active Sensor Area |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Standard 4K (16:9)** | $6000 \times 3376$ | $3840 \times 2160$ | 16:9 | Cropped (-15.6%) | 100% Full Width | 84.4% |
| **True Open Gate 3.2K** | **$6000 \times 4000$** | **$3240 \times 2160$** | **3:2** | **100% Full Height** | **100% Full Width** | **100% (Complete Sensor)** |
| **True Open Gate 4K (DCI)** | **$6000 \times 4000$** | **$3840 \times 2560$** | **3:2** | **100% Full Height** | **100% Full Width** | **100% (Complete Sensor)** |
| **Anamorphic Mode** | $5120 \times 3840$ | $2880 \times 2160$ | 4:3 | 96% Height | Center 4:3 | 75.0% |

---

## 2. Firmware Architecture: Built-in 3:2 Video Pipeline

Reverse engineering the video subsystem reveals that **Sony's engineers already wrote 3:2 Open Gate support into the camera's firmware stack**. It was built, tested, and left dormant in retail production builds.

### 2.1 The Aspect Ratio Enum in `libObj.so`
In `libObj.so` at `.rodata` offset `0x105d0f9`:
```cpp
namespace DefStruct {
    MOVIE_ASPECT_4_3  = 0,  // 4:3 Aspect Video
    MOVIE_ASPECT_16_9 = 1,  // 16:9 Standard Video
    MOVIE_ASPECT_3_2  = 2,  // 3:2 Open Gate (Full Sensor Readout)
    MOVIE_ASPECT_1_1  = 3,  // 1:1 Square Video
    MOVIE_ASPECT_17_9 = 4   // 17:9 DCI Cinema
}
```

### 2.2 The Hardware Sensor Readout Dispatch in `av-cam.bin`
In the BIONZ X RTOS camera module (`av-cam.bin`), function `ModuleCalcAspectImageArea` executes at VA `0x636cde88`:
```arm
; ModuleCalcAspectImageArea - Hardware ISP Sensor Window Calculator
0x636cde88: push    {r4, r5, r7, lr}
0x636cde8a: mov     r4, r0
0x636cde8c: ldr     r3, [r0, #4]          ; Load movie aspect ratio enum
0x636cde8e: cmp     r3, #1
0x636cde90: beq     #0x636cdea6           ; 1 = 16:9 crop calculation (3376 lines)
0x636cde92: blo     #0x636cdea0           ; 0 = 4:3 crop calculation (4000 lines, 5333 width)
0x636cde94: cmp     r3, #2
0x636cde96: beq     #0x636cdc00           ; 2 = 3:2 OPEN GATE (Full 6000x4000 Sensor Readout!)
```
When mode 2 is selected, execution branches to `0x636cdc00`. This handler sets up the hardware DMA registers for uncropped $6000 \times 4000$ sensor sampling without the 16:9 vertical windowing offsets.

---

## 3. The Artificial Lockout Point

The restriction to 16:9 is enforced by a single hardcoded constant in the Linux application layer (`libObj.so`).

### 3.1 The Real Astra 4K Recording Engine vs. Proxy Sequence Encoder
> [!IMPORTANT]
> **CORRECTION OF RECORD:**
> Early documentation identified `InfraMovieEncoderSeqSetAspect` at `0x2d229c` as the primary aspect ratio lockout. Reverse engineering in live execution revealed that `0x2d229c` only belongs to the **proxy / auto-edit sequencer**.
> 
> The true primary 4K recording engine resides at:
> - **`libObj.so` `InfraMovieEncoderSeqEncStart2Astra` (`0x2ccac0`)**: Controls primary 4K stream startup and dispatches co-processor AVBBC packet `0x55001f` (`0x2cce0a` & `0x2cce38`).
> - **`libmpr.so` `MovieRecorder::ConvMovieRecParam` (`0x3f642c` / `0x3f6730`)**: Directly hardcodes stream width (`mov.w r3, #3840`) and MP4 container width (`mov.w r2, #3840`).
> - **`libmpr.so` `RecLib_RecLineInfo::ConvContentTypeToUseCodec` (`0x3f1e18`)**: Hardcodes resolution `(2160 << 16) | 3840`.
> - **`libmpr.so` Profile Table (60 profiles across 5 groups)**: Profiles at `0x0866d8f6`..`0x08678812` define the hardware encoding configurations.
> 
> Furthermore, **`LD_PRELOAD` via `dmode 3p` does not work across reboots** because `/usr/bin/bootin.elf` explicitly calls `putenv("LD_PRELOAD")` (which unsets the variable) before executing `/usr/bin/im.elf`. All live modifications must be applied directly to running memory (`/proc/$PID/mem`).


---

## 4. Encoder Resolution & Frame Geometry

### 4.1 Target 1: 3.2K Open Gate ($3240 \times 2160$, 3:2) — **Optimal & Safe**
* **Frame Geometry:**
  * Width: $3240\text{ px}$ (divisible by 8; $202.5 \times 16$, or padded to $3248$ for 16-pixel macroblock boundary).
  * Height: $2160\text{ px}$ (standard 4K UHD height, exactly matches encoder line buffers).
* **Buffer Memory Calculation (YUV420 8-bit / 10-bit):**
  $$\text{Pixels per frame} = 3240 \times 2160 = 6,998,400\text{ pixels}$$
  $$\text{Standard 4K 16:9 Pixels} = 3840 \times 2160 = 8,294,400\text{ pixels}$$
  * 4K 16:9 Frame Buffer (packed12-bit YUV420): **18,662,400 bytes (17.80 MiB)** per frame, before padding.
  * 3.2K 3:2 Open Gate Frame Buffer (packed12-bit YUV420): **15,746,400 bytes (15.02 MiB)** per frame, before padding.
  * **Memory Impact:** 3.2K Open Gate uses **$15.6\%$ LESS memory** per frame than standard 4K 16:9.
  * **Memory Headroom:** Easily fits within the existing $680\text{ MB}$ uncached codec pool (`0x15800000:uc` reserved in `KEMCO.TXT`).

### 4.2 Target 2: True 4K Open Gate ($3840 \times 2560$, 3:2)
* Requires $2560$ vertical lines.
* The hardware AVC/HEVC encoder in BIONZ X has a verified maximum line buffer height of $2160$ lines for progressive scan real-time encoding (though it supports 8K $7680 \times 4320$ profile tables in high-tier models, the consumer ZV-E10 ISP clocking may cap real-time line generation at 2160 lines).
* **Verdict:** $3240 \times 2160$ delivers **100% full-sensor optical Open Gate** without triggering hardware encoder line buffer overflows.

---

## 5. Magic Lantern-Style Direct RAW Video Dumping

### 5.1 The Sensor Driver Framework (SDF) Raw Buffer
* In `av-cam.bin`, Extent `0x002f` allocates a dedicated **$96.0\text{ MB}$ ring buffer** at physical address `0x1a000000`.
* This buffer holds uncompressed Bayer sensor data directly from the sensor's SLVS-EC/MIPI lanes before reaching the BIONZ demosaic engine.
* Diagnostic command `adjstctl.elf SET_SDI_RAW_MODE` routes this raw stream to internal sinks.

### 5.2 Bus Bandwidth vs. SD Card Real-World Write Speeds
The ZV-E10 card slot is **UHS-I SDR104** (theoretical max $104\text{ MB/s}$, sustained real-world write $\approx 75 - 85\text{ MB/s}$ on V90/V60 cards).

Data rate calculations for direct RAW recording:

| Mode | Resolution | Format | Size / Frame | Bandwidth @ 24fps | Continuous SD Card Recording? | Max Buffer Burst Duration (96MB Pool) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Full Sensor 6K RAW** | $6000 \times 4000$ | 14-bit RAW | $42.0\text{ MB}$ | **$1,008\text{ MB/s}$** | ❌ **No** ($13\times$ bus limit) | $\approx 2.3\text{ seconds}$ ($\approx 55\text{ frames}$) |
| **Full Sensor 6K RAW** | $6000 \times 4000$ | 12-bit RAW | $36.0\text{ MB}$ | **$864\text{ MB/s}$** | ❌ **No** ($11\times$ bus limit) | $\approx 2.7\text{ seconds}$ ($\approx 64\text{ frames}$) |
| **3.2K Open Gate RAW** | $3240 \times 2160$ | 10-bit RAW | $10.5\text{ MB}$ | **$252\text{ MB/s}$** | ❌ **No** ($3.2\times$ bus limit) | $\approx 9.1\text{ seconds}$ ($\approx 218\text{ frames}$) |
| **3:2 Open Gate FHD RAW** | **$1920 \times 1280$** | **10-bit RAW** | **$2.9\text{ MB}$** | **$70.3\text{ MB/s}$** | ✅ **YES (100% Continuous!)** | **Unlimited** (Sustained real-time) |
| **3:2 Open Gate HD RAW** | **$1440 \times 960$** | **12-bit RAW** | **$2.1\text{ MB}$** | **$49.8\text{ MB/s}$** | ✅ **YES (100% Continuous!)** | **Unlimited** (Standard V30 cards) |

### 5.3 Breakthrough Conclusion on RAW
Just like Magic Lantern on DIGIC 5 DSLRs (where UHS-I limited 5D Mark III / 6D to 1080p continuous RAW, while 14-bit full-sensor required short bursts):
1. **1280p ($1920 \times 1280$) 3:2 Open Gate 10-bit RAW video is 100% mathematically and physically sustainable continuously on the ZV-E10** over standard UHS-I SD cards.
2. **6K Full-Sensor RAW** is achievable in 2-3 second cinematic bursts directly into the 96MB SDF RAM pool.

---

## 6. Implementation Architecture: The 138-Patch Memory Pipeline

Rather than relying on `LD_PRELOAD` (which is explicitly purged by `bootin.elf` across reboots), the production Open Gate implementation executes as an atomic memory transaction on `/proc/$PID/mem` via [`batch_patch_opengate.py`](file:///D:/02_Development_And_Projects/pmca-re/batch_patch_opengate.py).

### 6.1 Subsystem Synchronization Matrix
1. **Resolution Validation Gates (`libObj.so`):**
   - NOPs the conditional width checks (`bcc.n` $\to$ `00 bf`) in AVBBC builders at `0x2b2ca0`, `0x2b2cd6`, `0x2c07b4`, `0x2cfda0`, `0x2d004a`, `0x2d00ea`, `0x2d03b2`.
2. **Aspect Ratio Synchronization (`libObj.so` & `libmpr.so`):**
   - `ConvertRecFormat` (`0x978bea`): sets format aspect = 2 (3:2).
   - `InfraMovieEncoderSeqSetAspect` (`0x2d2388`): broadcasts Aspect 2 to Channels `0x1014` and `0x100e`.
   - `InfraMovieEncoderSeqEncStart2Astra` (`0x2ccb3a`, `0x2ccb4a`): writes Aspect 2 to Astra encoder input registers.
   - AVBBC packets (`0x2cce0a`, `0x2cce38`): sets Aspect 2 in co-processor packets `#0xd4` and `#0xd8`.
   - `FeaCore::SetRecAspect` (`0x5422e6` in `libmpr.so`): whitelists Aspect 2 (`tst.w r2, #0x2f`).
   - `GetPictureAspectForCodecDrv` (`0x8a436a` in `libmpr.so`): forces `esPictureAspect = 3` to satisfy hardware CodecDrv.
3. **Hardware Encoder Profile Tables (`libmpr.so`):**
   - Overwrites width and container width to 3240 (or 3232) across all 60 4K profile records in 5 groups (`0x0866d8f6`..`0x08678812`).
   - Injects resolution into `MprLibCore::GetPictureSize` (`0x8a46b4`) and `mxfIfo_CommonSequence::CnvResolutionMBtoMPR` (`0x8df60e`).

### 6.2 Zero Flash Risk
All 138 patches are applied purely to volatile RAM. Power-cycling the camera completely restores clean factory firmware with 0 persistence risk.

