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

**No camera binary or firmware image is tracked in this repository.** Every script
here takes one as an *input* from the git-ignored `dumps/` tree and emits
inventories, tables or documentation. Patched objects are reproducible from a
tracked script plus a file you pull off your own camera — the recipes and hashes
are in [`firmware/PATCHED_OBJECTS.md`](firmware/PATCHED_OBJECTS.md), and the
boundary is spelled out in [`docs/09-provenance.md`](../docs/09-provenance.md).

## Layout

| Directory | Files | Purpose |
|---|---:|---|
| `research/firmware/` | 213 | Firmware image structure: format analysis, carving, decompression, decryption, payload extraction. |
| `research/device/` | 52 | Talking to the camera over USB: PTP/MTP, mass storage, enumeration, card and firmware pulling. The only group that needs a physical ZV-E10 attached. |
| `research/disasm/` | 19 | Per-subsystem disassembly. Superseded for `av-cam.bin` by the `retool` package, kept for the other images. |
| `research/crypt/` | 7 | Brute-force and cryptanalysis of the update/crypter paths. |
| `research/diag/` | 7 | Diagnostics: offset, padding and size checks on carved regions. |
| `research/scan/` | 7 | Byte/string sweeps over firmware images looking for structure. |
| `research/lens/` | 5 | Lens protocol: query, trigger and lensfile handling. |
| `research/updater/` | 5 | The firmware update command surface. |
| `research/isp/` | 3 | ISP / sensor command work. |
| `research/common/` | 2 | Helpers shared across topics. `senser_fix` and `zve10_dumpall` are imported from `device/`, `diag/` and `isp/` alike, so they cannot live in any one of those. Each importer puts this directory *and* the repository root (for the `pmca` package) on `sys.path`. |

## Running a script

Scripts were written when the project lived at `C:\Users\Minhsnguhoa\pmca-re`
and sat next to the `pmca` package. Two consequences:

- The scripts in `common/` are imported by name. Their importers carry a
  one-line `sys.path` bootstrap; do not remove it.
- **Path portability is partial, and here is the honest split.** Of the 317
  scripts in this tree, **82 resolve their inputs** from their own location via
  a `ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]` bootstrap and run
  from any checkout. **152 still hardcode an absolute path** to either
  `D:\02_Development_And_Projects\pmca-re` or the harness temp directory, so they
  only run on the machine that wrote them. 83 take no path at all.

  The tools **cited in `docs/` are all in the portable set** — `annotate.py`,
  `sysdef_tables.py`, `mwf_catalog.py`, `mwf_ids.py`, `scenario_vocab.py`,
  `imcfg_block.py`, `factor_table.py`, `cmd_surface.py`, `elf_catalog.py`,
  `vdf_methods.py`, `uxc_color.py`, `verify_view_parser.py`, `testcmd_elf.py`,
  `testcmd_thumb.py`, `zve10_retry.py`, `lens_query.py`, `scan_lensfirm2.py`,
  `check_docs.py`. Following the documentation works on a fresh checkout. The
  unpinned remainder are one-shot exploration scripts, kept as the working
  record rather than as a supported interface.

  The bootstrap is named `ROOT_REPO` and not `REPO` because several scripts
  already use `REPO` for something else — a vendored tool path, usually. Six
  scripts use the shorter `ROOT` instead; both are load-bearing, so do not
  rename either.

`research/firmware/fix_hardcoded_paths.py` performs the rewrite. It is
idempotent, skips itself, self-tests its own quoting, and compile-checks every
file it touches, so it is safe to re-run if more paths turn up.

**But note its scope honestly:** it rewrites literals matching the *previous*
machine's home (`C:\Users\Minhsnguhoa\pmca-re`), not the current repo root or
the harness temp directory. It has therefore been re-run against the paths that
actually appear now, but a further pass over the 152 remaining scripts has not
been done. Extending the tool to cover `D:\02_Development_And_Projects\pmca-re`
is the obvious next step if the whole tree needs to be portable.

Running `retool` is unaffected: see `RETOOL.md`.

## Index

Listed by original filename, because the notes in `docs/` refer to the
scripts by bare name.

<details><summary><code>research/firmware/</code> — 213 files</summary>


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
- `annotate.py`
- `apl_find.py`
- `apl_layer.py`
- `app_resources.py`
- `arity_census.py`
- `arity_verify.py`
- `arm_helper.py`
- `arm_ioctl.py`
- `arm_probe.py`
- `arm_stack_sim.py`
- `arm_static_check.py`
- `arm_transfer.py`
- `arm_verify.py`
- `bb_info.py`
- `bright_lut.py`
- `build_inject.py`
- `carve_elf.py`
- `carve_udtrbody.py`
- `cave_check.py`
- `cave_reach.py`
- `cave_scan.py`
- `cave_sound.py`
- `check_docs.py`
- `check_stamp.py`
- `check_vanilla.py`
- `cluster_6b40.py`
- `consume_key.py`
- `datarelro_hunt.py`
- `debug_elf_layout.py`
- `decompress_udtrbody.py`
- `decompress_udtrbody2.py`
- `dep_graph.py`
- `desc_walk.py`
- `diff_variants.py`
- `disasm_dispatch.py`
- `dispatch_read.py`
- `dmm_fb.py`
- `dmm_regions.py`
- `dmmconfig.py`
- `elf_catalog.py`
- `engine_colour.py`
- `engine_names.py`
- `engine_names2.py`
- `engine_names3.py`
- `extract_fw.py`
- `extract_udtr.py`
- `factor_table.py`
- `fb_detect.py`
- `fdat_decrypt.py`
- `find_base.py`
- `find_crypter_syms.py`
- `find_display.py`
- `find_output.py`
- `find_ram.py`
- `find_rect_key.py`
- `find_rect_reader.py`
- `find_setter_callers.py`
- `find_tpzl.py`
- `find_updater_path.py`
- `find_uxengine.py`
- `fix_hardcoded_paths.py`
- `flash_fs_probe.py`
- `forge_dat.py`
- `full_decrypt.py`
- `fwtool_ma1co.py`
- `geom_layout.py`
- `get_busybox.py`
- `global_xdb.py`
- `graphics_find.py`
- `grm_modules.py`
- `icon_bar_sheet.py`
- `icon_bars.py`
- `icon_cands.py`
- `icon_classify.py`
- `icon_edit.py`
- `icon_opx.py`
- `icon_opx_sheet.py`
- `icon_opx_zoom.py`
- `icon_res_sheet.py`
- `icon_sheet.py`
- `icon_survey.py`
- `icon_targets.py`
- `icon_targets_verified.py`
- `im_elf.py`
- `imcfg_block.py`
- `imdb_table.py`
- `kpageflags_walk.py`
- `ldec_dis.py`
- `ldec_ioctl.py`
- `ldec_ko.py`
- `make_bundle2.py`
- `make_uxc_bundle.py`
- `memcpy_sites.py`
- `memcpy_window.py`
- `mod_align.py`
- `mod_caller.py`
- `mod_callsite.py`
- `mod_diff.py`
- `mod_disasm.py`
- `mod_lineage.py`
- `mod_module.py`
- `mod_strings.py`
- `mount_assessment.py`
- `mwf_catalog.py`
- `mwf_ids.py`
- `nflasha15_super.py`
- `obj_names.py`
- `opx_payload.py`
- `oril_header.py`
- `oril_segments.py`
- `osal_id_map.py`
- `outvid_calls.py`
- `outvid_funcs.py`
- `outvid_path.py`
- `pagemap_probe.py`
- `pagewalk.py`
- `pick_slot.py`
- `planecopy.py`
- `posid_follow.py`
- `posid_hypothesis.py`
- `prop_table.py`
- `rawdump.py`
- `reader_across_libs.py`
- `recheck_outvid.py`
- `regen_research_readme.py`
- `registry_resolve.py`
- `regress_pcrel.py`
- `resolve_dispatch.py`
- `ringbuf.py`
- `scenario_ids.py`
- `scenario_vocab.py`
- `sha1_decrypt.py`
- `stage_busybox.py`
- `stream_ko.py`
- `string_patch.py`
- `surf_geom.py`
- `surf_id.py`
- `surf_render.py`
- `sysdef_tables.py`
- `testcmd_dis.py`
- `testcmd_elf.py`
- `testcmd_gram.py`
- `testcmd_parse.py`
- `testcmd_thumb.py`
- `thumb.py`
- `trace_bool.py`
- `trace_bool2.py`
- `trace_version.py`
- `updater_key.py`
- `usr_tar_stream.py`
- `uxc_bool_hunt.py`
- `uxc_bool_hypotheses.py`
- `uxc_bool_meaning.py`
- `uxc_color.py`
- `uxc_find_safe.py`
- `uxc_format.py`
- `uxc_id_puzzle.py`
- `uxc_inline.py`
- `uxc_key_hash.py`
- `uxc_loader2.py`
- `uxc_loader_hunt.py`
- `uxc_recheck.py`
- `uxc_safe.py`
- `uxc_shift.py`
- `uxc_style.py`
- `uxc_style_derive.py`
- `uxc_style_field.py`
- `uxc_style_rec.py`
- `uxc_tlv.py`
- `uxc_view_rec.py`
- `uxc_views.py`
- `uxc_widget_rec.py`
- `uxc_xref.py`
- `uxc_xref_full.py`
- `vdf_align.py`
- `vdf_bright.py`
- `vdf_execute.py`
- `vdf_index.py`
- `vdf_inner.py`
- `vdf_members.py`
- `vdf_methods.py`
- `vdf_pat.py`
- `vdf_rtti.py`
- `vdf_simple.py`
- `vdf_strref.py`
- `vdf_strref2.py`
- `vdf_strref3.py`
- `verify_decrypt.py`
- `verify_full_format.py`
- `verify_index_rule.py`
- `verify_inject.py`
- `verify_view_parser.py`
- `view_colour_path.py`
- `view_colour_path2.py`
- `view_geometry.py`
- `view_geometry2.py`
- `view_geometry3.py`
- `view_geometry4.py`
- `vtable_census.py`
- `vtable_diff.py`
- `vtable_probe.py`

</details>

<details><summary><code>research/device/</code> — 52 files</summary>


- `audit_surface.py`
- `diag_stream.py`
- `dump_funcs.py`
- `dump_helper.py`
- `dump_helper2.py`
- `dump_text.py`
- `enum_usb.py`
- `im_runtime_manifest.py`
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
- `push_file.py`
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
- `zve10_live.py`
- `zve10_msc.py`
- `zve10_poweron_gate.py`
- `zve10_pull.py`
- `zve10_replug_gate.py`
- `zve10_retry.py`
- `zve10_service.py`
- `zve10_shell.py`
- `zve10_wpd.py`

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

<details><summary><code>research/crypt/</code> — 7 files</summary>


- `brute_enter.py`
- `brute_enter2.py`
- `brute_opcode.py`
- `scan_bnb.py`
- `scan_bnb2.py`
- `scan_cipher.py`
- `scan_crypter_endpoint.py`

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

<details><summary><code>research/scan/</code> — 7 files</summary>


- `scan_avcam_delivery.py`
- `scan_avcam_trigger.py`
- `scan_avcam_update.py`
- `scan_rootfs.py`
- `scan_rootfs_ctx.py`
- `scan_udtr_format.py`
- `scan_update_trigger.py`

</details>

<details><summary><code>research/lens/</code> — 5 files</summary>


- `lens_query.py`
- `scan_lens_trigger.py`
- `scan_lensfirm.py`
- `scan_lensfirm2.py`
- `sony_cmd.py`

</details>

<details><summary><code>research/updater/</code> — 5 files</summary>


- `cmd_surface.py`
- `scan_pc_updater.py`
- `scan_pc_updater2.py`
- `scan_updater_pc.py`
- `updater_probe.py`

</details>

<details><summary><code>research/isp/</code> — 3 files</summary>


- `sample_isp.py`
- `scan_isp.py`
- `scan_sndcmd_ids.py`

</details>

<details><summary><code>research/common/</code> — 2 files</summary>


- `senser_fix.py`
- `zve10_dumpall.py`

</details>
