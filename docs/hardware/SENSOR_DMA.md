# Sensor, DFE and DMA hardware contracts

The priority route is sensor → acquisition/DFE → a completed Bayer buffer → an independently owned USB transfer. Each boundary needs a physical register/transaction contract. Linux driver APIs and firmware stage names are leads, not substitutes for that contract.

## Sensor control and acquisition

| Item | Established evidence | Still missing |
| --- | --- | --- |
| Sensor model and electrical control link | Earlier firmware tables and acquisition paths exist. | Independently confirmed sensor identity, control-bus instance/pins, bus timing, device addressing, reset/standby/power order. No model is guessed here. |
| Mode programming | Earlier mode/geometry table extraction exists. | Actual serial transaction sequence, sensor register addresses/widths/bank selection, documented reset/required values and validated readout mode. An image-size table is not proof of sensor support or open-gate operation. |
| Sensor-to-SoC data link | Native acquisition and DFE stage leads. | Physical receiver, lane/pin mapping, clocking, packet or parallel format, sync polarity and receiver programming. Do not assume a particular CSI/MIPI/SLVS link. |
| DFE setup | The reference image enters DfeAcqSet at 0x6390b93c and StrtRdrawRd at 0x6390a014. Selected FOPD MMIO writes and routing fields are verified below. | These are firmware virtual addresses, not hardware registers. Trace their actual base-address providers, descriptor words, start and completion conditions. |
| DFE callbacks | Native slots 3, 9, 10, 11 and 14 are registration leads; slot 10 signals event 0x16. | Callback slot → hardware fact → IRQ/status/ack mapping, and exact frame-buffer ownership. |
| Runtime cadence | SetImgRd about 41.6–41.8 ms and other preview markers about 20.8 ms in saved sessions. | Marker-to-frame association, exposure/readout timing, Bayer packing and usable completion-to-reuse interval. |

Source scope: [later RAW pipeline audit](../../research/firmware/raw_frame_source/verified_bayer/evidence/raw-pipeline-audit-20261031/REPORT.md), [reviewed runtime claims](../../research/firmware/evidence/zve10-20261117/CLAIM_REVIEW.md). Those offline firmware addresses are bound to their recorded image, not automatically the current body. The native accessor corpus is mostly display-related and does not fill this sensor register gap.

## RAW readout and FOPD routing

An offline audit of `av-cam.bin` (SHA-256 recorded in the [FOPD contract](data/dfe-fopd-contracts.json)) maps part of the RAW readout path to the `0xf302xxxx` MMIO aperture encoded by the firmware. It covers instruction behavior in this reference image. Fourteen selected file pages matched the installed image over Senser, including the AIF table, routing helpers and write-channel adapter. The overall image hashes differ. The capture read firmware files only. Hardware effects and reset values remain unverified. [Body page hashes](../../research/device/zve10_hardware_map/evidence/20261120-senser-fopd-identity.json)

The `StrtRdrawRd` function starts at firmware VA `0x6390a014`. The previously reported `0x6390a03e` is its trace call. It builds a request at context `+0x6d70` and calls `0x63b61540` or `0x63b618c8` depending on its third input. Both targets reference `S:A_KickFOPD`. The second receives an extra eight-byte structure built by `0x63d89d1e`. The separate `DfeAcqSet` function starts at `0x6390b93c` and traces at `0x6390b96e`. Its helper `0x6390b8a0` reaches `0x63d73502` through `0x638cf374`, builds a zero-initialized 52-byte request and passes it to `0x6379cb68`. This is a separate setup path worth tracing to its register writes.

| MMIO address | Recovered contract |
| --- | --- |
| `0xf302078c` | 32-bit read-modify-write. The low five bits of a software mask select two-bit fields at bit positions 0, 4, 8, 12 and 16. Selected fields take the supplied selector (0–3). With match-clearing enabled, unselected fields equal to that selector become 3. All other bits are preserved. The two KickFOPD paths call this helper with match-clearing enabled. |
| `0xf3020790` | A separate routine at `0x63d20e4e` first sets the selected routing fields to 3. It then writes the incoming second argument ORed with one bit at the bottom of each selected field, followed by a zero write. This order is verified. The physical effect of the pulse remains open. |
| `0xf30207b8`, `0xf30207bc`, `0xf30207b4` | On the traced branches, the first KickFOPD path writes 0, 0, 0 in that order. The second writes 1, 1, 0. The purpose of these registers remains open. |
| `0xf3020518`, `0xf3020558`, `0xf3020598` | The first callback of each of three rows in the firmware dispatch table at `0x645f2114` writes its 32-bit input here, with a 0x40-byte stride. The other callbacks and these words' meanings need further tracing. |

### FOPD AIF buffer and status registers

The FOPD error path at firmware VA `0x63793fd0` identifies the banks as R0 and W0 through W4. It tests bit 0 of each channel's `+0x00` and bit 31 of `+0x04` before calling cleanup. The 12-byte firmware table at `0x63e89724` independently maps IDs `0x11..0x16` to bases `0xf3020200, 0xf3020280, 0xf3020300, 0xf3020380, 0xf3020400, 0xf3020480` in that order. The IDs are firmware AIF indices.

| Offset or word | Verified reference operation |
| --- | --- |
| Channel `+0x20` / `+0x24` | For each write bank, the adapter at `0x63d1f1bc` takes the input buffer word at `+0x0c` via the `(0x10, 1)` identity address branch and programs it to `+0x20`. The input word at `+0x04` goes to `+0x24`. In the tested mode a low alignment bit produces `-8` before any MMIO write. Mode 3 in the low-level config writer uses `0xff000000` at `+0x20`. |
| Channel `+0x0c` and `+0x10` | The config routine writes a separate word to `+0x0c` on the tested write branches, skipping it when existing control bit 5 and status bit 31 are both set. R0 writes zero there. The accessor at `0x639e231c` reads `+0x10` unchanged. Its layout makes it a current-address candidate for a later capture. |
| Channel `+0x28..+0x44` | The geometry writer alternates four 32-bit inputs with four zero-extended 16-bit inputs. Dimensions, units and packing depend on the caller. |
| Channel `+0x00` / `+0x04` | The start helper sets bit 0 in `+0x00`. The cleanup prefix clears bit 0 in `+0x04`, clears bit 0 in `+0x00`, then sets bit 30 in `+0x04`. Each helper does a register readback and mirrors the resulting word to firmware RAM. |
| Unit `0xf3020000` | One four-bit field per mapped bank, starting at bit 0 for R0 and bit 20 for W4. The read helper extracts the selected nibble. The write helper writes only the supplied low nibble shifted to that position, then reads back the word. The actual interrupt and acknowledge effects are still open. |

The audit passed 1,267 original-instruction cases. It used synthetic buffer addresses and simulated MMIO. The USB session separately matched 14 installed firmware pages and performed no MMIO access or camera file writes. Binding an active write bank to a completed Bayer frame still requires tracing the live-view producer and consumer across completion and reuse. [Reproduction command](../../research/device/zve10_hardware_map/README.md)

## Distinct DMA engines

| Engine/path | Source-defined map or recovered behavior | Unresolved hardware contract |
| --- | --- | --- |
| XDMAC | GPL UDIF groups at 0xf0000000 and 0xf0010000, each declared 64 KiB; logical channels 0–3 and 4–7 share their respective group window. IRQ bases 189/193. Offline `dmac.ko` instruction checks recover `XDACS`, all 9 channel registers, 48-byte LLI start, `XDDSD` ack and shutdown. | Live-body `dmac.ko` identity, descriptor attribute fields (`XDSAC`/`XDDAC`/`XDDCC`) and sensor/DFE channel-to-buffer ownership remain open. |
| DMA330 | GPL UDIF declares 0xf0030000, size 64 KiB, with channel IRQs 115–118 and abort 119. Offline `dma330.ko` instruction checks recover 60 mapped registers, `DMAGO`/`DMAKILL` debug-port sequences, `INTCLR` and 4 `.data` PL330 template arrays. | Live-body `dma330.ko` identity, per-field `CCR` tuning beyond template presets and stronger source-reuse fencing in callers remain open. |
| Sensor/DFE/ISP DMA | Native acquisition and RAW allocation/dump paths exist. | Which engine moves which image plane, address translations, descriptor lifetime, stride/packing and ownership. It is not established to be the USB DMA330 path. |
| USB staging copy | Audited usbg_video path calls dma330_mem_transfer_async from source PA to staging +12. | A source-reuse fence stronger than submit return value, and confirmed cancellation/drain behavior. |
| PCIe/device DMA | PCIe apertures and GRM/DMP driver structure exist. | Endpoint/BAR binding, shared-address translations, command format and quiescence. Not interchangeable with XDMAC or DFE. |

## USB submission contract already recovered

For the specific audited usbg_video.ko identity in the [USB lifetime audit](../../research/firmware/raw_frame_source/verified_yc/evidence/usb-lifetime-20261029/REPORT.md), submission 0x4008f003 consumes two little-endian 32-bit words in order: size, physical source. 0xf002 checks staging availability. Neither fact establishes Bayer input or a zero-copy path.

The audited timeout path can mark staging ready and return success without proving completed DMA. Stop/release paths lack an identified cancel operation in that audit. Preserve the report's exact binary scope; the installed module may be a later patched version. Its inferred explanation of a historical crash is separate from the directly recovered instruction behavior.

## Required buffer description

Before copying a live Bayer frame, identify physical span and owner, format/CFA/bit depth, dimensions and crop, row/plane stride, compression or tiling, cache attributes, producer-start event, producer-completion fact, consumer fence and earliest reuse time. A handle, virtual mapping, IRQ count, elapsed delay or successful submit is insufficient alone.

DMM handles, physical/bus addresses, Linux mappings and firmware pointers must remain typed separately. Native RAW allocation/dump gates are firmware logic and must not be represented as sensor MMIO registers. A native one-shot dump is not yet a verified continuous Bayer stream.

## XDMAC channel 5 in normal shooting

Two saved stock-mode captures show channel 5 IRQ 194 advancing at nearly the same rate. In [live view](../../research/firmware/evidence/zve10-20261117/additional-captures/live_view_full_1.txt) the counter advanced from 35601 to 35651 over 1.05 s of sampled uptime (about 47.6 IRQ/s). In [4K24 recording](../../research/firmware/evidence/zve10-20261117/additional-captures/rec_4k24_full_1.txt) it advanced from 51877 to 51939 over 1.31 s (about 47.3 IRQ/s). These are interval averages from sequential proc reads. Neither capture associates a specific interrupt with sensor frame completion.

Both DMAC dumps label channel 5 ASYNC, report its register base as 0xf0010040, and report zero current request, pending count, lli_phys and XDTBC. The saved XDSSA / XDDSA pairs differ between modes (0xfc034ad8 / 0x115071d8 in live view and 0xfc0364d8 / 0x115126c0 in recording). No in-flight descriptor or owner accompanies either pair. They therefore cannot establish a Bayer buffer address or a safe reuse interval. The channel base is a measured point for channel 5. The offline driver analysis below resolves the stride.

## XDMAC channel register stride

The saved initrd module kmod/dmac.ko (SHA-256 718284caacf31654151fac234db7293d8338e348687c37b6e3f65dbf24de1522) defines boss_lld_get_base_addr_dmac_ch at ELF .text+0x830. During probe the driver saves the mapped group base for each channel. For supported channels 0 through 7 the helper returns group base + 0x10 + 0x30 times the channel index within its group of four. The per-channel software records in dmac_async_probe have a separate 0x3c-byte stride.

An offline ARM instruction run resolved the helper's .data relocation to a scratch table, supplied the two GPL group bases, and checked the returned pointer for all eight channels. Offsets within each group were 0x10, 0x40, 0x70 and 0xa0. Channel 5 returned 0xf0010040, matching the live-view and recording driver dumps. The other seven addresses are driver-derived. Buffer ownership and the live module's binary identity remain open.
## Firmware path into asynchronous XDMAC submission

In the captured current-body liro.ko, the relocation at .init.data+0x2f4 imports dmac_mem_transfer_async. Accounting for the loader prefix gives callback slot 0x318, which the current av-cam.bin wrapper at file offset 0x19b24 invokes. In the independently identified initrd dmac.ko, .text+0x99c accepts a request pointer, checks that the pointer and word +8 are nonzero, and uses unsigned word +0 as a channel in the range 0 through 7.

One traced producer begins at firmware file offset 0x7da0ba. It reads the first word of the object in r0 and passes that value to 0x419f68. This routine constructs the request at the second object's offset +0xc. Request +0 receives the channel and request +4 receives the original first word of the second object. Three offline runs with synthetic channels 3, 5 and 7 reached wrapper 0x19b24 with those exact channel values preserved and the same request layout. Execution stopped before driver submission. This is a channel-selectable interface. The assignment of the first object's channel by a real producer and the identity of its buffers remain open.

## XDMAC hardware contract (offline initrd dmac.ko)

Original-instruction execution of `dmac.ko` (SHA-256 `718284caacf31654151fac234db7293d8338e348687c37b6e3f65dbf24de1522`; `current_body_module_identity_checked=false`) in Unicorn verified the full channel probe, start, result and shutdown sequences ([dma-contracts.json](data/dma-contracts.json)):

- **Register layout:** Unit arbitration `XDACS` is at `unit_base + 0x00` (`boss_hw_dmac_unit_enable` writes `0x10000000` for fixed priority, `0x11000000` for round-robin). Each channel base (`unit_base + 0x10 + 0x30 * (ch % 4)`) exposes nine 32-bit registers: `+0x00 XDTBC`, `+0x04 XDSSA`, `+0x08 XDDSA`, `+0x0c XDSAC`, `+0x10 XDDAC`, `+0x14 XDDCC`, `+0x18 XDDES`, `+0x1c XDDPC`, `+0x20 XDDSD`.
- **Start & coherency fence:** `boss_hw_dmac_start_transfer(ch_base, lli_phys)` translates `lli_phys` (DDR0 or DDR1) to kernel VA, cleans `0x30` bytes via `___dma_single_cpu_to_dev(va, 0x30, dir=2)`, writes the six descriptor words to `XDTBC..XDDCC` (`+0x00..+0x14`), writes `0x11` to `XDDPC` (`+0x1c`), and writes `0x11108003` to `XDDES` (`+0x18`), guarding each MMIO write with `DSB SY` and `outer_cache + 0x1c`.
- **Completion, error & shutdown:** `boss_hw_dmac_get_transfer_result` reads `XDDSD` (`+0x20`), writes `0x0` back to `XDDSD` to clear status, and returns `0` iff `(status & 0xf) == 8`, otherwise `-13` (`-EACCES`). `boss_hw_dmac_shutdown` writes `0x0` to `XDDES` (`+0x18`).
- **Async queue contract:** `dmac_mem_transfer_async` accepts channels `0..7` (rejecting `8` with `-22` / `-EINVAL`), requires a nonzero callback at `req+0x08` and `lli_phys` at `req+0x04`, and queues on the per-channel list at `req+0x10` while the channel is busy; `dmac_async_irq_handler` reads/clears `XDDSD`, invokes `callback(result, req+0x0c)` and kicks the next queued request.

## DMA330 hardware contract (offline camera_2025 dma330.ko)

Original-instruction execution of `dma330.ko` (SHA-256 `a86794fb8ab97fb27adac21bbcb067d424b787f3815d97bf91942b460dffd86d`; `current_body_module_identity_checked=false`) in Unicorn verified the probe table, debug-port commands, interrupt clear and async microcode builder ([dma-contracts.json](data/dma-contracts.json)):

- **Mapped registers:** `dma330_probe` populates 60 32-bit MMIO pointers from `0xf0030000`, matching `dma330_read_proc`: 9 global registers (`DSR +0x000`, `DPC +0x004`, `INTEN +0x020`, `INT_EVENT_RIS +0x024`, `INTMIS +0x028`, `INTCLR +0x02c`, `FSRD +0x030`, `FSRC +0x034`, `FTRD +0x038`), 32 per-channel registers across `ch=0..3` (`FTR +0x040 + 4*ch`, `CSR +0x100 + 8*ch`, `CPC +0x104 + 8*ch`, `SAR +0x400 + 0x20*ch`, `DAR +0x404 + 0x20*ch`, `CCR +0x408 + 0x20*ch`, `LC0 +0x40c + 0x20*ch`, `LC1 +0x410 + 0x20*ch`), 4 debug registers (`DBGSTATUS +0xd00`, `DBGCMD +0xd04`, `DBGINST0 +0xd08`, `DBGINST1 +0xd0c`), 7 config registers (`CR[0..4] +0xe00..+0xe10`, `CRD +0xe14`, `WD +0xe80`) and 8 ID registers (`PERIPH_ID[0..3] +0xfe0..+0xfec`, `PCELL_ID[0..3] +0xff0..+0xffc`).
- **Debug-port commands:** `intclr(ch)` writes `1 << ch` to `INTCLR` (`0xf003002c`, channels `0..4`). `dmakill(ch)` clears `INTCLR`, checks `DBGSTATUS` bit 0 (`0xf0030d00`), and writes `DBGINST0 = 0x00010001 | ((ch & 7) << 8)`, `DBGINST1 = 0`, `DBGCMD = 0` (retrying via `osal_snd_sync_direct` up to 2 waits before returning `-5` if `DBGSTATUS` stays busy). `dmago(ch, prog_pa)` requires `DBGSTATUS` bit 0 clear (else immediate `-5`), RMW-sets `INTEN |= 0x10 | (1 << ch)`, writes `DPC = prog_pa`, writes manager-thread `DBGINST0 = (0xa2 << 16) | (ch << 24) | ((ch & 7) << 8)` and `DBGINST1` from the 32-bit PC at bytes `2..5` of the `DMAGO` buffer, then triggers `DBGCMD = 0`.
- **Microcode templates & coherency:** `dma330_probe` copies four preassembled `.data` template arrays per channel (`0xc440` bytes/channel: `array_type 0..3` with channel strides `0x4510`, `0x3510`, `0x2910`, `0x2110` and up to `256` segments at strides `0x45`, `0x35`, `0x29`, `0x21`, terminated by `DMAWMB`/`DMASEV`/`DMAEND` `13 34 00...`). `dma330_mem_transfer_async` accepts `ch=0..3`, `num=1..256` and `area_info` entries of `(size, src_pa, dst_pa)` (12 bytes each). The driver maps its microcode buffer via `arch_phys_to_noncache` and guards MMIO with `DSB SY` + `outer_cache + 0x1c`, but does **not** flush or invalidate caller data buffers.
