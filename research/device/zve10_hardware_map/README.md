# Hardware atlas tools

These tools build and query the [central ZV-E10 hardware atlas](../../../docs/hardware/README.md). They operate on local files only. No USB, SSH, camera memory access, register writes or uploads are implemented.

## Build

Run from the repository root using the project virtualenv with Capstone installed:

```powershell
.venv/Scripts/python.exe -B research/device/zve10_hardware_map/build.py --kernel PATH_TO_SONY_GPL_TREE --firmware .local/dumps/av-cam.bin --observations research/device/zve10_hardware_map/evidence/20261118-senser-registers.json --page-matches research/device/zve10_hardware_map/evidence/20261118-code-pages.json --out docs/hardware/data
```

The existing local source tree used for the first build was the matching Sony GPL tree under the external zve10-qemu checkout. It is read, never edited. This is Sony platform-source evidence; QEMU is external work and no emulator behavior is treated as hardware proof. Source-relative paths and normalized SHA-256 hashes appear in generated platform.json.

build.py writes platform.json, native-accessors.json and coverage.json (currently 507 numeric symbols, 64 UDIF channel windows, 4 UDIF clock entries, 4 interrupt-only UDIF channels, 9 CRG11 clock-divider domains, 8 static I/O MMU mappings, and 1,245 native RMW candidates). Curated register-contracts.json (122 named registers) is maintained separately and is not overwritten by regeneration. Integer macro expressions are parsed with a restricted AST, not eval or shell execution. Unsupported C expressions and conflicting definitions remain unresolved. C preprocessor conditions are not selected; declarations do not establish body wiring or active configuration. Channel IRQ and clock entries are associated only within the same textual channel initializer.

The native extractor deliberately accepts only short Thumb literal-base/load/BFI/store/return patterns with supported input casts/shifts and matching fixed memory offsets. It scans an explicitly bounded region of the known reference image, without claiming complete executable coverage or function-boundary identification. A candidate can remain an unreferenced pattern in data. It does not infer semantic field names, reset values, required values, side effects or safe access. High addresses outside the main declared I/O aperture remain unclassified rather than automatically MMIO.

The reference whole-image MD5 differs from the current camera image. Five current-camera file pages were captured and matched. The builder checks each recorded matched-page SHA-256 against the corresponding reference bytes before marking an accessor as page-matched. Other accessors retain reference-only scope. No proprietary image bytes are copied into generated metadata.

## Inspect and check

```powershell
.venv/Scripts/python.exe -B research/device/zve10_hardware_map/query.py 0xf3445108
.venv/Scripts/python.exe -B research/device/zve10_hardware_map/query.py DMA330
.venv/Scripts/python.exe -B research/device/zve10_hardware_map/verify.py --data docs/hardware/data --builder research/device/zve10_hardware_map/build.py
```

The verifier checks independent platform/channel arithmetic, field masks, unknown/reset-value separation, address classification, current-camera page flags on the display fields, and rejection of conflicting or unsupported C macros. It does not establish physical device semantics. The original native display instruction tests remain in the [display experiment](../zve10_ram_boot/DISPLAY.md); their passing field updates did not produce a working LCD output on hardware.

Saved observations include date, mode, boot identity, firmware identity and source-response SHA-256. The register capture was read-only; later module installation in the same service session is a distinct operation. The raw terminal/session stays local. A Senser value is never silently promoted to a normal-shooting, reset or required programming value.

## External graphics transaction extraction

The user-supplied [chocotan/zve10-qemu source](https://github.com/chocotan/zve10-qemu) supplied a graphics power-up lead, which was checked independently against the identified local Sony module. No emulator code was copied or changed. Reproduce the data-only extraction:

```powershell
.venv/Scripts/python.exe -B research/device/zve10_hardware_map/extract_graphics_clock.py --module .local/dumps/camera_2025/usr/usr/kmod/grm_gles.ko --out docs/hardware/data/graphics-clock-transaction.json
```

The extractor refuses an unreviewed module hash, checks key original opcodes/literals and IO/delay/error relocation symbols, and records the ordered transaction. It never executes the transaction. The [external audit](../../../docs/hardware/EXTERNAL_ZVE10_QEMU.md) separates modeled effects from source facts and records the unmatched graphics ELF identities.

## Native LCD contracts and saved body capture

The [LCD reconstruction](../../../docs/hardware/DISPLAY_RECONSTRUCTION.md) separates instruction tests from current-body settings and physical behavior. Install pyelftools and Unicorn in the project virtualenv for the contract audit. Do not run Python with -O: the audit uses assertions to reject unexpected identities and results.

```powershell
.venv/Scripts/python.exe -B research/device/zve10_hardware_map/audit_display_native.py --repo . --out docs/hardware/data/display-native-contracts.json
.venv/Scripts/python.exe -B research/device/zve10_hardware_map/bind_display_capture.py --capture PATH_TO_LOCAL_DISPLAY_CAPTURE --reference .local/dumps/av-cam.bin --contracts docs/hardware/data/display-native-contracts.json --out docs/hardware/data/display-current-body.json
```

The audit checks six LiRo callback bindings with the loader's +0x24 prefix, eight original wait-helper cases, eighteen GPIO output cases plus invalid-bank rejection, selected saved Backup properties, the 304-byte source-ID list and six empty graphics exports. MMIO is only recorded in Unicorn; peripheral effects are not modeled. Expected firmware/LiRo/graphics identities are enforced. This is not an LCD initialization test.

The capture validator verifies the saved session status, all four pulled-file hashes, matching reference slices, 328 selected settings and selector-zero profile layout. It compares current-body settings with the separately identified saved Backup. Neither tool connects to a device. Raw capture files, firmware bytes and disassembly stay local; only metadata reports are published.

The LCD profile transport check reconstructs the selected profile, verifies its SHA-256 against the saved body capture and executes the reference firmware's type gates offline.

```powershell
.venv/Scripts/python.exe -B research/device/zve10_hardware_map/audit_lcd_profile_transport.py --repo . --out docs/hardware/data/lcd-profile-transport.json
```

## Offline DMA, I2C, VPH/AIF and GRM contract audits

Reproduce the Unicorn original-instruction audits for `dmac.ko`, `dma330.ko`, `i2c.ko`, `av-cam.bin` VPH/AIF and `grm_gles.ko`/`grm_ma.ko`/`dataflowInfraFramework.so`/`libObj.so` (do not pass `-O` since assertions guard module hashes and MMIO sequences):

```powershell
.venv/Scripts/python.exe -B research/device/zve10_hardware_map/audit_dma_contracts.py --repo . --out docs/hardware/data/dma-contracts.json
.venv/Scripts/python.exe -B research/device/zve10_hardware_map/audit_i2c_contract.py --repo . --out docs/hardware/data/i2c-contract.json
.venv/Scripts/python.exe -B research/device/zve10_hardware_map/audit_vph_aif_contracts.py --repo . --out docs/hardware/data/vph-aif-contracts.json
.venv/Scripts/python.exe -B research/device/zve10_hardware_map/audit_grm_contracts.py --repo . --out docs/hardware/data/grm-contracts.json
```

All auditors enforce exact local binary SHA-256 hashes, record MMIO/cache-sync interactions in Unicorn without camera access, and leave live-body module matching and physical peripheral wiring open.


## Senser display snapshot

Use `capture_display_state.py --plan` to print the selected register words and omissions without opening a USB connection. Run with `--out PATH_TO_NEW_LOCAL_JSON` to capture an authenticated Senser session. The capture discovers the existing full BusyBox at the previously used path or documented alternatives. It saves proc data and file hashes even if reader discovery fails. The exact command list limits the session to static probes, file identity checks and 32-bit reads of the selected words. Repeat samples include elapsed time and IRQ deltas. See the [first capture and its interpretation](../../../docs/hardware/DISPLAY.md#november-19-senser-snapshot).

## Offline DFE and FOPD audit

From the repository root, run the hash-pinned original-instruction check with Unicorn installed and Python assertions enabled.

```powershell
.venv/Scripts/python.exe -B research/device/zve10_hardware_map/audit_dfe_fopd.py --firmware .local/dumps/av-cam.bin --out docs/hardware/data/dfe-fopd-contracts.json
```

The audit records simulated MMIO accesses. The [sensor atlas](../../../docs/hardware/SENSOR_DMA.md#raw-readout-and-fopd-routing) traces the callers and identifies the hardware semantics that still need evidence.
