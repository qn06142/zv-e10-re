# Native 10/12-bit YC path: initial firmware trace

30 October 2026. The user redirected work away from the 8-bit benchmark and requires at least 10-bit native image data. Native 10/12-bit YC is acceptable; sensor Bayer RAW is not required. Padding an 8-bit image into a wider word is explicitly insufficient. No camera access, firmware write, new 8-bit patch, or live configuration change occurred during this pass. Installed 4.0 remains an 8-bit historical reference, not the target.

## Concrete findings

1. Original Linux libObj.so function +0x95d5cc maps recording-format enum 0 to VIDEO_BIT_DEPTH_8BIT, 1 to VIDEO_BIT_DEPTH_10BIT, and 255 to VIDEO_BIT_DEPTH_INVALID. The original instructions executed successfully for all three cases. This identifies the recording-format enum only.

2. libObj.so +0x970c06 requests parameter key 0x2007 with width/type argument 8. Its non-null branch obtains a value, passes it through +0x9625c4 and logs PARAMID_REC_FORMAT_VIDEO_BIT_DEPTH. The null branch checks recording-format type against 5; one path defaults the field to zero, another to 255. The saved assembly captures the entire branch. A related native command usage string advertises MOVREC SetRecFormat [-VI VideoBitDepth(8bit/10bit/INVALID)]. This is a concrete configuration lead, NOT proof that setting the property configures the ISP or yields native 10-bit YC. It was not invoked on camera.

3. The codec's original RTOS name mapper 0x63a06dfc separately maps 0/1/2/3 to DEPTH_8/10/12/14 (previously executed evidence retained). Its actual direct calls found here are 0x63671d2a and 0x63a129be; both read an enclosing configuration word at +0x38. This is a codec enum, not yet a bridge to SSYC byte +0x36.

4. A confirmed metadata consumer block 0x6368c924..0x6368c976 copies the YC ImageSizeInfo geometry from native wire offsets +0x18/+0x1a/+0x20/+0x22 and reads byte +0x36. It writes output parameter word +0x14 as 0 for zero input and 1 for ANY nonzero input. It independently normalizes compression byte +0x2f to 0/1/2/3. Forty-five combinations (nine byte values, five compression values) executed original instructions and passed. Execution stopped before caller-dependent processing dispatch; no hardware was invoked. The binary split does not establish exact native bit precision, packing, allocation capacity or valid enum values. In particular literal 10/12 metadata writes must not be guessed from this behavior.

5. libBizFw.so and libObj.so export no named pixel-depth setter in the inspected defined symbols. The framework exports SetData_YcBitDepth/GetData_YcBitDepth, but these are metadata field accessors, not demonstrated producer configuration operations. Do not use a metadata-only setter to claim new sample precision.

6. Original VDF initialization declares four type-0 YC output indices 0..3. The existing transport consumes index 0. Additional Send-slot candidates for indices 1 and 3 were located in original code (e.g. calls near 0x6374c922 and 0x6374ac62). These are alternate source-routing leads, not proof that they are unoccupied, safe to connect, high precision or even suitable live video modes. No connection was requested. They must be traced to their actual producer configurations before use.

## Rejected shortcuts and limits

The old 640x480 destination and YUY2 USB presentation are explicitly 8-bit. They cannot satisfy this task. The existing saved source descriptors report a zero YC depth byte, but the precise identity of that byte's enum with the recording/codec enums has not been proved. No retained allocation is certified 10/12-bit here.

The string 220_422_10BIT is in a codec/profile name family next to MPEG/XAVC/ProRes names. It is not a demonstrated DMM unit or a camera capability declaration. Likewise a candidate mapper at 0x636abc20, found from an unrelated structure's +0x36 field, returns MPEG1/MPEG2/AVC/etc. It is a codec-format mapper, NOT YC precision; that lead was rejected. Broad immediate-offset searches include unrelated structures and data-like instruction patterns; only the geometry-matched metadata consumer above is promoted to evidence.

## Next implementation boundary

Trace parameter 0x2007/recording-depth selection through the actual producer setup and hardware format parameters. Establish whether an existing YC output really generates 10-bit or 12-bit samples, including canvas/valid dimensions, compression, allocation size, sampling order, bit placement and write-completion semantics. The minimum qualification is source precision plus sample-preserving transport; neither a profile name, a USB descriptor nor changing SSYC flags is sufficient.

Once a genuine source is established, use the matched SEND -> SDS -> DMM Open -> typed image attachment -> DMM Open chain, preserving grants until a copy is complete. Transport native bytes or a verified high-precision representation without passing through the old 8-bit resize/YUY2 conversion. Unverified or 8-bit sources must not become a fallback. Resolution/rate must fit the verified native allocation and USB path; choose them after the format is known.

No new high-depth flashing binary is ready. The active reverse-engineering target and hard precision requirement are captured in requirements.json. No new benchmark work or diagnostic firmware was introduced.
