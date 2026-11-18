# USB and image-source research

Start with [current status](../CURRENT_STATUS.md) for the latest installation and the distinction between observed captures and candidate implementations.

| Question | Read |
| --- | --- |
| What transport has a verified capture? | [VGA colour-bars hardware report](uvc_yuy2_patch_v24p.md) |
| How does YC reach a consumer? | [YC subsystem synthesis](uvc_yc_subsystem_and_codex_findings.md) and [backend corrections](uvc_sony_backend_recovery.md) |
| What is wrong with the proposed Bayer connection? | [Hook claim review](../../research/firmware/evidence/zve10-20261117/CLAIM_REVIEW.md) |
| What must source and staging ownership guarantee? | [USB lifetime audit](../../research/firmware/raw_frame_source/verified_yc/evidence/usb-lifetime-20261029/REPORT.md) |
| Where are the candidate recipes? | [Firmware research index](../../research/firmware/README.md) |
| Where is earlier investigation? | [Diagnostic handoff](uvc_yuy2_diagnostics_handoff.md) and [postmortem](uvc_patch_postmortem.md) |

Other files in this directory are dated investigations and patch-revision reports. Their filenames retain the historical revision and date. Use their test evidence and corrections when evaluating a result.
