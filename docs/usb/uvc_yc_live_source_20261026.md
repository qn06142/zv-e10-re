# Live YC continuation —26 October2026

Offline continuation after the other agent's metadata/multi-segment handoff. No camera access, installation, RAM modification or live capture. Permanent2.4p synthetic bars remains the last hardware-verified output. The31-field decoder and multi-segment work are retained. This pass follows the actual640x480 preview path; there is still no completed Sony acquisition backend.

## Executed native640x480 path

Resolved actual references to the preview geometry table0x63e43e9c. Its lookup0x6372e57c initializes from record8 and loops offsets0..0xa0 in steps0x14, ending at0xb4. It is **nine20-byte records**, not18. Each record has four u16 dimension values, two u32 native memory types and a u32 compression selector. Seven executions of original RTOS code with no external stubs verify640x480→row1,1920x1080→row0,1280x720→row5,1440x1080→duplicate rows3/4,720x240→row6,720x288→row7, and unsupported123x456→default row8. These are native table selections, not current camera observations.

Executed original `VdfInputCmdUpdateYuvPin::changeSSYCData`0x6372f54c, including real SSYC lookup and real geometry lookup, on three-entry native containers. Only the message-accessor return and OSAL memory mapping were stubbed; the latter is a fixture identity mapping and does NOT validate RTOS/Linux address translation. All five cases pass:

| Input canvas | Native dataContent | Output canvas/valid/target height | dataPlacement | ycCompress |
|---|---:|---:|---:|---:|
|640x480|2|480|1|0|
|640x480|1|240|0|0|
|640x480|0|240|0|0|
|1920x1080|2|1080|1|1|
|1280x720|2|720|1|1|

The function also sets dataSite0, YcStateInfo.author1 and updates a CameraInfo word by adding its adjacent word. It does not write actual image pixels. This directly establishes that dataPlacement participates in full/half-height organization here; it does NOT justify the old header's numeric mapping1=YUY2/2=NV16. Byte order, planes/stride and bit-depth enum remain unknown. Native helper0x63733abc passes ycCompress0/1 directly to `VPH_ENUM_ONXOFF` in `set_vph_dcd_info`; values beyond1 go to error handling. That is a decompression-control lead, not proof of standard linear YUV packing.

## Actual configured units

Native unit selector0x6372f4a4 calls the geometry lookup with canvas width/height, reads table+8 for dataContent2 and table+12 otherwise. Native640x480 row1 selects type0x6193f or0x61940. These are found in saved DmmConfig.bin:

| Native type | Config unit record | Extent | Config capacity |
|---|---:|---:|---:|
|0x6193f|0x108d8|0x8e|2,073,600B|
|0x61940|0x108c8|0x8d|1,036,800B|
|0x240b2e|0x10ff8|0x14e|614,400B|

A separate resize allocation table0x63e43c98 has24-byte records. Its initial row has640,480,640,480,0,type0x240b2e. UpdateYuvResize at0x6372d880..0x6372d894 selects a record and allocates that type. This ties the exact614400B configured workspace to a genuine resize code path; it still does not prove active output, packing, a current unit handle, current physical address or a read lease. Do not borrow it merely by type/size or reuse historical source addresses.

## Scope corrections for the inherited handoff

- The previous18-entry preview geometry claim is replaced by the executed nine20-byte record lookup above.
-0x63a2e47c identifies itself as `dgi_jpeg_common_check_unit_alignment` in `src/dgi_jpeg_common_make_rsl_musashi.c`. Its128-byte checks are demonstrated for that JPEG unit-validation path, not every YC/USB DMA path.0x63dbcd70 and0x63dbcdb8 are functions selecting paired address/length words; they are not static plane tables. Their existence does not prove Y/C plane layout.
- Finding three direct builder calls establishes the observed direct callsites, not an absolute proof that slots0/3 can never be called indirectly or after runtime patching.
- DMM open/share references and release-handler names do not alone prove pixel write-stability. Preserve separate allocation lifetime, completion fences and producer reuse rules.

## Mapping lead and next step

`liro.ko` exports local named helpers os_virt_to_phys(.text+0xb9c) and os_phys_to_virt(+0xbb8). The former chooses wrapping subtraction0x60000000 or0x20000000 at virtual threshold0xa0000000; the latter adds0x60000000 for physical values below0x80000000 and0x20000000 otherwise. The module separately imports arch_va_to_phys, arch_phys_to_cache and arch_phys_to_noncache. These are distinct layers: do not blindly apply the local helper arithmetic to native YC addresses. The runtime RTOS mapping dispatcher0x63c48e0c reaches an OSAL function table whose registration still needs recovery. A kernel export/string investigation remains exploratory and is not used in any decoder or target patch.

Next: trace the640x480 resize completion into the delivered pixel handle, resolve the actual mapping function/table and byte packing, then attach a bounded source to raw_live_ops while retaining the original completion/reference until the copy completes. Keep old synthetic protocol backend disabled. Generic2.5 still requires source640x480. Target24fps remains later work; this pass changes neither timing nor transport.

Reproducible evidence is under research/firmware/raw_frame_source/verified_yc/evidence/yc-live-20261026; new scripts verify_preview_update.py and verify_preview_geometry.py execute only saved binaries. Full local working files remain C:/Users/qn061/Documents/Codex/2026-10-22/chec/work/yc-live-20261026 and outputs/yc-live-20261026.
