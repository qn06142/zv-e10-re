# Recording depth configuration traced; native YC producer still unproved

30 October 2026. Offline only. Camera revision 4.0 unchanged; no camera connection, configuration command, reboot or flash.

## Evidence and tested behavior

Original saved libmpr.so (13,021,036 bytes), SHA256 68f426bf362783de9e548f5b84d3ba9093097b87de84ff4f94643994f5389a37. Addresses below are ELF-relative Thumb code addresses, without the Thumb entry bit.

- MprIf::SetRecVideoBitDepth at 0x8aee08 forwards through FeaIf at 0x5549a4 to FeaCore at 0x5420dc. A VBitdepthParam entry is an eight-byte channel/depth pair. With enclosing state 3/4 and channel state 1/5, the core accepts depth values 0..2 and writes object + channel*0x108 + 0x176c. Invalid depth returns 5; disallowed states return 10. This core setter caches state; it does not dispatch producer hardware commands.
- Original CnvVideoBitDepth at 0x899774 labels enum 0/1/2 as 8bit/10bit/12bit; 3 is unknown. These names establish MPR enum meanings, not physical YC precision.
- Crucial consumer found: FeaCore::RecStart at 0x543324 reads the cached depth at 0x5436e0..0x5436e6 and stores it into its MovieRecParam at offset +0x6c (stack r7+0x90 relative to struct r7+0x24). Twelve native slice tests cover all four channels and depths 0/1/2. The record-start call at 0x5438d6 passes this structure to code at 0x3f56d0.
- MovieRecorder::ConvMovieRecParam at 0x3f6370 reads color/depth +0x68/+0x6c and passes them to the virtual picture-quality converter. The exported MovieRecorder converter at 0x3f6282 forwards to PubUtil::ConvertPictureQualityMpr2Pub at 0x737fbc. The exact runtime virtual-table binding was not executed in this fixture.
- Original PubUtil converter was executed in 504 controlled cases: 42 quality enums, two color enums, two bool values and three depth enums, with content 0x100. Depth 1 selects distinct public quality identifiers for some combinations. Depth 2 produces exactly the same identifier as depth 0 in all 168 quality/color/bool combinations. A named 12-bit setter value is therefore not evidence that this recording conversion route supports 12-bit output. This is a software identifier mapping result, not a captured-pixel measurement.
- Independently, MprLibCore::GetPictureQualityForCodecDrv at 0x8a4438 was executed in 252 cases. Depth 2 likewise matches depth 0 in all 84 quality/color combinations. E.g. quality 8/color 0 maps depth 0/1/2 to 0x08/0x43/0x08; quality 36/color 0 rejects 0/2 (0xff, return 0) while accepting depth 1 (0x52, return 1). No direct Thumb BL callers to this overload were found; do not conflate it with the record-start chain or assume it is used on this camera.
- FeaCore::SetColorFormatAndVideoBitDepthToEnterRecParam at 0x54917e copies requested color/depth to recorder-entry offsets +0xe8/+0xec only for content 0x100; otherwise both become 255. Four original-instruction cases verify this. The unnamed builder around 0x5491a4 calls this helper at 0x54942a using incoming +0xec/+0xf0. Another CreateEnterRecParam at 0x547984 copies +0xe8/+0xec. These structured configuration copies are not sample generation.
- The libObj recording-format cache is indexed: setter 0x9625c4/getter 0x95da8c use context + profile_index*0x19c +0x270. A verified call edge from property 0x2007 to the above MPR setter remains missing.

## Verification limits and next work

The verifier executes the original ELF instructions in Unicorn with controlled object state and memory. It does not emulate the sensor, ISP, physical DMM allocations or actual RTOS IPC. The RecStart check is a bounded instruction slice, not a full recording session. No retained frame is certified 10/12-bit. No new flashing binary is justified yet.

Follow the depth-sensitive public quality identifiers into native recording/producer setup and allocation; distinguish encoder input interpretation from producer precision. Independently locate the writer and actual semantics of the proposed RTOS config+0x37 flag before using it. Establish sample depth, compression, plane/stride layout, allocation capacity and lifetime from that source. Then transport those samples without the old 8-bit resize path. Keep the no-8-bit-fallback requirement.

The disassembly helper now continues across embedded literal pools with Capstone skipdata. Earlier function dumps could stop at a pool, hiding the RecStart cache read. Complete dumps retain pool bytes as disassembly/data, so instruction-looking pool entries still need control-flow validation. The cache-read slice above was executed, not inferred solely from a linear listing.

## Artifacts

verify_record_depth_api.py records 11 core/helper cases, 12 channel-cache copy cases, four enum labels, 252 codec-quality and 504 public-quality executions. Assertions cover return values/cache writes, enum names and 12-bit/8-bit mapping equivalence. Mapping tables preserve all outputs rather than equating success with native high-depth capability.

find_callers.py and elf_calls_complete.py support offline direct-call/disassembly inspection. The verifier additionally uses workspace .local/work/vga-v40/recipe/verify_support.py for original ELF loading and relocation; that dependency is included as verify_support.py with this evidence package. Original firmware binaries are not copied into this package.
