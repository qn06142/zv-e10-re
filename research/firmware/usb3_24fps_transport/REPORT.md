# USB 3.0 SuperSpeed UVC Transport & 24fps Continuous RAW Pipeline Specification

**Date:** 31 October 2026  
**Scope:** Strictly Offline Static Analysis & Mathematical Modeling  
**Target Architecture:** Sony Alpha ZV-E10 (`cxd90045` / BIONZ X SoC)  
**Binaries Analyzed:**
- `.local/dumps/firmware/vmlinux.bin` (Linux 3.0.27_nl-rt106+, base `0x60108000`)
- `.local/dumps/camera_2025/usr/usr/lib/libInfraUsbCmn.so` (MD5: `31308976206a837f6f5c571992d2b499`)
- `.local/dumps/camera_2025/usr/usr/kmod/usbg_video.ko` (MD5: `5b59c2e62c80683d754955ab5de0467d`)
- `.local/dumps/firmware/av-cam.bin` (MD5: `cdcae9d4fdbf66a33704a4c7564e346d`, base `0x635c6000`)

---

## 1. Executive Summary

With the introduction of a physical USB 3.0 / 3.2 Gen 1 SuperSpeed connection and the operational requirement of targeting continuous video at **$\ge 24\text{ fps}$ minimum**, the transport bottleneck that previously constrained the camera over USB 2.0 High-Speed Bulk ($\sim 43\text{ MB/s}$ practical limit) is completely resolved.

Key findings established in this reverse engineering turn:
1. **DWC3 USB 3.0 Gadget Driver Built into Kernel:** The CXD90045 SoC hardware USB controller is Synopsys DesignWare Core USB 3.0 (`dwc3-gadget`), fully implemented in `vmlinux.bin` with hardware support for SuperSpeed control transfers (`SET_SEL`, `U1/U2` link states), streams, and bulk endpoint bursts.
2. **Native SuperSpeed Descriptors Already Exist in Factory Firmware:** In `libInfraUsbCmn.so`, the descriptor registration subsystem already defines a complete SuperSpeed descriptor set (`Set 3` at `0x1cca0`) containing:
   - Endpoint `0x81` Bulk IN with `wMaxPacketSize = 1024` (`0x0400`) and burst capability (`0x1cce8`).
   - Speed query via `usb_otgcore` ioctl `0x8001e30b`, mapping kernel speed `3` directly to `CUSB_SPEED_SUPER` (`0x2`) at table `0x1280c`.
3. **$\ge 24\text{ fps}$ Frame Rates Fit with Massive Bus Margin:** At sustained USB 3.0 SuperSpeed throughput ($\sim 380\text{ MB/s}$ usable), 1080p 10-bit Bayer RAW at 24 fps requires $59.3\text{ MB/s}$ (15.6% bus utilization); 1080p 12-bit RAW at 24 fps requires $71.2\text{ MB/s}$ (18.7% bus utilization); and 1280p 3:2 Open Gate RAW at 24 fps requires $70.3\text{ MB/s}$ (18.5% bus utilization). Even 30 fps 1080p 12-bit RAW ($89.0\text{ MB/s}$, 23.4%) fits easily.
4. **Continuous LiveView Sensor Readout Architecture Mapped:** Unlike single-shot still capture (`Wai>GetMmIdtRaw` / `Stg>ReadEndBase`), continuous LiveView frames are driven by `ReadKickLv` (`0x638f5ee2`), `ExpWaitBase` (`0x638f7396`), and `ReadExeLv` (`0x638f8820`). DFE sensor readout frames are ring-buffered via `0x63d8a232` (incrementing index at `[context + 0x6700 + 0x98 + 0x6fec]`), and `DUALREC_BAYER` (`0x63b322a0`, `0x63b324d4`, `0x63b32344`) operates directly on handle `[context + 0x67e0]` opened via `Capture_MemOpen` `0x63d8a42a`.

---

## 2. Kernel DWC3 USB 3.0 Subsystem Verification

Static analysis of `.local/dumps/firmware/vmlinux.bin` (base `0x60108000`) confirms full native SuperSpeed controller and gadget capabilities:

1. **DWC3 Hardware Controller Driver:**
   - Driver path: `drivers/usb/dwc3/ep0.c` and `dwc3-gadget`.
   - String literals confirm TRB (Transfer Request Block) ring management:
     - `dwc3-gadget: failed to register udc`
     - `drivers/usb/dwc3/ep0.c: Set SEL should be 6 bytes, got %d` (`SET_SEL` is standard USB 3.0 control request to configure System Exit Latency).
     - `&dwc->u1_u2_enable_mutex` (SuperSpeed link power management states U1 and U2).

2. **OTG Speed Detection & Control Interface (`usb_otgcore`):**
   - In `vmlinux.bin` at offset `0x1b4600` (virtual address `0x602bc600`), `usb_otgcore` implements ioctl dispatcher:
     - `0x8001e30b` (`_IOR(0xe3, 0x0b, uint8_t)`): Returns negotiated physical connection speed:
       - `1`: Full-Speed (12 Mbps)
       - `2`: High-Speed (480 Mbps)
       - `3`: SuperSpeed (5 Gbps)
     - `0x4040e311` (`_IOW(0xe3, 0x11, struct usb_otgcore_port_descriptor)`): Configures 64-byte port descriptor table.

---

## 3. Native SuperSpeed UVC Descriptors in `libInfraUsbCmn.so`

In `.local/dumps/camera_2025/usr/usr/lib/libInfraUsbCmn.so`, the UVC streaming interface structure defines three complete hardware speed branches:

### A. Speed Query & Enumeration
`CUsbSvc::getSpeed` (`0x9d6c`) calls ioctl `0x8001e30b` on `/dev/usb_otgcore` and indexes conversion table `0x1280c`:
```arm
0x9d94: ldr.w r0, [r3, r2, lsl #2]  ; r2 = (driver_speed - 1)
```
- Driver speed `1` (Full-Speed) $\to$ `0x3` (`CUSB_SPEED_FULL`)
- Driver speed `2` (High-Speed) $\to$ `0x1` (`CUSB_SPEED_HIGH`)
- Driver speed `3` (SuperSpeed) $\to$ `0x2` (`CUSB_SPEED_SUPER`)

### B. Interface Descriptor Sets (`streaming_ntsc_interface_desc` at `0x1cc60`)
The interface descriptor table contains three speed sets of 32 bytes each:
- **Set 1 (Full-Speed, `0x1cc60`):** Points to endpoint descriptor `0x1ccd4` (`wMaxPacketSize = 64`).
- **Set 2 (High-Speed, `0x1cc80`):** Points to endpoint descriptor `0x1ccc0` (`wMaxPacketSize = 512`).
- **Set 3 (SuperSpeed, `0x1cca0`):** Points to endpoint descriptor `0x1cce8` (`wMaxPacketSize = 1024`).

### C. Factory SuperSpeed Endpoint Descriptor (`0x1cce8`)
Memory dump of `0x1cce8`:
```
0x1cce8: 81 02 00 04 02 02 00 00 00 00 00 00 00 00 00 00
```
- `bEndpointAddress = 0x81` (Endpoint 1, IN direction)
- `bmAttributes = 0x02` (Bulk Transfer)
- `wMaxPacketSize = 0x0400` (**1024 bytes**, standard USB 3.0 Bulk packet size)
- `bInterval = 0x02`
- `bMaxBurst = 0x02` (Allows multi-packet burst transmission up to 3 packets per service interval)

Downstream pointer at `0x1ce1c + 0x10` links directly to UVC Class-Specific Video Streaming header hierarchy at `0x12625` (`wTotalLength = 61`).

---

## 4. Bandwidth Budget & Framerate Feasibility ($\ge 24\text{ fps}$)

On USB 3.0 SuperSpeed (5 Gbps with 8b/10b encoding, nominal raw bus $\sim 500\text{ MB/s}$, real-world sustained bulk payload $\sim 380\text{ MB/s}$):

$$\text{Throughput} = \text{Width} \times \text{Height} \times \text{BytesPerPixel} \times \text{FPS}$$

$$\text{dwFrameInterval} = \text{round}\left(\frac{10^7}{\text{FPS}}\right) \quad (100\text{ ns units})$$

### Bandwidth Evaluation Table

| Format / Mode | Resolution | Bytes/Pixel | Frame Size | FPS | dwFrameInterval | Sustained Throughput | Bus Utilization | Fits in USB 3? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1080p 10-bit Bayer RAW** | $1920 \times 1080$ | 1.25 B | $2,592,000\text{ B}$ | **24** | 416,667 (`0x065B9B`) | **$59.33\text{ MB/s}$** | **15.6%** | **PASS** |
| **1080p 10-bit Bayer RAW** | $1920 \times 1080$ | 1.25 B | $2,592,000\text{ B}$ | **30** | 333,333 (`0x051615`) | **$74.16\text{ MB/s}$** | **19.5%** | **PASS** |
| **1080p 12-bit Bayer RAW** | $1920 \times 1080$ | 1.50 B | $3,110,400\text{ B}$ | **24** | 416,667 (`0x065B9B`) | **$71.19\text{ MB/s}$** | **18.7%** | **PASS** |
| **1080p 12-bit Bayer RAW** | $1920 \times 1080$ | 1.50 B | $3,110,400\text{ B}$ | **30** | 333,333 (`0x051615`) | **$88.99\text{ MB/s}$** | **23.4%** | **PASS** |
| **1280p 3:2 Open Gate RAW**| $1920 \times 1280$ | 1.25 B | $3,072,000\text{ B}$ | **24** | 416,667 (`0x065B9B`) | **$70.31\text{ MB/s}$** | **18.5%** | **PASS** |
| **1080p YUY2 Uncompressed** | $1920 \times 1080$ | 2.00 B | $4,147,200\text{ B}$ | **24** | 416,667 (`0x065B9B`) | **$94.92\text{ MB/s}$** | **25.0%** | **PASS** |
| **3.2K 3:2 Open Gate RAW** | $3240 \times 2160$ | 1.25 B | $8,748,000\text{ B}$ | **24** | 416,667 (`0x065B9B`) | **$200.23\text{ MB/s}$** | **52.7%** | **PASS** |

**Conclusion:** All requested continuous raw video modes at $\ge 24\text{ fps}$ have $>45\%$ headroom on the USB 3.0 SuperSpeed physical link.

---

## 5. Continuous LiveView Sensor Readout Pipeline

Unlike photo still capture which executes through `Wai>GetMmIdtRaw` (`0x638d9892`) and `Stg>ReadEndBase` (`0x638f4018`), continuous video frames flow through the LiveView stage pipeline:

```
[ Sensor Readout Trigger ] -> ReadKickLv (0x638f5ee2)
                                   |
[ Exposure Initialization ] -> ExpIniLv (0x638f7302)
                                   |
[ Hardware Timing Fence ]  -> ExpWaitBase (0x638f7396) / ExpWaiAftLv (0x638f7782)
                                   |
[ LiveView Readout Exec ]  -> ReadExeLv (0x638f8820)
                                   |
[ Hardware DMA Config ]    -> Utl>DfeAcqSet (0x6390b96e) -> 0x63d782a4 (DFE Regs)
                                                         -> 0x63d785b4 (DMA Start)
                                   |
[ LiveView Ring Advance ]  -> 0x63d8a232:
                                 - Advances ring index: [context + 0x6700 + 0x98 + 0x6fec] += 1
                                 - Fires consumer completion callback via 0x63d2a730 (vtable[0x5c/4])
```

### Sensor Sub-Sampling & Binned Geometry
In `0x638ec2e8`, the camera configures the LiveView readout dimensions from full sensor capture geometry:
- Full sensor dimensions: `ldrh r3, [context + 0x6c00 + 0x36]` (Width), `ldrh r7, [context + 0x6c00 + 0x38]` (Height).
- 2x2 Binned / Half-sampling:
  - `[context + 0x6400 + 0xe0] = Width >> 1` ($6000 \to 3000$, or $3840 \to 1920$)
  - `[context + 0x6400 + 0xe2] = Height >> 1` ($4000 \to 2000$, or $2160 \to 1080$)
- 4x4 Sub-sampling:
  - `[context + 0x6400 + 0xdc] = Width >> 2`
  - `[context + 0x6400 + 0xde] = Height >> 2`

### Dual Recording RAW Pipeline (`DUALREC_BAYER`)
The functions `0x63b322a0` (acquire), `0x63b324d4` (start), and `0x63b32344` (release) are called in strict sequence from `0x638f2048`, `0x638f230a`, and `0x638f2398`.
- At `0x638f206a`, it resolves the native memory handle stored in `[context + 0x6700 + 0xe0]` (`context + 0x67e0`).
- It passes handle `[context + 0x67e0]` to `Capture_MemOpen` `0x63d8a42a`, mapping the physical DMA buffer for Bayer processing without interrupting the video stream.

---

## 6. Verification and Test Results

Verification was performed using:
- `research/firmware/usb3_24fps_transport/verify_usb3_descriptors.py`
- Output: `research/firmware/usb3_24fps_transport/usb3-verification.json`

Summary of automated test results:
1. `kernel_dwc3_superspeed`: **PASS** (`dwc3-gadget`, `SET_SEL`, `U1/U2`, `otgcore` switch verified).
2. `libInfraUsbCmn_superspeed`: **PASS** (Speed 3 $\to$ `CUSB_SPEED_SUPER`, EP `0x81` `wMaxPacketSize = 1024`, burst verified).
3. `bandwidth_budget_24fps`: **PASS** (All 7 modes at 24/30 fps fit comfortably within SuperSpeed budget).
4. Overall Test Result: **100% PASS**.
