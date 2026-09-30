# 01 — The device: platform, firmware images, and how to get them

Sony ZV-E10, firmware 2.02/2.03, kernel 3.0.27-rt.

- [Platform](#platform)
- [Two operating systems on one SoC](#two-operating-systems-on-one-soc)
- [USB modes](#usb-modes)
- [Firmware images](#firmware-images)
- [Decryption](#decryption-consistent-with-a-hardware-crypto-core)
- [The av-cam.bin string map](#the-av-cambin-string-map)
- [Unauthenticated input vectors](#unauthenticated-input-vectors)
- [Dumping a firmware image](#dumping-a-firmware-image)
- [Windows host gotchas](#windows-host-gotchas)
- [Toolchain traps](#toolchain-traps)

Related: [02-service-shell.md](02-service-shell.md) ·
[03-binaries.md](03-binaries.md) · [08-camera-interfaces.md](08-camera-interfaces.md) ·
[06-method.md](06-method.md)

## Platform
- SoC: Sony CXD900X0, quad ARM Cortex-A9 (ARMv7 rev1, NEON/VFPv4), ~1GHz
- RAM: 1GB + 256MB (mem=1G@0 + mem=256M@0x80000000@1 in cmdline)
- Kernel: 3.0.27_nl-rt106+ (PREEMPT RT), BusyBox v1.34.1, root shell
- Wi-Fi/BT: Broadcom BCM4339 (bcmdhd driver; bt_firm.hcd = "BCM4339 37.4MHz Sony DI 152H-0178")
- Storage: raw NAND (nflasha* nodes), SD card via BayHubTech (internal microSD) + USB reader
- Camera firmware: av-cam.bin (17.3MB) is a C++ app (libstdc++ exceptions, future/promise)

## Two operating systems on one SoC

- Linux is the **housekeeping** OS: USB, Wi-Fi/BT, HDMI/CEC, SD/MMC, GUI (`grm_gles`), buttons (`input`), IR (`sircs`).
- The **camera** (sensor / ISP / AF / AE / AWB / encode) runs in the `liro` RTOS alongside Linux on the same SoC.
- ~150 `liro-kliro_NN` userspace threads plus ~90 `liro-NN` hardware IRQs — that is the real imaging core.
- Bridge: `osal_uipc` (messages) plus `dmm` (3.1 MB shared-memory buffer manager).
- `/proc/iomem` shows **no** sensor/ISP registers, so Linux cannot touch the ISP directly; everything goes via uipc.
- The Wi-Fi card mounts only via liro (exFAT); the Linux kernel supports only ext2 / cramfs / vfat.

## USB modes
- MSC mode: PID 0x0d95 (libusb1, itfs 8,6,80). For pmca we Zadig'd this to libusb-win32.
- Service mode: PID 0x0336 (vendor ff/00/00). Reached by pmca switching the camera.
- After a CLEAN script exit the camera auto-recycles to MSC (no replug needed) -- UNLESS a
  process is orphaned (see Process pitfall). Then it stays in service mode / off bus.

## Decryption: consistent with a hardware crypto core

`av-cam.bin` has a 4 KB plaintext LIRO header stub (ARM reset vector
`0a0000ea`, `LIRO` magic at offset 4), then high-entropy body at offset `0x1000`.
`size mod 16 = 12`, which is not AES-ECB alignment.

The bootrom (`Astra Loader1 Ver.01.00 Nov 17 2015`, 24 KB) disassembly with
capstone:

- reset vector `ea00000a` → `b #0x58`
- **exactly one** `bl`/`blx` in the entire code region, so there is no AES routine to call
- references `KEY f:%x r:%x` as a debug string (`0x1344`), **not** a software key-expansion loop
- **no MMIO crypto-base writes** anywhere in the code region

Consistent with an onboard secure crypto core doing the decryption. Later
measurement refined this: 2,459 of 4,221 4 KB blocks are below 6.5 bits/byte and
the readable region spans the whole file, so the body is only *partly* opaque.

## Firmware images
Location: D:\02_Development_And_Projects\pmca-re\fw\
  dfe_dat.bin   65536   8c5f3b191dd124cf1ee2cb5055cec37e   (sensor reg/calib table, "LEO" 20180731)
  dfe_app.bin    1956   4d6d250734e0ad2e3ffe620de8afdf2b   (DFE driver: XDMAC/CPU padding errs)
  ldr_drv.bin    7012   7c8c16cd1090978558db9a9f4176c006   (Loader-Driver, uart)
  lif_app.bin    6716   7f4be40e8dc6afe24f7d0c64ceeb74b5   (Lens Interface app: uart+DMAC)
  wole_app.bin  10848   20ff1de413945a02ce06494e268bf9ec  (WoL-E main: port/power mgmt)
  bt_firm.hcd   61787   be8ac9166791929f152d64d5a637a93b  (BCM4339 BT firmware)
  bonobo.bin    172144  ce846fae07329955c71b0b3e16d000b0  (168KB, packed/resource?)
  initrd.img   2183168  a7d17524f296e10264ee59249eaa1fb0  (rootfs)
  vmlinux.bin  4117760  f5b6bc225e2e5158fecabead4108e9ab  (kernel)
  av-cam.bin  17289388  cdcae9d4fdbf66a33704a4c7564e346d  (liro camera app, C++)
Also: dumps\bootrom (24KB Astra Loader1, md5 n/a but verified ARM vector + strings)

## The `av-cam.bin` string map
- 161,595 plaintext strings. Subsystem counts: sen=920, codec=445, DFE=286, LIF=271,
  face=317, mag=476, hdmi=83, cec=90, backup=222, lens=268, iris=186, zoom=165,
  dmm=162, stream=147, SEC=115, sign=89, key=62, diag=441, Ver=374, liro=414.
- COMMAND SURFACE (prime targets):
  * CMD_ID_SDF_* : SDF_OPEN/CLOSE/EXEC/INPUT/OUTPUT/START/STOP/PAUSE/CANCEL/RESTART
    -> SDF_EXEC executes something. Gated behind authenticated service channel.
  * ExecCmd, ExecSensCmd, ExecReceive, ExecConnect, ExecApi* (command dispatch)
  * uipc / LIRO message handlers
- CRYPTO/AUTH (names only, real key in HW core): AES, sha, key_code, key_type,
  keymap table, "Key has been revoked", "key not available"
- PARSER/FORMAT (mem-corruption class): DECODE_JPEG_RSS, EncodeJpeg,
  LoadLensAberrationData, Parse*, LoadPriorityMedia, EXIF/TIFF/JPEG thumbnails
- 98 handler/entry symbols (Exec*, *Handler, *Callback, *Init, *Msg)

## Unauthenticated input vectors
1. SD CARD filesystem / EXIF / lensfile parsers (usbg_storage, LoadLensAberrationData).
   We have 61 VX*_lensfile.bin samples in /lens to mutate. MOST REACHABLE.
2. JPEG/EXIF decoder (DECODE_JPEG_RSS) fed a crafted image on the card.
3. USB MSC/MTP layer (usbg_stillimage) -- crafted filesystem metadata.
4. Wi-Fi/PTP services if exposed.
Service-mode CMD_ID_SDF_EXEC requires auth -> not a cold-boot vector.

## Toolchain traps

### The orphaned-process pitfall

Background runs that "exited" leave **orphaned** python children (the bash/timeout
wrapper dies, the child lives). An orphan holds the USB session, so the camera
stays in service mode or drops off the bus, and spurious `GenericUsbException`s
appear. **Always kill by PID, verify with `ps`, then replug.**

`zve10_dumpall.py`, `zve10_dumpfw.py`, `zve10_dumpcard.py` and `sample_isp.py`
all import `senser_fix` and call `_preflight()`, which refuses to start if another
`pmca-re` python is alive.

### `senser_fix.py` — a required monkeypatch

`pmca`'s `SonySenserDevice.sendSenserPacket` has a bug: in PID `0x0336` mode
`minSize=0`, but it still performs a 512-byte padding read after every
512-aligned chunk, swallowing `0x8000` (32,768) bytes of real payload and
desyncing the stream. **Without this patch `readFile` returns `size - 32768` and
corrupts data.** The patch removes the spurious read.

### The device scripts

- `zve10_replug_gate.py` — scan for any Sony device (PID `0x0d95` or `0x0336`); use as a bus check.
- `zve10_shell.py` — service-mode terminal driver (`writeTerminal` / `readTerminal` plus `pump()`). `pump()` waits out a silence window (`quiet_after=1.5s`) so slow `dd` replies are not misread as no-output. `-f file` runs command lists; `ZVE10_LOG` logs.
- `zve10_dumpall.py` — chunked `dd` → `/log` staging → pmca `readFile`, per-chunk md5 against the camera. Resumes per partition.
- `zve10_dumpfw.py` — same, for the ten `/system` firmware files rather than raw partitions.
- `zve10_dumpcard.py` — `dd` firmware onto a FAT32 card at `/tmp/sd/fw_dump/` (the fast path; the card reader does the heavy lifting). Idempotent mount, md5 on-card.
- `sample_isp.py` — pulls 64 KB samples of firmware blobs for entropy/string analysis.
- `disasm_bootrom.py` / `disasm_key.py` / `disasm_calls.py` — capstone disassembly of the bootrom.
- `analyze_strings.py` / `analyze_surface.py` — string, crypto and command-surface extraction from `av-cam.bin`.
- `verify/verify_zve10.py` — offline verification harness (import safety, chunk sizing, read-only invariants, preflight guard).

The current index is [`research/README.md`](../research/README.md); the live
device link is [`research/device/zve10_retry.py`](../research/device/zve10_retry.py).

## Dumping a firmware image
1. Format a <=32GB SD card to FAT32 (camera Linux can't mount exFAT; Windows GUI can't FAT32 >32GB
   -> use diskpart/Format-Volume in elevated PS, target USB disk by size+bus only).
2. In service-mode shell: mount -t vfat /dev/mmca1 /tmp/sd (idempotent: may already be mounted).
3. dd if=/system/<blob> of=/tmp/sd/fw_dump/<blob> bs=512; md5sum both sides.
4. sync; umount. Pull card -> PC reader -> copy + md5 re-verify.

## Windows host gotchas
- Zadig set reader (VID_1908 PID_0226) to WinUSB -> Windows wouldn't mount it.
- Fix: find OEM inf (pnputil /enum-drivers -> "VID_1908&PID_0226 (libwdi autogenerated)").
  Elevated PS: pnputil /delete-driver oem42.inf /uninstall /force; then rescan -> USBSTOR.
- Do NOT touch the ZV-E10's libusb driver (oem63 = VID_054C&PID_0D95) or the camera breaks.
