# November ZV-E10 runtime evidence

Imported into pmca-re on 18 November 2026. [manifest.json](manifest.json) records original paths, exact byte counts, SHA-256 and context for 27 imported files. Evidence is copied byte for byte. The old session directories remain available as provenance.

## Runtime captures

| Repo path | What it contains | Interpretation |
| --- | --- | --- |
| [codex/tmonitor.txt](codex/tmonitor.txt), [codex/second.txt](codex/second.txt) | Two recording-session trace windows and a second state snapshot. | The user supplied 4K24 as the setting. Actual encoded dimensions and delivery rate were not measured. |
| [codex/state.txt](codex/state.txt), [codex/media.txt](codex/media.txt), [codex/threads.txt](codex/threads.txt), [codex/switches.txt](codex/switches.txt) | Mounts, I/O/IRQ counters and selected movie threads. | Some probes report unavailable applets or unsupported sed syntax. Preserve these errors when evaluating completeness. |
| [codex/live-view.txt](codex/live-view.txt) | Six reads of the same 46.847 ms trace plus state. | Six identical windows represent one trace window. |
| [codex/live-view-counters.txt](codex/live-view-counters.txt), [codex/live-view-recheck.txt](codex/live-view-recheck.txt) | Trace hashes, advancing IRQs, trace parameters and empty reads. | The first hash is nonempty, the second is the empty-input hash. These expose trace-state dependence. |
| [codex/live-view-rearmed.txt](codex/live-view-rearmed.txt), [codex/sensor-markers.tsv](codex/sensor-markers.tsv) | Four distinct explicitly rearmed windows and extracted timing markers. | Masks 15, 15, 4, 4. All windows have 1,024 records. The two CPU-2 windows contain four measured SetImgRd intervals, 41.629–41.754 ms. |
| [codex/tools-check-tmonitor.txt](codex/tools-check-tmonitor.txt) | Trace-reader installation check. | Confirms data read through the installed helper. Freshness needs the additional rearm evidence. |
| [additional-captures/live_view_dmm_extents_units2.txt](additional-captures/live_view_dmm_extents_units2.txt) | Multiple DMM snapshots from the supplied analysis session. | Shows changing handles with type 0x000e0b00 and operation records involving 0x0059000e and 0x01670464. |
| [additional-captures/live_view_full_1.txt](additional-captures/live_view_full_1.txt), [additional-captures/rec_4k24_full_1.txt](additional-captures/rec_4k24_full_1.txt) | IRQ, DMM, thread and UIPC snapshots in the filename-labelled modes. | Recording snapshot includes transient types 0x2d8 and 0x289. Their pixel format and frame identity remain unresolved. |
| [additional-captures/live_view_threads_disk_dmm.txt](additional-captures/live_view_threads_disk_dmm.txt), [additional-captures/live_view_rapid_dmm_dmac.txt](additional-captures/live_view_rapid_dmm_dmac.txt) | Thread and additional allocation/DMA diagnostics. | Counter activity needs operation-specific correlation before assigning a producer-completion meaning. |
| [additional-captures/camera_surfaces_inventory.txt](additional-captures/camera_surfaces_inventory.txt), [additional-captures/kallsyms_and_proc_subdirs.txt](additional-captures/kallsyms_and_proc_subdirs.txt) | Runtime interface and symbol inventories. | A device/proc name identifies an inspection lead. Its open/read/write side effects require separate checking. |
| [additional-captures/live_view_check_1.txt](additional-captures/live_view_check_1.txt), [additional-captures/live_view_traces_1.txt](additional-captures/live_view_traces_1.txt) | Supplemental session checks and traces. | Retain their source context and timestamps when comparing with other sessions. |
| [additional-captures/live_view_mask4_1.txt](additional-captures/live_view_mask4_1.txt), [additional-captures/live_view_udm_osal_1.txt](additional-captures/live_view_udm_osal_1.txt) | Empty capture files. | Failed collection evidence. |

## Installation and candidate records

[demo/install-final.txt](demo/install-final.txt) contains the successful 16 November permanent colour-bars installation readback. The verified MD5s were c1cad400372e26eca729e4b9bc47a237 for usbg_video.ko, 5fde77e394572ebcf420f8941575f6c4 for libInfraStreamingUsb.so and 9181ef744955190d04728cf4ef7965c5 for yuy2_640_v24p.so. It ends with COLOR_BARS_PERMANENT_PAIR_VERIFIED and command status 0.

The later SuperSpeed [manifest](transport/manifest.json), [build script](transport/build.py) and [producer patch](transport/producer-source.patch) describe an offline candidate. Its manifest explicitly sets hardware_tested to false. Its input firmware and generated Sony-derived binaries remain in the original local build directory. [Current project status](../../../../docs/CURRENT_STATUS.md).

The two diagnostic tool sources are now [in research/device](../../../device/zve10_diagnostics/README.md). Private keys, Sony firmware objects, raw partition backups and disassembled instruction dumps were excluded from this import under the existing [provenance policy](../../../../docs/reference/09-provenance.md).

## Review outcome

[CLAIM_REVIEW.md](CLAIM_REVIEW.md) records which claims in the supplied UVC/Bayer mapping were supported, contradicted or left open during the file-based verification. No new camera operation was performed for that review or this import.
