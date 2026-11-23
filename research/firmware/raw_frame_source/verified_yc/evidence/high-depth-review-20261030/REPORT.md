# Independent review of the submitted Imola packing findings

30 October 2026. Offline only. Camera remains4.0. No live IPC, configuration change, flash, reboot or memory-pool scan. User's active target remains genuine native10/12-bitYC; no8-bit fallback or padded8-bit samples.

## Confirmed: diagnostic field offsets, not an OPEN builder

Original function0x6368cffc..0x6368d828 is an open_param diagnostic dump in enc/sfmc_enc_codec_video.cpp. Its tail returns at0x6368d828;0x6368d82c onward is a literal pool. It reads an existing request and logs fields. Original execution, with logging/context/time stubs, verifies +0x50=input_image_bit_depth,+0x54=input_image_compress,+0x58=input_image_chroma. Setting the input-info-valid flag at+0x38 enables those log rows. Three controlled values1/2/3 were logged unchanged. This function does NOT itself build the request, force chroma0, switch producer precision, dispatch0x2103, or prove a live source. Any claimed SSYC->request copy and OPEN route must be demonstrated in the actual builder/sender separately. Earlier45-case metadata-consumer execution remains valid but does not alone bridge all request offsets/enums.

## Material correction: constants are NOT packed-versus-padded frame sizes

The cited code is in dec/imola_dec_state.cpp. Original instructions0x639f506e onward accept configuration depth0or1. Both paths set arithmetic parameters identically: r3=8,r1=2; calculate(width*height*2*8)>>3; then execute original division helper0x635dbae0 with divisor2. Result is width*height for BOTH depths.

It compares that result against0x1fa400,0x4f1a00,0x7e9000 and selects identifiers0x36a,0x3d0,0x369 at object+0x45c00. Those constants equal pixel counts1920x1080,2560x2025,3840x2160 for these controlled dimensions. Twelve original-instruction cases verify both depths, all three boundaries and oversize rejection.1920x1080selects0x36a for BOTH depths. They cannot establish5,184,000-byte packed10-bit buffers versus8,294,400-byte padded10-bit buffers, component order,5-byte groups, row stride or output mode4/5. Arithmetic coincidence with1920x1080*2.5or*4is not a packing proof.

Output mode4/5 is selected later from depth and additional decoder state. Its meaning still needs recovery independently of these bucket constants. Actual allocation capacity must come from the relevant allocation result/configuration and be associated with its live producer.

## Material correction: cited routing is a record/pointer operation

Code0x639e953a..0x639e9564 tests object+0x4bb0 against1. On1it calls a copy with length64bytes, maps the copied first pointer through0x63c48e0c(site argument17), adds object+0x4bb4, and stores the resulting pointer. Values0and2skip those operations. Three original-branch cases prove this behavior with copy and mapping services mocked. Source diagnostic filename nearby is common/imola_common_api_enc_handler.cpp.

This proves a record-copy/pointer-adjustment branch, not a bypass of an8-bit pixel-plane copy. It does not prove object+0x4bb0is a depth field, a camera source configuration, or a connection to the SSYC depth enum. Trace that flag's writers and the pointed-to record before assigning semantics.

## Host format corrections

Microsoft's primary format documentation defines P010as10-bit4:2:0, P210as10-bit4:2:2semi-planar, and Y210as10-bit4:2:2packed using four16-bit words per two pixels. The10significant bits occupy the upper bits, with six low bits zero. Those zero container bits do not mean an8-bit source is acceptable; source precision must still be proved.

Apple's CoreVideo format-block documentation describes v210as6pixels per128-bit block, or16/6bytes per pixel before stride padding. That is not a tightly packed5bytes/two-pixel format. A bare10-bit4:2:2sample count is20bits/pixel=2.5bytes/pixel, but that alone does not identify an actual storage format. Do not advertise native bytes as v210/Y210/P210until packing, planes, stride, alignment and bit significance match. Choosing a UVC version is not a substitute for those proofs or host-driver support.

Primary references:
https://learn.microsoft.com/en-us/windows/win32/medfound/10-bit-and-16-bit-yuv-video-formats
https://developer.apple.com/documentation/corevideo/kcvpixelformatblockwidth

## What remains useful and what to do next

The recording-depth selector and request field names are useful leads. Consumer/decoder support does not establish that the camera ISP/YC producer emits that precision. The new assertions about forwarding through libmpr/libmprctrl and configuration[+0x37] are not independently established here. Trace actual setters, IPC builder/dispatcher and producer hardware-format registers; do not invoke drawing/playback APIs or write a guessed flag as a shortcut.

Keep the genuine10/12-bit requirement. Recover producer mode, actual DMM allocation/capacity, sampling/packing and reference/completion behavior; only then select transport format. No new high-depth binary is justified by this submitted report alone. No camera behavior changed by this review.
