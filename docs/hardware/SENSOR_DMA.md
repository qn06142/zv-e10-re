# Sensor, DFE and DMA hardware contracts

The priority route is sensor → acquisition/DFE → a completed Bayer buffer → an independently owned USB transfer. Each boundary needs a physical register/transaction contract. Linux driver APIs and firmware stage names are leads, not substitutes for that contract. For the recovered IMX284 power/SPI, DFE PLL/SGC0/SyncSeq, ComboPHY/SLVS-EC RX, RdcW0 (`0xfc0a9200`), and a6400 cross-check details, see [Sensor pipeline bring-up and register map](SENSOR_PIPELINE.md).

## Pipeline and feature insertion points

| Stage | Evidence on the ZV-E10 | What we can use it for |
| --- | --- | --- |
| Sensor mode, exposure and readout | The stock trace exposes live-view exposure and readout stages. Saved live-view `SetImgRd` markers arrive at about 24 Hz. Firmware geometry tables are available for still, movie and high-speed presets. | Correlate mode and exposure changes with readout. Sensor identity, power and reset sequencing, serial setup and the physical data link are open. The table geometry alone cannot identify the wire format. |
| Acquisition and RAW routing | `DfeAcqSet` prepares per-block setup. `StrtRdrawRd` reaches the FOPD routing and AIF writer paths; the AIF unit exposes R0 and W0–W4. | Candidate insertion point for black-level correction, Bayer-plane statistics or RAW export. First bind a live writer to a completed frame, including CFA, packing, stride and reuse. |
| ISP and processed preview | In reference firmware, VDF's type-0 YC producer shares pixel memory before sending a separate SSYC metadata reference. Native consumer methods recover pixel handles and geometry through that metadata. A live subscription and the exact pixel layout on this body are open. | Try luma statistics here once a live preview buffer can be leased and read. Histograms and zebras can start here without programming sensor modes. |
| Preview composition | Stock live-view captures place the preview and overlays at the VPH display end. Separate bare-metal tests established OSD0 scanout with our own 640×480 RGBA4444 buffers. | Draw the result in an owned overlay surface. A hook into Sony's running preview needs its own composition and ownership contract. The takeover demo establishes overlay output only. |

[Runtime claim review](../../research/firmware/evidence/zve10-20261117/CLAIM_REVIEW.md) · [Firmware geometry tables](../imaging/avcam/sensor_modes.json) · [Native YC frame contract](../../research/firmware/raw_frame_source/verified_yc/evidence/frame-contract-20261029/REPORT.md) · [Display routing and capture](DISPLAY.md)

The first image-feature milestone is a histogram from a read-only copy of one completed stock preview frame. At the existing producer/consumer boundary, record the frame sequence, pixel and SDS handles, dimensions, crop, stride, packing, completion state and release point for the **same** frame. Resolve the handles through the owning service. Check byte order and row pitch with a controlled scene before using the luma samples, then compute the histogram in our own memory. Repeat in normal live view and 4K24 recording before treating it as a continuous input. Keep the RAW path separate until a FOPD write bank can be correlated with a completed Bayer buffer and its next reuse.

### Display-side YC handle resolution and scanout

The normal VDF display path builds a `VPH_CMD_UPDATE_YUV` before handing the video buffer address to VPH. In `0x63733de0`, the branch at `0x63733e3e` takes the pixel type word from Category 0 `+0x04` and the handle halfword at `+0x08`. It invokes DMM Open through `0x6371f540` (operation 5 to `0x0061003c`) and then Close through `0x6371f4a0` (operation 6). When both succeed, the word returned at DMM control record `+0x0c` goes into the VPH command at `+0x00`. An Open error exits that branch before Close or the address write. A separate matching branch can supply its cached address at `0x63733f58`. The temporary Open/Close pair establishes the address-resolution contract. It does not establish the display consumer's separate hold or the producer's reuse deadline.

`0x63735c88` calls the normal video update object's first virtual method. The object at `0x642442e4` is constructed with vtable `0x645817f0`, whose first method forwards to `0x6371e6a4`. That wrapper checks for a nonzero command address at `+0x00` and nonzero words at `+0x04` and `+0x0c` before submission. The latter words each contain pairs of geometry halfwords. `0x63a5c2e4` stages the whole 144-byte command at `0x64418d74` and sets the pending byte at `0x64418d70`. This documents the normal display-side consumer. Matching one live output pin's SSYC handle to one queued display command remains open.

The pending command travels in a `0xe4`-byte envelope on RTOS queue `0x006605a9`. The send call is at `0x63a5d29c`, and the receive task at `0x63a5eda0` hands the envelope to `0x63a5ec40`. With the envelope's pending byte at `+0x04` set to 1, the 32-bit command selector at `+0x4c` sends the same 144-byte record to YUV0 for 0, YUV1 for 1, and both for 2. The YUV0 ready flag and command are at destination `+0x180/+0x184`. YUV1 uses `+0xec/+0xf0`. The route handlers pass route 0 and route 1 respectively to `0x63dcbb42`.

Both route drivers use `0x635d3c90` to build video geometry. The primary source descriptor takes the command's base word from `+0x00` and passes it at descriptor `+0x04` to `0x63dcb590`. In that helper, `linear = u16(+0x0c) + u16(+0x08) * u16(+0x0e)`. The adjusted address at result `+0x10` is `base + (linear & ~63) * scale`. The scale is 1 for descriptor type word 1 and 2 otherwise. The helper returns the leading sample and byte counts at result `+0x00` and `+0x04`.

The route's plane configuration helpers `0x63dcb4ea` and `0x63dcb48e` select the primary and secondary banks in the table below. Both use `0x63dcb3c8` to submit the plane result's `+0x10` as configuration word `+0x08`. The AIF config writer at `0x639e2044` stores that word to bank `+0x20` when the channel passes validation and its enable bit is clear. The four register addresses are `0xf34412a0`, `0xf34415a0` for YUV0 and `0xf3441220`, `0xf3441520` for YUV1. The firmware's `+0x10` readback and this programmed base are separate registers. The adjacent words describe the DMA rows. Bank `+0x24` holds the aligned fetch byte count, `+0x28` holds the line gap in bytes, and `+0x2c` holds the programmed row count minus one. The primary geometry builder copies command `+0x04` to descriptor `+0x08` for row stride and command `+0x0a` to descriptor `+0x0e` for row offset. In the single-step case (descriptor word `+0x18` and byte `+0x14` both 1), the row step in bytes is the sum of the fetch byte count and line gap. The size includes alignment padding.

Two split-region builders, at `0x635d3ee0` and `0x635d40c0`, copy the primary source descriptor into the secondary source descriptor and keep its original base and row stride. They give the second DMA bank a different horizontal start within the same image data. For the special route-0 branch with selector `0x1b` or `0x1c`, the second column is `command_x + (command_width >> 1) - 10`, and the second width is `(command_width >> 1) + 10`. The other traced split uses column `command_x + (command_width >> 1) - 14`. Both rerun `0x63dcb590` on the copied descriptor. In these paths, the secondary hardware bank represents a second horizontal fetch region of one source. Pixel packing remains unverified.

In the VPH video start tails, a zero route-gate result permits the normal video AIF to arm. The mode byte here is the local byte at stack `+0x204` in each tail. Its enum and the eventual display format still need independent confirmation.

| Video route tail | Plane 0 | Plane 1 |
| --- | --- | --- |
| `0x63a7f292` / YUV0 | Always arms AIF `0x3a` at `0xf3441280` after the gate. | Arms AIF `0x3f` at `0xf3441580` for local mode byte 1 or 2. |
| `0x63a7fae0` / YUV1 | Always arms AIF `0x39` at `0xf3441200` after the gate. | Arms AIF `0x3e` at `0xf3441500` for local mode byte 1. |

The offline audit verified the DMM lookup and failure path, staged command copy, eight pending/route combinations, four alignment and row-geometry cases, four secondary-region cases, 32 AIF address and fetch-width cases, 16 line-gap and row-count cases, and eight arm cases. These tests execute the native helpers with synthetic records and MMIO. In Senser, eight checked pages matched the reference. The full `av-cam.bin` hashes differ. The secondary-region builders were tested offline, with the second builder's page outside the checked ranges. Senser previously showed YUV1 plane 0's `+0x10` fixed at `0x3c3f4580`. The live-view experiment still needs to correlate a changing address with the matching frame handle, layout and ownership fence before reading pixels. [VDF and AIF firmware comparison](../../research/device/zve10_hardware_map/evidence/20261120-senser-preview-scanout-identity.json) · [Route and address firmware comparison](../../research/device/zve10_hardware_map/evidence/20261120-senser-preview-address-identity.json) · [Offline verifier](../../research/device/zve10_hardware_map/audit_preview_scanout.py)

```text
python research/device/zve10_hardware_map/audit_preview_scanout.py .local/dumps/av-cam.bin
```

### Acquisition setup dispatch

In the reference `av-cam.bin`, `0x63d73576` calls `0x6379cb68` with the 52-byte request built by `0x63d73502`. On the traced setup branch, `0x6379cdda` calls a builder that fills fields through byte `+0x24` of a separate descriptor, then `0x6379cde8` hands that descriptor to `0x6379a57c`.

`0x6379a57c` obtains the table at firmware VA `0x645bab60` through GOT slot `0x646388e0`. The table holds 28 one-bit selector/object pairs and a trailing zero row. The loop tests each selector against the setup object's word at `+0x28`. A match invokes the selected object's vtable entry `+0x10`, passing the same descriptor pointer as its second argument. For example, masks `0x00020000`, `0x00040000` and `0x00080000` select objects at `0x6426affc`, `0x6426b068` and `0x6426b008`, respectively. Those are object addresses in firmware RAM. Their vtable words are zero in the saved image, so the next offline step is resolving their runtime initializers and register-writing methods.

Original Thumb instructions passed 31 dispatch cases using stub method targets, including every single selector, a pair and all selectors together. The test establishes selection, order and descriptor forwarding in the reference image. It stops before the next setup stage and does no MMIO. The saved Senser comparison includes the top-level `DfeAcqSet` page, with the dispatch leaf and table still outside that comparison. [Dispatch verifier](../../research/device/zve10_hardware_map/audit_dfe_acquisition_dispatch.py) · [Installed firmware page comparison](../../research/device/zve10_hardware_map/evidence/20261120-senser-fopd-identity.json)

## Sensor readout from trigger to buffer

The later factory still capture returned a 6048 × 4024 Bayer frame. The ZVOS sensor readout remains under investigation. The latest handoff records the native IRQ sequence, DMM ownership, and hardware timeout. [Bayer readout handoff](../../research/device/zve10_ram_boot/BAYER_HANDOFF.md)

The trace below uses reference `av-cam.bin` SHA-256 `bc6cba98c1ce5ef9c7692b9701ed855c25958d285a646ef90dc3fdf398f5c4fa`, loaded at `0x635c6000`. Function and object locations are firmware virtual addresses. Hardware register addresses are identified explicitly.

| Step | Traced path | What it establishes |
| --- | --- | --- |
| Prepare and request readout | At `0x638f5eb0`, the camera stage passes the context's `+0x590` record and two argument records to `0x638d146c`. That path can update the DFE timing parameters through `0x63d735f8 → 0x6379ce58`. Its later call `0x638d1596 → 0x63d1068a → 0x63778410` adapts the request for CamCore. The wrapper chooses fields at input `+0x38/+0x3c/+0x40..+0x42` or `+0x98/+0x9c/+0xa0..+0xa2` depending on the state byte at `+0x48`. | These are inputs to the sensor/readout request. The `ReadKickLv` or `ReadKick` text is logged **after** the call at `0x638f5eb0`. It reports stage progress. The physical sensor bus transaction and its timing remain open. |
| DFE start | A separate stage branch at `0x638f5f5e` takes the operation token from context `+0x6cec`. The call chain is `0x638cf404 → 0x63d73588 → 0x63d23120 → 0x6379ab48`. If the first call returns zero, the branch follows with a timing update at `0x638f5f7a`. | The operation token selects an initialized DFE resource. The stock resource and live plane for a given shooting mode still need to be bound on the body. |
| Candidate DDR writer | With explicit geometry and logical interface 5 enabled in the offline harness, `0x6379e2b8` configures RdcW0 via its AIF. The writer's MMIO holds destination at `0xfc0a9220`, line bytes at `0xfc0a9224`, line gap at `0xfc0a9228` and line count minus one at `0xfc0a922c`. The native start sets bit 0 at `0xfc0a9200`. | This is the DFECore writer path. The separately audited FOPD bank at `0xf3020280` also has a W0 label. No equivalence between those apertures is established. Default movie resource selection in the earlier audit did not enable this DFECore writer, and forcing its enable flag left the RAW geometry absent. |
| Completion and copy | The native DFE IRQ path `0x6379ef08` checks the registered processing mask. The mask excludes logical RAW AIF 5/6. In prior tests, the processing callback fired while the modeled W0 busy bit at MMIO `0xfc0a9204[31]` remained set. Native stop also returns after a bounded busy wait. | Neither callback delivery nor stop return establishes that this Bayer destination is ready. The first actual frame needs a completion correlation specific to the writer, a stable byte span and a proven release point. |
| Native software consumer | In `ReadEndBase`, the calls at `0x638f410a` and `0x638f413e` pass a 16-bit value selected from capture context `+0x67b6` or `+0x67b0` to native dump helper `0x6390897c`. Selection depends on stage flags, capture state and the `0xffff` sentinel. | These values are memory handles passed to the native dumper, rather than physical addresses. This is a concrete consumer boundary to trace back to an owned buffer. It is a gated path and does not establish continuous preview Bayer frames. |

The nearby power-state callback can also fire without a frame event. The original `0x638cf0a0` tests the DFE power-state word via GOT slot `0x6463e4f4`. With positive state, it invokes a supplied callback synchronously and returns zero. With nonpositive state, it takes the request branch through `0x6379c440`. The verifier executed six positive-state cases with and without a callback. The only stub was the supplied callback, and no MMIO was mapped.

### From capture allocation to the acquisition request

On successful allocation, `0x638d9ff4` stores the RAW handle at context `+0x67b6` and an address/capacity pair at `+0x6b5c/+0x6b60`. The branch at `0x63d871f2` forwards a pointer to that pair and the handle. Its alternate path at `0x63d87204` selects `+0x6b3c/+0x6b40` and `+0x67b0`. These are paired fields from one branch. Mixing a handle from one branch with the other address would lose their provenance.

The call at `0x63d87230` passes the request to `0x638f4fa8`. On that routine's flag-`0x10` branch, the two words are dereferenced at `0x638f5526` and `0x638f5534` and land at offsets `+0x34/+0x38` of the stack descriptor. The call at `0x638f576c` passes the descriptor to `0x639079a0` as its fifth argument. Four original-instruction fixtures checked both source branches and two address/capacity/handle tuples. The test starts at each selected branch, stubs the unrelated selector and stops at the downstream call. The descriptor's destination hardware bank and timing remain unverified on the body.

Inside `0x639079a0`, the descriptor pointer is loaded into `r8`. The Thumb dispatch table at `0x63907d64` forwards it through different adapters according to the one-based selector:

| Selector values | Adapter | Descriptor argument at adapter entry |
| --- | --- | --- |
| 1, 14, 16, 17, 19, 20 | `0x63771c30` | `r3` |
| 2, 15 | `0x63771bcc` | stack `+4` |
| 3, 18, 21 | `0x63771b7c` | stack `+0` |
| 11 | `0x63771b10` | stack `+8` |

These are static branch results from the table and call sites. The first three adapters reach `0x63d07822`, `0x63d0784a` or `0x63d0787a` respectively after object checks. Each then calls the selected object's vtable slot `+0x5c`. All three adapters request an RTTI cast from `Camera::CamCore::CoreController` to `Camera::CamCore::CapController`. The reference CapController vtable at `0x64586d30` resolves `+0x5c` to Thumb method `0x63d07596`. Derived `SplitCapController` (vtable `0x64587030`) and `StripCapController` (vtable `0x64587160`) override `+0x5c` with `0x63773d58` and `0x63774cf8`. All three wrappers passed the descriptor at stack argument `+0` for each of the three fixture vtables. All three classes share the `+0x44` method. The body's active class and selector remain unbound.

On the admitted branch, CapController forwards that pointer through `0x63d08dc6 → 0x63d08bf4`. If the pointer is present, the call at `0x63d08ce6` passes it in `r1` to vtable `+0x44`, which resolves to `0x637721ec` on the reference CapController. This method reaches the Camera AIF adapter `0x63775bd4` on its setup path, using the AIF object from controller `+0x2c`. The two native ISP bindings for that instance are traced below. The active index on the body remains to be measured.

The descriptor remains polymorphic at this boundary. Its initializer at `0x63775488` installs an `RdcImage` vtable. In one branch of `0x637721ec`, the code reads descriptor `+0x34` into a value compared against 1 and 2 for encoding selection. Original instructions verified that read with four inputs, including an address-shaped word. The earlier allocation forwarding check establishes the word's origin on its branch. It does not establish that this encoding branch programs that value as a DMA destination. Trace the AIF instance and the values reaching its address writer before assigning a physical destination to this call chain.

### Camera AIF memory-span programming

The memory-backed path uses a span record distinct from the polymorphic `RdcImage` descriptor. In the one-span case, builder `0x63775acc` takes the base/capacity from span record `+0x08/+0x0c`. For the tested no-extra-gap case, it adds the caller's byte offset to the base and derives the line gap as stride minus active line bytes. It returns a configuration consumed by `0x63775bd4`.

The adapter reads its logical channel at object `+0x20`. The native setup and geometry wrappers both use that channel to index the 12-byte table at `0x63e89724`; its second word is the port MMIO base. IDs 17 through 22 select FOPD R0 and W0–W4, respectively. This is the same table used by the FOPD-specific audit. The general adapter's routing remains distinct from DFECore RdcW0 at `0xfc0a9200`.

| Port offset | Value from the tested one-span configuration |
| --- | --- |
| `+0x20` | Destination for a write bank, calculated as span base plus byte offset |
| `+0x24` | Active line bytes |
| `+0x28` | Byte gap between active lines |
| `+0x2c` | Line count minus one |

Six original-instruction tests ran the builder and adapter through both alignment-checked wrappers with RAM-backed MMIO and no software hooks. The same input produced `[0x22704040, 3840, 256, 479]` in each selected port. The port control's start bit remained clear. R0 was included as a read-side control case. The logical channel, span and status bit 31 were fixtures. These trials establish how the adapter programs the bank supplied by its caller. They leave the live controller's channel, span origin, start and completion order open.

### Capture-controller ISP writer binding

The normal CapController setup at firmware VA `0x63d0771c` assigns backing object `base + 0x754 + index × 0x860` to controller `+0x50`. The acquisition branch at `0x63d08466` promotes it into the active slot `+0x2c`, calls its vtable `+0x08` entry, and merges its mask into controller `+0x7c`. The constructors at `0x63777f62` and `0x637780bc` give those two objects logical IDs 3 and 9. Subconstructor `0x63d0a8e0` stores the ID at object `+0x20` and mask `0x8000` at `+0x1c`.

| ISP index | AIF object offset | Logical ID | Global MMIO | Port MMIO |
| --- | --- | --- | --- | --- |
| 0 | `+0x754` | 3 | `0xf3002000` | `0xf3002380` |
| 1 | `+0xfb4` | 9 | `0xf3102000` | `0xf3102380` |

The activation tests executed both original constructors and the pointer handoff, with the object's vtable callback stubbed. Separate original-instruction tests fed each initialized object to the memory-span builder and programming adapter. Both paths wrote the modeled destination at port `+0x20` and geometry at `+0x24/+0x28/+0x2c`. These candidate ISP banks differ from the FOPD and DFECore banks considered earlier. This binds an actual firmware object layout to the ISP table, without measuring whether that path is active or carries Bayer, YC, or another format in stock live view.

To bind the live path, compare `+0x00` (control), `+0x04` (status), and `+0x10` (the address-like word read by `0x639e231c`) on both ports. These offsets already have native read accessors. Compare successive samples with the display-side YUV AIF and the camera's capture cadence. Address movement can identify candidates for follow-up, but does not by itself establish frame format or a completion boundary.

### Live USB Senser observation

Four read-only passes covered 30 words each on the attached ZV-E10. ISP channels 3 and 9, FOPD W0 and W1, and DFECore W0 all returned zero for control, status and the address-like word. Both YUV0 planes and YUV1 plane 1 also stayed zero. YUV1 plane 0 held control `2`, status `0` and the same address-like word `0x3c3f4580` across all four passes. OSD0's address readback changed on every pass. Display IRQ 102 advanced by 140 across a 2.84-second uptime window, while IRQ 110 and XDMAC5 IRQ 194 stayed fixed. [Senser register samples](../../research/device/zve10_hardware_map/evidence/20261120-senser-isp-readout.json)

This Senser session had a functioning LCD scanout and no observed frame advance in the sampled sensor/video banks. It cannot bind the stock live-view writer or provide a completed frame for the standalone runtime. The register observations apply to the USB service state. Sensor activation or a Senser-compatible shooting path still needs to be found.

For the exclusive runtime, the first readout can use one owned destination and one armed transfer. It can omit Sony's consumer leases, a ring and inter-consumer arbitration. It still needs a writer-specific completion check, including DMA errors and CPU visibility, before copying pixels. Identify the active Camera AIF instance and bind its programmed destination to a writer-specific completion condition. Stock DFE callbacks and timeout exits alone do not provide that check.

[Native movie and DFE audit](../../research/firmware/zve10-session-2026-11/movie-bayer-audit/REPORT.md) · [Writer lifecycle and completion tests](../../research/firmware/zve10-session-2026-11/movie-bayer-audit/RAW-GEOMETRY-FINDINGS.md) · [Acquisition and callback verifier](../../research/device/zve10_hardware_map/audit_dfe_acquisition_dispatch.py) · [Runtime sensor trace markers](../../research/firmware/evidence/zve10-20261117/codex/sensor-markers.tsv)

### Sony factory preview setup and Senser service state

A follow-up USB Senser inventory found `im.elf` (PID 152, 195 threads) with `dataflowInfraFramework.so` mapped and open descriptors for `/dev/uipc`, `/dev/stream`, `/dev/stream2` and `viewUsbMassStorage.uxc`. OSAL 4.2 reported 857 global message queues and 196 semaphores. The filtered dump did not identify queue owners or RTOS endpoints. This runtime switch from Mass Storage kept the imaging process alive, so the older forced-service observation of an absent imaging process does not explain this camera's inactive sensor writer samples. [Read-only service inventory](../../research/device/zve10_hardware_map/evidence/20261120-senser-preview-services.json)

Sony's `CAMERA_SCN_EE_SETUP_START_STOP.so` in the 2025 reference dump (SHA-256 `c3026b082b44d2b795735b2de6d27a3655e2d1755e9acbfce71e7b8a73c22fb0`) exposes an explicit factory preview setup path. In `scenario_run`, the calls at ELF VAs `0x1d44..0x1dcc` execute in this order, checking the result of each step before continuing.

| Call-site VAs | Operation |
| --- | --- |
| `0x1d44`, `0x1d50` | `PinConnect(0)`, then `PinConnect(1)`. The table at `0x2054` supplies pairs `(0, 0)` and `(3, 1)`. |
| `0x1d64`, `0x1d74`, `0x1d88` | `SetStill`, `SetMovie`, then `SetPathVDF`. The VDF path argument is 8 when configuration byte `+8` is 4, otherwise 1. |
| `0x1d94`, `0x1da0`, `0x1daa`, `0x1db4` | Panel mute/output, brightness and color configuration. |
| `0x1dc0`, `0x1dcc` | `SetMode`, then `cam_scn_scn_mode`, using the same configuration halfword at `+0`. |

The pin-connect helper sends a 40-byte dataflow request to `0x00050004` and expects the matching source and reply type `0x8001` before proceeding. The pin-disconnect helper expects `0x8002` from the same endpoint. `SetMode` at `0x177c` sends to OSAL destination `0x00030001`. It writes request selector 0 at payload `+0` and the mode halfword at `+2`. It then waits for a reply and checks selector 1 plus the same mode halfword. These are firmware message-level contracts. The scenario was disassembled offline and was not dispatched on the camera. Its endpoint availability in this Senser state and the mapping from `SetMode` to sensor enable and the active AIF writer remain open. In particular, the mapped framework and display cadence do not establish a frame producer.

## Sensor control and acquisition

| Item | Established evidence | Still missing |
| --- | --- | --- |
| Sensor model and electrical control link | The installed firmware implements `C_ImagerCtrl_IMX284` over P2S SPI (`0xfc088300`/`e00`/`f00`), PMIC SPI (`clk_id 0x4e`), and Imager GPIO (`0xfc029000..2c`). Stepped rail power-on (`0x637ad800`), wake (`0x637ad310`), and power-off (`0x637ab9fc`) sequences and packet builders are recovered and hardware-verified for 6/7 bursts in [Sensor pipeline](SENSOR_PIPELINE.md). | Physical sensor ID/revision readback and non-Mode-1 PMIC/gain datasheet semantics. |
| Mode programming | Mode pointer arrays (`0x645bc738`/`0x645bc804`), `wake_regs_0..2`, Mode-1/`0x37` P2S bursts, `0x0832` stream-latch rule (`0x637abea4`), and `SetImgRd` exposure descriptor construction (`0x63c047c8 -> 0x63bbe150 -> 0x637aca24`) recovered. | Runtime AE/gain inputs feeding `SetImgRd` for live still/movie shots and Open-Gate tuning. |
| Sensor-to-SoC data link | ComboPHY (`0xf292a000`), AFE (`0xf2931100`), D-PHY/SLVS PHY (`0xfc02a060..80`, `0xfc02d000`), MPHY (`0xfc02a040..5c`), 8-lane dual-port `SLVS-EC` RX (`0xfc0f0000/0100`), `DrvSGC0` (`0xfc0a11xx`), `SyncSeq` (`0xfc0800xx`), and `CamCore SGC1` (`0xf3120000`) recovered in [Sensor pipeline](SENSOR_PIPELINE.md). | Bare-metal `SGC0` start qualification / local clock gate (`0xfc0a1110[16]=0`, frozen `HVcnt`) and pre-start `SyncTask` (`0x635ce230`) actions. |
| DFE setup | The reference image enters DfeAcqSet at 0x6390b93c and StrtRdrawRd at 0x6390a014. Selected FOPD MMIO writes and routing fields are verified below. | These are firmware virtual addresses, not hardware registers. Trace their actual base-address providers, descriptor words, start and completion conditions. |
| DFE callbacks | Native slots 3, 9, 10, 11 and 14 are registration leads; slot 10 signals event 0x16. | Callback slot → hardware fact → IRQ/status/ack mapping, and exact frame-buffer ownership. |
| Runtime cadence | SetImgRd about 41.6–41.8 ms and other preview markers about 20.8 ms in saved sessions. | Marker-to-frame association, exposure/readout timing, Bayer packing and usable completion-to-reuse interval. |

Source scope: [later RAW pipeline audit](../../research/firmware/raw_frame_source/verified_bayer/evidence/raw-pipeline-audit-20261031/REPORT.md), [reviewed runtime claims](../../research/firmware/evidence/zve10-20261117/CLAIM_REVIEW.md). Those offline firmware addresses are bound to their recorded image, not automatically the current body. The native accessor corpus is mostly display-related and does not fill this sensor register gap.

### IMX284 imager dispatch and readout register sequence

The installed ZV-E10 firmware matches 15 selected pages of the reference `av-cam.bin`, including the imager initializer, control code, RTTI, vtable and register accessors. The initialized object at GOT slot `0x6463e068` is bound to the singleton returned by `0x637aac18`. Its initializer `0x637abbe4` installs vtable address point `0x64588e88`, whose typeinfo names `Camera::Imager::IMX284::C_ImagerCtrl_IMX284`. This identifies the native driver implemented by the installed code. A physical sensor ID read and package revision are still open. [Installed file page hashes](../../research/device/zve10_hardware_map/evidence/20261120-senser-imager-identity.json)

The capture-side `ImagerSetMode` wrapper at `0x6390b8fc` reaches `0x637aadd8`, then uses imager vtable slot `+0x28` to dispatch to `0x637acd98`. That method stores the requested mode from descriptor `+0` to object `+0x11c`, then takes a mode-table branch. Readout helper `0x63d2a758` selects slot `+0x44` (`0x637ad06c`) for nonzero input and slot `+0x48` (`0x637ab588`) for zero. Multiple capture-side callers issue the nonzero readout request after the mode wrapper. The factory scenario's OSAL mode halfword and this driver's internal mode word are separate fields. Their translation remains open.

When internal mode `+0x11c` and prior mode `+0x120` both equal `0x11`, the nonzero readout method invokes `0x63d2b6ee`. This helper makes 13 ordered 32-bit stores:

| Register | Operation in call order |
| --- | --- |
| `0xfc02a01c` | Set bits 0–11, preserving the other bits. |
| `0xfc0f0050`, `0xfc0f0150` | Write zero to both registers in order. |
| `0xfc0f0000` | Four successive read-modify-writes clear bits 0–7, 8–15, 16–19, and 24–25. |
| `0xfc0f0004` | Write zero. |
| `0xfc02a04c`, `0xfc02a048`, `0xfc02a05c`, `0xfc02a058` | Clear the low nibble, bit 0, low nibble, and bit 0 respectively, in order. |
| `0xfc02a040` | Set bit 0, preserving the other bits. |

The offline audit executed the native mode and readout dispatch with a synthetic object and checked the 13 writes against three initial register patterns. The Senser session only read firmware files. This branch provides a concrete SoC-side register sequence to correlate with stock shooting state. The electrical sensor transport, the active live-view mode, and the resulting DMA writer remain to be verified. [Offline verifier](../../research/device/zve10_hardware_map/audit_imager_control.py)

```text
python research/device/zve10_hardware_map/audit_imager_control.py .local/dumps/av-cam.bin
```

### Stock `SetImgRd` request and nearby interrupts

The saved stock trace's `SetImgRd` marker comes from `0x6392fb2e`. The function pushes that marker before building a per-frame request and calling `0x638d0584`. That helper raises the scan state to at least 5 and calls `0x637aae88`, which forwards the descriptor with arguments `(1, 1)` through imager slot `+0x3c` to `0x637aca24`. This is separate from the mode reservation and mode-transition vtable slots above. Nine pages covering the marker, descriptor builder and dispatch matched the installed firmware. [Request code page comparison](../../research/device/zve10_hardware_map/evidence/20261120-senser-imager-request-identity.json)

The descriptor starts with six halfwords copied from the selected context's `[+0x2c]` table at `+0x14`. The first is replaced with the result of `0x63d31d5e`. When configuration byte `+0x1d` has bit 1 set, descriptor halfwords `+0x02` and `+0x04` become `0x0f00` and 0. The context's `[+0x38]` table supplies descriptor halfword `+0x0c` from table `+0x20` and descriptor words `+0x10/+0x14/+0x18/+0x1c` from table `+0x10/+0x14/+0x1c/+0x18`. The IMX284 method returns 2 early when the internal mode word is `0x11`. The marker therefore shows the request path was entered, without establishing that the sensor accepted the request or that a DMA buffer completed.

Across six complete pairs from two saved live-view captures, the first IRQ 74 after each marker arrived 26.206–26.573 ms later, and IRQ 75 followed 26.891–27.260 ms after the marker. Two complete 4K24 pairs gave 26.638–27.033 ms and 27.328–27.724 ms respectively. The captures contain no per-frame IDs shared by these three markers. [Live view, first capture](../../research/firmware/evidence/zve10-20261117/additional-captures/live_view_full_1.txt) · [Live view, second capture](../../research/firmware/evidence/zve10-20261117/additional-captures/live_view_traces_1.txt) · [4K24 capture](../../research/firmware/evidence/zve10-20261117/additional-captures/rec_4k24_full_1.txt)

| IRQ | Installed table entry and handler | Status and callback contract |
| --- | --- | --- |
| 74 (`0x4a`) | Row `0x64592720`, handler `0x637968b0` | Read low nibble at `0xf3040004` and write it back. Bit 1 calls the configured callback with code 2 or 4, selected by a firmware flag. Bit 2 calls it with code 4. Both callbacks can occur for one status word. |
| 75 (`0x4b`) | Row `0x64592730`, handler `0x6376db78` | Read and write back the full status word at `0xf3850610`. The two configured callbacks receive a boolean indicating whether bits 24–27 are nonzero. Sony's handler labels this block `YC: [APL0 DMA]`. |

The six handler, table and diagnostic pages matched over Senser. Offline execution verified both descriptor variants and seven modeled IRQ cases. IRQ 75 is a concrete processed-path DMA observation point. The sampled status and timestamps do not establish a Bayer producer, frame address, or safe reuse window. The movie and face-sequence callers below identify concrete users for these interrupt paths. [IRQ code page comparison](../../research/device/zve10_hardware_map/evidence/20261120-senser-imager-irq-identity.json) · [Offline verifier](../../research/device/zve10_hardware_map/audit_imager_control.py)

### APL movie DMA buffers and the PRC face path

The movie sequence calls an APL address preparer at `0x6376f430`, then starts the job at `0x6376e8ac`. Sony's diagnostics name these operations `apl_mov_set_dma_addr` and `apl_mov_start`. In the kick path, `0x6376e8de` writes the supplied callback into the selected core's slot through `0x6376db04`. The movie caller at `0x63959b76` explicitly supplies zero, as do the two nearby callers at `0x639597ec` and `0x63959e3e`. For those launches the kick clears that callback slot. The separate callback slot used by IRQ 75 remains outside this finding.

The kick at `0x6376ea62..0x6376eb2e` programs 23 words for a selected core. The descriptor table starts at firmware RAM `0x6425bfd4` with a `0x38`-byte stride. In the table below the APL0 register addresses are absolute. APL1 uses the same offsets at `0xf3950000`.

| Firmware diagnostic name | Descriptor offset | APL0 register |
| --- | --- | --- |
| `TAR__IN__ADDR` | `+0x00` | `0xf3850400` |
| `SML_REF0_ADDR` / `SML_REF1_ADDR` | `+0x0c` / `+0x10` | `0xf3850418` / `0xf385041c` |
| `ME___OUT_ADDR` | `+0x14` | `0xf3850420` |
| `SML_POST_ADDR` | `+0x1c` | `0xf3850428` |
| `COPY_SRC_ADDR` | `+0x20` | `0xf385042c` |
| `MV___OUT_ADDR` | `+0x24` | `0xf3850434` |
| `REF0_OUT_ADDR` / `REF1_OUT_ADDR` | `+0x28` / `+0x2c` | `0xf3850450` / `0xf3850454` |
| `MBL__OUT_ADDR` | `+0x30` | `0xf38504a4` |
| `LGR_DL___ADDR` | `+0x34` | `0xf38504d0` |

The target input, reference buffers, and motion-vector output identify this as a movie processing job. IRQ 75 is an observation point for APL activity. The LCD preview surface should be traced through the VDF producer's published frame handle and VPH video input.

IRQ 74's `0xf3040004` status belongs to the PRC path. One concrete client is Sony's face sequence at `0x63933832`, which passes callback `0x63932ed1` to the PRC request at `0x637967e8`. The request stores that callback in the slot read by the IRQ 74 handler. The callback stores its incoming event code and posts a firmware message. Other callers also use the PRC request, so identifying which client owned a particular saved IRQ still needs runtime evidence.

Eleven selected pages matched the installed firmware. Offline execution checked all 23 stores for both APL cores and the movie caller's null callback argument. This maps the programmed words and their source fields. Live values, buffer lifetime, and preview routing remain open. [Firmware page comparison](../../research/device/zve10_hardware_map/evidence/20261120-senser-apl-identity.json) · [Offline verifier](../../research/device/zve10_hardware_map/audit_apl_addresses.py)

```text
python research/device/zve10_hardware_map/audit_apl_addresses.py .local/dumps/av-cam.bin
```

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
