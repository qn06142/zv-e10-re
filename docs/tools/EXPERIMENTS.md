# Experiment records

Reviewed 18 November 2026. Each experiment directory contains EXPERIMENT.json with status, source/recipe hashes, known firmware input hashes, reproduction instructions, hardware result and rollback context. Empty firmware hashes and unresolved commands are explicit open items.

The records preserve historical recipe instructions. They do not certify a current installation or authorize replaying an old deployment. The current checkpoint lives in [current status](../CURRENT_STATUS.md).

| Experiment | Status | Record |
| --- | --- | --- |
| 4k12bit_baseline_20261027 | historical | [record](../../research/firmware/4k12bit_baseline_20261027/EXPERIMENT.json) |
| live_bayer_tap_v01 | offline-candidate | [record](../../research/firmware/raw_frame_source/verified_bayer/live_bayer_tap_v01/EXPERIMENT.json) |
| raw_receiver_v01 | offline-candidate | [record](../../research/firmware/raw_frame_source/verified_bayer/raw_receiver_v01/EXPERIMENT.json) |
| raw_uvc_v01 | historical | [record](../../research/firmware/raw_uvc_v01/EXPERIMENT.json) |
| usb3_24fps_transport | historical | [record](../../research/firmware/usb3_24fps_transport/EXPERIMENT.json) |
| yc_observer | historical | [record](../../research/firmware/yc_observer/EXPERIMENT.json) |
| yuy2_transport_v2 | historical | [record](../../research/firmware/yuy2_transport_v2/EXPERIMENT.json) |
| yuy2_transport_v21 | failed | [record](../../research/firmware/yuy2_transport_v21/EXPERIMENT.json) |
| yuy2_transport_v22 | historical | [record](../../research/firmware/yuy2_transport_v22/EXPERIMENT.json) |
| yuy2_transport_v23 | historical | [record](../../research/firmware/yuy2_transport_v23/EXPERIMENT.json) |
| yuy2_transport_v24 | historical | [record](../../research/firmware/yuy2_transport_v24/EXPERIMENT.json) |
| yuy2_transport_v24p | hardware-observed | [record](../../research/firmware/yuy2_transport_v24p/EXPERIMENT.json) |
| yuy2_transport_v25 | historical | [record](../../research/firmware/yuy2_transport_v25/EXPERIMENT.json) |
| yuy2_transport_v26_raw | historical | [record](../../research/firmware/yuy2_transport_v26_raw/EXPERIMENT.json) |
| yuy2_transport_v27_snapshot | historical | [record](../../research/firmware/yuy2_transport_v27_snapshot/EXPERIMENT.json) |
| yuy2_transport_v28_snapshot | historical | [record](../../research/firmware/yuy2_transport_v28_snapshot/EXPERIMENT.json) |
| yuy2_transport_v29_full_snapshot | historical | [record](../../research/firmware/yuy2_transport_v29_full_snapshot/EXPERIMENT.json) |
| yuy2_transport_v30_vga | historical | [record](../../research/firmware/yuy2_transport_v30_vga/EXPERIMENT.json) |
| yuy2_transport_v31_vga_init_fix | historical | [record](../../research/firmware/yuy2_transport_v31_vga_init_fix/EXPERIMENT.json) |
| yuy2_transport_v32_source_diagnostics | historical | [record](../../research/firmware/yuy2_transport_v32_source_diagnostics/EXPERIMENT.json) |
| yuy2_transport_v33_source_retry | historical | [record](../../research/firmware/yuy2_transport_v33_source_retry/EXPERIMENT.json) |
| yuy2_transport_v34_team_candidate | historical | [record](../../research/firmware/yuy2_transport_v34_team_candidate/EXPERIMENT.json) |
| yuy2_transport_v35_native_vga | historical | [record](../../research/firmware/yuy2_transport_v35_native_vga/EXPERIMENT.json) |
| yuy2_transport_v36_single_snapshot | failed | [record](../../research/firmware/yuy2_transport_v36_single_snapshot/EXPERIMENT.json) |
| yuy2_transport_v37_event_yc | failed | [record](../../research/firmware/yuy2_transport_v37_event_yc/EXPERIMENT.json) |
| yuy2_transport_v38_descriptor_evidence | historical | [record](../../research/firmware/yuy2_transport_v38_descriptor_evidence/EXPERIMENT.json) |
| yuy2_transport_v39_metadata_settle | historical | [record](../../research/firmware/yuy2_transport_v39_metadata_settle/EXPERIMENT.json) |
| yuy2_transport_v40_no_image_benchmark | historical | [record](../../research/firmware/yuy2_transport_v40_no_image_benchmark/EXPERIMENT.json) |
| yuy2_transport_v41_hd_resize | historical | [record](../../research/firmware/yuy2_transport_v41_hd_resize/EXPERIMENT.json) |
| yuy2_transport_v42_chunked_hd | historical | [record](../../research/firmware/yuy2_transport_v42_chunked_hd/EXPERIMENT.json) |
| yuy2_transport_v43_usb3_hd | offline-candidate | [record](../../research/firmware/yuy2_transport_v43_usb3_hd/EXPERIMENT.json) |

After changing a recorded source or recipe, review the experiment and update its source SHA-256. Record hardware results with mode, boot/process identity, raw evidence and the matching rollback baseline. Run python -B scripts/check_research.py from the repository root to validate records and evidence.
