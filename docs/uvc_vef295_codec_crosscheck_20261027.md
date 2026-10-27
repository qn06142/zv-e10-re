# VEF 0x295 decoding theory: independent firmware cross-check

27 October 2026. Offline only; no camera access or patch changes. Reviewed the external decoding report and its actual build_fullres_reconstruction.py implementation. Do not overwrite that agent's report. This audit provides confidence boundaries and concrete missing pieces.

## Finding

The report contains useful, reproducible evidence of structured, spatially correlated native image bytes. The 64-byte-block / 30-block-row / compressed-HD interpretation is a strong working hypothesis. It does NOT yet establish an exact decoder, active 1920x1080 descriptor, exact 1-byte-per-pixel codec, 8-bit/10-bit source, color sampling order, or tear-free capture. Its use of "proven" is too broad. A pattern resembling scene structure supports an image source but is not a validation of all generated pixel detail or color.

## Claims checked against original firmware

Exact camera-matching patched RTOS MD5 90096db2c76148f4f9db5d104e5c608c was used. Original Thumb instructions were executed in Unicorn, with only logging calls replaced for these new tests. Hardware was not emulated.

1. VEF table at 0x645b580c, stride 56: record 0 has valid/canvas 1920x1080, record 1 valid1440x1080/canvas1472x1080, record4 valid/canvas1280x720, record5 valid/canvas640x480. All use unit0x295. Original builder block0x6374cdd4..0x6374cf38 sets yc_compress=1 in those three HD records and0 in VGA. This confirms available configurations, not which one was attached to the captured packet. Same allocation family spans multiple geometries and compression modes. The earlier producer/allocator trace remains valid.

2. Crucial qualification: 0x6374cf0e loads64 and0x6374cf14 stores strip_width BEFORE the branch that sets yc_compress at0x6374cf1a..0x6374cf2c. Executing all four records produces strip_width64, including UNCOMPRESSED VGA. Therefore strip_width64 does not prove compressed packets are64bytes or that compression is active.

3. Original CheckOutputImageMirrorYcCompAlignment at0x63a460d4 checks mode argument r2 in{1,3} and compression argument r3==1, then tests (u16(object+0x30)+u16(object+0x34)) &63. Misalignment returns5, aligned returns0; other gating combinations return0. All32 combinations passed. This is a conditional alignment restriction, not a universal byte-stride calculation. The report's other address0x63a44708 is a different enclosing check on object+0x24, not this function's entry.

4. CalcStripWidth routines at0x63a37f3c and0x63a3ad04 handle several strip-width selector values. Examples: selector1 returns64,2 returns1408,3 returns1440,5 returns640; the second routine also returns1920 for selector8. Other branches depend on context/configuration. These are geometry/configuration calculations, not bytecode parsing or proof of64-byte storage units. The raw fixture output JSON records all tested returns; do not generalize zero returns from an incomplete context into real widths.

5. The exercised VEF metadata builder leaves yc_bit_depth atwire+0x36 untouched. The audit initialized it to0xa5 and it stayed0xa5. This sentinel is NOT a valid bit depth. YcStateInfo still needs to be recovered for actual y_range/colorimetry/chroma phase. Native data_content/data_placement enum values alone do not establish 4:2:2 or planar order.

6. Inspected SDF compression configuration functions pass/translate compression selections, rather than decoding image sample bits: SetYcCompress-associated code0x636eb63c maps inputs0..5 to matching output values, rejecting larger inputs; the call at0x636ea51c invokes0x63cc3c3e with input/output compression arguments and a configuration-output pointer. That wrapper invokes a virtual operation and records whether either argument is nonzero. These bounded paths contain no recovery of the report's unary tokens, zigzag signs, word ordering or quantizer tables. No matching software pixel decompressor was identified in this pass. That is a bounded negative result, not proof no such implementation exists elsewhere. An exported-symbol scan found metadata getters/setters but no clearly named YC decoder; unrelated magnetometer decomposition symbols were excluded.

## Packet facts independently reproduced

Input SHA256 b0cceb40c44526e72784cec1892dcf86829113ba4c59376f19d5daf2a031714b, length614400B. Grouping into64B blocks gives9600 groups. Byte5 autocorrelation:

| Lag in blocks | Correlation |
| --- | --- |
| 10 | -0.01515 |
| 20 | -0.01629 |
| 29 | 0.19545 |
| 30 | 0.86568 |
| 31 | 0.19402 |
| 60 | 0.82460 |

Byte9 also peaks at30 (0.25476). Exactly3453 groups have W4==W5==0. W0 upper16-bit counts match the report:0xfffa3760,0xfff83047,0xfffc2647. Those are real byte-level results. They support recurring64B structures and a30-block spatial pitch. Interpreting each as64horizontal pixels yields1920pixels/row, and the614400B prefix then spans320rows. The last two steps are still conditional on the packet-to-pixel mapping. Height1080 and row0 origin need live descriptor/data offset/placement confirmation, despite the persuasive2073600-byte allocation-size match.

The proposed W0->W2... and W1->W7... routes remain useful candidates based on the external agent's byte-difference experiments. This firmware pass did not independently establish their bit-exact meaning. No evidence here establishes the AXI beat interpretation.

## Decoder implementation audit

I extracted only the supplied decoder functions with AST (without running its top-level image-writing code), instrumented token counts and ran them on all9600 blocks.

- Luma parses56 residual tokens in9056blocks, fewer in544; the code caps decoding at56, so a count of56 does not prove that exactly56 were encoded.
- Chroma parses64 tokens in3837blocks, fewer in5763 (60.03%). The code fills the remaining samples with unchanged values. Thus the implementation does NOT demonstrate the report's "exactly64tokens" claim for most blocks.
- Quantizer/residual scales1.6,0.8and0.75 are empirical constants in the implementation, not recovered firmware constants.
- Absolute Y uses multiple manually chosen piecewise ranges and offsets (e.g.76,18,80,110). Chroma bases are explicitly modeled around128. Cr base is derived partly from Cb via `128-(Cb-128)*0.55+...`, rather than an independently verified Cr bitfield. These choices can produce bounded natural-looking colors by construction. Bounded chroma and small temporal differences are therefore not independent proof of exact decoding.
- All-zero tail padding does not itself represent a zero residual under the asserted unary code: that code assigns zero to the bit1. An explicit implicit-tail/truncation/escape rule is needed before omitted residuals may be filled with zeros. The current parser also treats runs over16zeros as termination without firmware validation.
- No validated stream-length/termination rule or nonoverlap check prevents the candidate Y/C parsers from consuming each other's shared words. This must be established before labeling all output pixels recovered.

This does not refute the overall compressed-strip theory. It identifies which parts remain a visualization/calibration model rather than an exact codec.

## What is missing and how to close it

1. Capture the whole allocation from one owned copy; revision2.9 is prepared for this. It uses64-byte headers, so each614400-byte USB packet carries614336native bytes. Reassemble with its supplied reassemble.py; do not concatenate packets or apply the external report's old614400-byte native-offset schedule. A2073600B snapshot needs4packets; the final payload is230592B.
2. Obtain ImageSizeInfo and YcStateInfo belonging to the SAME producer delivery and unit handle. Needed fields include valid/canvas geometry, offsets, unit_data_offset, data_site, placement/content/scan, yc_compress, strip_width, yc_bit_depth, y_range, colorimetry and chroma phase. Inspect active segments if applicable. A configuration table and a DMM capacity cannot substitute for the live descriptor.
3. Recover the actual anchor/quantizer/escape/termination specification, from deeper firmware/register configuration tracing or independent controlled captures (dark/bright/ramp/color patches, known transitions). Require bit accounting and tests across scenes, not just coherent output on one static scene. A verified hardware uncompress/resize path could be an alternative, but invoking it safely requires its native configuration/ownership protocol; merely clearing a flag would mislabel bytes.
4. Establish producer completion and source lifetime explicitly. Observing pin SEND before SendComp may be a promising interception point, but a hook alone does not guarantee safe retention after original callbacks/acknowledgements. The pin's actual ownership/return protocol and any cache synchronization remain necessary. A static scene with no visible seam cannot prove absence of tearing.

Current patch preparation remains2.9 OFFLINE ONLY, installed camera version remains2.8. This audit made no firmware changes. Next step should favor live metadata plus full capture before implementing a permanent decoder from the present heuristic.

## Reproducibility

Scripts: work/yc-codec-audit/verify_firmware.py, verify_packet_structure.py, audit_decoder.py, audit_decoder_functions.py, string_xrefs.py and disasm.py. Evidence: firmware-verification.json (32alignment cases,13strip-selector cases,4metadata cases), packet-structure-verification.json, decoder-audit.json, disassembly and Linux-symbol scan in this folder. Original reconstruction files were read only and remain unchanged.
