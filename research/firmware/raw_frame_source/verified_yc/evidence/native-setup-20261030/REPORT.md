# Native configuration trace: verified forwarding and real recorder dispatch

30 October 2026. Offline only; no camera access, flash, reboot or configuration changes. Revision 4.0 remains unchanged. The target is genuine native 10/12-bit YC with no 8-bit fallback.

## RTOS config+0x37: exact chain, meaning still unproved

The submitted producer-flag claim refers to the byte at ([0x64277f68+0x34])+0x37. Original RTOS code does contain this getter:

- 0x637cd6b0 loads global 0x64277f68 via a PC-relative literal, dereferences +0x34 and returns byte +0x37.
- Its one direct immediate caller found is 0x637cf926. The next call, 0x637cf92a, invokes 0x638514c0 with that result.
- 0x638514c0 normalizes zero/nonzero to 0/1 at 0x6414fb40+0x36. It does not preserve separate values 10 and 12, or enums 1 and 2.
- Original getter, both call instructions and setter executed successfully for source bytes 0,1,2,10,12,255. All nonzero inputs became 1. No external functions were mocked on this bounded chain.
- Getter 0x638513e4 returns structure base 0x6414fb40. Its direct callers include configuration builders around 0x637cf468/0x637cf500/0x637cf50c/0x637cf558/0x637cf9ac, a query dispatcher at 0x637ceb7c and status serialization at 0x63d2ebd4/0x63d2ebdc. These findings do not establish a hardware producer command or pixel allocation.

Crucial limit: this structure's +0x36 is NOT established as the SSYC wire depth byte just because the offset matches. No type identity or copy into an SSYC image descriptor was demonstrated. Likewise a boolean flag could still select a genuine hardware mode through an as-yet-untraced consumer; normalization alone neither establishes nor disproves that. Do not name this a certified depth control, or patch it as if it generates high-depth samples.

The PC-relative literal search intentionally collects candidate load/add pairs. Older loads may have been overwritten before an ADD; nearby target matches are not all validated references. Exact getter/call/setter cases were validated by original execution. The data are saved to make rejected candidates auditable.

## Recorder: virtual dispatch now demonstrated, not just matched names

Saved libmpr.so contains a virtual-table address point at +0xa0c788. Slot +0x10 points to ConvMovieRecParam (+0x3f6371, Thumb); slot +0x14 points to MovieRecorder::ConvertPictureQualityMpr2Pub (+0x3f6283, Thumb). The previous report located compatible functions but did not execute their virtual binding.

Executed the original ConvMovieRecParam slice +0x3f639c..+0x3f63c0 using this relocated saved table, source MovieRecParam and controlled stack content 0x100. Original indirect BLX at +0x3f63b4 reaches the real MovieRecorder wrapper, then the real PubUtil converter and returns to store MovieRecConvParam+0x0c. No converter stand-in was used.

For quality enum 8, results are:

| MPR depth enum | Name | color enum 0 | color enum 1 |
| --- | --- | --- | --- |
| 0 | 8bit | 0x18 | 0x18 |
| 1 | 10bit | 0x43 | 0x44 |
| 2 | 12bit | 0x18 | 0x18 |

All six slice cases pass with output error flag zero. These are public quality identifiers, not pixel encodings. No claim about the meanings of color enums 0/1 is made here. The 12-bit value still follows the 8-bit mapping in this route. A controlled saved-table test does not certify that a live camera chooses this exact runtime class.

The recording-start inner function +0x3f99d4 obtains converter slot +0x10 at +0x3f9a16 and calls it at +0x3f9a4a. Converted parameter storage uses object +0x4544 + channel*0x1cc. The preceding FeaCore cache-to-MovieRecParam chain is documented in producer-depth-20261030.

## Allocation branch checked

MRecFltMgr_bni::SetBaseRecBufInitParam (+0x3fd630) selects a recording line, reads converted parameters at +0x74/+0xb8 and fills base record-buffer init fields +0x24/+0x28. It is not demonstrated to allocate native YC pixel planes. Its name is insufficient evidence for a high-depth DMM allocation; do not substitute these fields for source plane capacity/stride.

## Remaining boundary

No trace in this pass has reached a verified producer precision register, hardware format request or physical YC allocation. Next work must identify the actual writer/consumer of producer configuration, establish sample precision and allocation layout and then use the matched SEND/SDS/typed attachment/DMM handle chain. Recording quality identifiers and queried boolean configuration fields cannot certify source samples. No new binary was produced.

## Reproduction and evidence

Run .local/work/yc-native-setup-20261030/verify_config_forwarding.py from the existing workspace. It uses .local/work/yc-frame-contract-20261029/rtos.py and rtos_harness.py, plus .local/work/vga-v40/recipe/verify_support.py. Original RTOS MD5 cdcae9d4fdbf66a33704a4c7564e346d (asserted by loader); original libmpr SHA256 68f426bf362783de9e548f5b84d3ba9093097b87de84ff4f94643994f5389a37. Helpers and new verification source are copied alongside this evidence for reference; original firmware binaries are excluded.

verification.json records six RTOS forwarding tests and six Linux indirect-dispatch tests. Raw disassembly and candidate/caller inventories are also retained. These bounded original-instruction tests do not execute a full camera session, ISP or allocator.
