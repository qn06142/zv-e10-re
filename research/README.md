# Consolidated research tree

Everything that used to sit loose in the repository root now lives under a
directory named for what it actually does. Nothing was deleted; the original
filenames are preserved, so a note that refers to a script by bare name still
resolves via the index below.

Current firmware analysis lives elsewhere and is not duplicated here:

| Path | What it is |
|---|---|
| `avcam_re/` | Findings on `av-cam.bin` (see `HARDWARE_OVERVIEW.md`) |
| `retool/` | The rizin-based analysis package |
| `re_symbols/` | Recovered symbols with per-symbol provenance |
| `dumps/` | Firmware images and carved payloads (git-ignored) |
| `results/` | JSON result data from the probes |
| `logs/` | Captured probe output |

## Layout

| Directory | Files | Purpose |
|---|---:|---|
| `research/common/` | 2 | Helpers shared across topics. `senser_fix` and `zve10_dumpall` are imported from `device/`, `diag/` and `isp/` alike, so they cannot live in any one of those. Each importer puts this directory *and* the repository root (for the `pmca` package) on `sys.path`. |
| `research/device/` | 46 | Talking to the camera over USB: PTP/MTP, mass storage, enumeration, card and firmware pulling. The only group that needs a physical ZV-E10 attached. |
| `research/firmware/` | 27 | Firmware image structure: format analysis, carving, decompression, decryption, payload extraction. |
| `research/disasm/` | 19 | Per-subsystem disassembly. Superseded for `av-cam.bin` by the `retool` package, kept for the other images. |
| `research/scan/` | 7 | Byte/string sweeps over firmware images looking for structure. |
| `research/diag/` | 7 | Diagnostics: offset, padding and size checks on carved regions. |
| `research/crypt/` | 7 | Brute-force and cryptanalysis of the update/crypter paths. |
| `research/lens/` | 5 | Lens protocol: query, trigger and lensfile handling. |
| `research/updater/` | 5 | The firmware update command surface. |
| `research/isp/` | 3 | ISP / sensor command work. |

## Running a script

Scripts were written when the project lived at `C:\Users\Minhsnguhoa\pmca-re`
and sat next to the `pmca` package. Two consequences:

- The scripts in `common/` are imported by name. Their importers carry a
  one-line `sys.path` bootstrap; do not remove it.
- Many scripts still hardcode the old absolute project path and will fail
  with `FileNotFoundError` until that is repointed. This is pre-existing and
  unrelated to the move.

Running `retool` is unaffected: see `RETOOL.md`.

## Index

Listed by original filename, because the notes in `docs/` refer to the
scripts by bare name.

<details><summary><code>research/common/</code> — 2 files</summary>

- `senser_fix.py`
- `zve10_dumpall.py`

</details>

<details><summary><code>research/crypt/</code> — 7 files</summary>

- `brute_enter.py`
- `brute_enter2.py`
- `brute_opcode.py`
- `scan_bnb.py`
- `scan_bnb2.py`
- `scan_cipher.py`
- `scan_crypter_endpoint.py`

</details>

<details><summary><code>research/device/</code> — 46 files</summary>

- `dump_funcs.py`
- `dump_helper.py`
- `dump_helper2.py`
- `dump_text.py`
- `enum_usb.py`
- `msc_diag.py`
- `msc_dump.py`
- `msc_intr_probe.py`
- `msc_recon.py`
- `msc_scsi_probe.py`
- `nag_reboot.py`
- `nag_zve10.py`
- `probe_scsi.py`
- `probe_storage.py`
- `ptp_9805_sweep.py`
- `ptp_argsweep.py`
- `ptp_deep.py`
- `ptp_deep2.py`
- `ptp_deep3.py`
- `ptp_probe.py`
- `ptp_probe2.py`
- `ptp_raw.py`
- `ptp_scan_ext.py`
- `ptp_trace.py`
- `ptp_unlock.py`
- `ptp_unlock2.py`
- `re_probe.py`
- `run_after_reboot.py`
- `sony_libusb.py`
- `speed2.py`
- `speed_test.py`
- `usb_ids.py`
- `zve10.py`
- `zve10_dump.py`
- `zve10_dumpcard.py`
- `zve10_dumpfw.py`
- `zve10_enum.py`
- `zve10_enum0.py`
- `zve10_gate.py`
- `zve10_msc.py`
- `zve10_poweron_gate.py`
- `zve10_pull.py`
- `zve10_replug_gate.py`
- `zve10_service.py`
- `zve10_shell.py`
- `zve10_wpd.py`

</details>

<details><summary><code>research/diag/</code> — 7 files</summary>

- `diag_fixed.py`
- `diag_known.py`
- `diag_known2.py`
- `diag_offset.py`
- `diag_one.py`
- `diag_pad.py`
- `diag_sizes.py`

</details>

<details><summary><code>research/disasm/</code> — 19 files</summary>

- `disasm_adj.py`
- `disasm_adj_calls.py`
- `disasm_adj_header.py`
- `disasm_bootrom.py`
- `disasm_calls.py`
- `disasm_cmdtools.py`
- `disasm_crypter.py`
- `disasm_crypter_callers.py`
- `disasm_dio_ctx.py`
- `disasm_dllhandler.py`
- `disasm_dmm.py`
- `disasm_dmm_cfg.py`
- `disasm_img_call.py`
- `disasm_img_imports.py`
- `disasm_key.py`
- `disasm_liro.py`
- `disasm_pe_imports.py`
- `disasm_uipc.py`
- `disasm_uipc2.py`

</details>

<details><summary><code>research/firmware/</code> — 27 files</summary>

- `analyze_adj_usage.py`
- `analyze_bins.py`
- `analyze_cmdtools.py`
- `analyze_crypter.py`
- `analyze_fdat.py`
- `analyze_libupdaterbody.py`
- `analyze_loaders.py`
- `analyze_strings.py`
- `analyze_surface.py`
- `analyze_tools.py`
- `analyze_udtrbody.py`
- `analyze_uipc.py`
- `carve_elf.py`
- `carve_udtrbody.py`
- `debug_elf_layout.py`
- `decompress_udtrbody.py`
- `decompress_udtrbody2.py`
- `extract_fw.py`
- `extract_udtr.py`
- `find_crypter_syms.py`
- `find_tpzl.py`
- `find_updater_path.py`
- `forge_dat.py`
- `full_decrypt.py`
- `fwtool_ma1co.py`
- `sha1_decrypt.py`
- `verify_decrypt.py`

</details>

<details><summary><code>research/isp/</code> — 3 files</summary>

- `sample_isp.py`
- `scan_isp.py`
- `scan_sndcmd_ids.py`

</details>

<details><summary><code>research/lens/</code> — 5 files</summary>

- `lens_query.py`
- `scan_lens_trigger.py`
- `scan_lensfirm.py`
- `scan_lensfirm2.py`
- `sony_cmd.py`

</details>

<details><summary><code>research/scan/</code> — 7 files</summary>

- `scan_avcam_delivery.py`
- `scan_avcam_trigger.py`
- `scan_avcam_update.py`
- `scan_rootfs.py`
- `scan_rootfs_ctx.py`
- `scan_udtr_format.py`
- `scan_update_trigger.py`

</details>

<details><summary><code>research/updater/</code> — 5 files</summary>

- `cmd_surface.py`
- `scan_pc_updater.py`
- `scan_pc_updater2.py`
- `scan_updater_pc.py`
- `updater_probe.py`

</details>

