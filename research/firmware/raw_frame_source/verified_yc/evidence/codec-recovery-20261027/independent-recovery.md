# Independent YC codec recovery attempt — 27 October 2026

Status: exact decoder NOT recovered. Offline investigation only; no camera access, no image presented as a verified decode, and revision2.9 unchanged/unflashed.

## New results

The supplied reconstruction is not bit-complete under its own proposed stream routing. I independently instrumented the actual decoder, tracking its final consumed bit rather than merely counting generated pixels. Across ten saved packets,34279 blocks have W4=W5=0, isolating both candidate streams from one another in those middle words. On29163of those blocks (85.08%), the luma parser stops while nonzero bits remain in its isolated stream. Chroma does so on14604blocks (42.60%). Only761blocks have both56luma residual tokens and an all-zero tail;896meet the corresponding64chroma-token criterion. This is not an exact decode of all supplied data. An unidentified trailer could theoretically exist, but its syntax/meaning would need to be established rather than discarded.

The shortest isolated candidate chroma stream contains57bits through its last1, with19one bits. Under the report's proposed unary0^z1 representation, even64zero-valued sample tokens need64one-bit terminators, before any headers/anchors. Therefore the report's64-sample pure-unary model does not fit that block. A different coding alphabet, run representation, sample count, routing or header interpretation is necessary. This does not independently prove which candidate is correct.

I wrote new searches for Rice, Exp-Golomb, sign-magnitude variants, interleaved prefix codes and fixed initial samples. The fixed-offset searches did not yield an all-stream match. Then a compiled C search tested21952groupwise variants: eight groups of eight coefficients, reversed/direct2-bit header ordering,343maps for three header symbols with the fourth assignedk0, first sample coded or8/10/12raw bits, both unary polarities, optional sign bits and Rice/Exp-Golomb suffix lengths. On384isolated blocks, the best model fit the stream end plus at most8zero bits in125cases (32.55%), not384. It is rejected as a universal parser. These are bounded candidate searches, not proof that Rice-like coding, transforms or adaptive coding are absent. The presumed stream routes and64-coefficient count may themselves be wrong. A search over absolute-anchor candidates also produced no validated winner; continuity by itself can reward outliers and cannot establish a codebook.

## Firmware progress

The original bit-depth name mapper at0x63a06dfc was executed directly in Unicorn. It maps0->DEPTH_8,1->DEPTH_10,2->DEPTH_12,3->DEPTH_14,4->DEPTH_UNKNOWN; larger tested inputs returnundefined. A codec diagnostic call at0x63671d2a uses this mapper for its logged bit_depth field. This identifies that codec enum, NOT the captured allocation's live depth and NOT yet a proved identity with the SSYC yc_bit_depth enum. Do not interpret a live metadata value using this table until that bridge is verified.

A separate firmware Stage_Decomp.cpp path was traced:0x638ef968calls acquire0x63b31fec,0x638efad4calls start0x63b3218c, and0x638efb4ecalls release0x63b32078. The driver works through native resource/channel setup and parameter structures, with14-bit threshold fields in nearby construction. No pixel bit-reader or identified YC codebook was recovered from it. This may be a RAW-stage decompressor; no evidence yet connects it to VEF0x295. It must not be invoked on YC data just because its name includesDECOMP.

The earlier SDF/VEF paths inspected still establish metadata, compression selection and geometric alignment, not the entropy alphabet. The additional firmware flat-pattern scan found many sparse data records but no confirmed compressed-black reference packet. Black-frame helper routines checked so far dispatch subsystem operations rather than exposing a standalone CPU encoder.

## Public research leads (unconfirmed matches)

Sony's [Virtually lossless video data compression](https://patents.google.com/patent/US20090161753A1/en) describes internal block compression with padding and separately controlled luma/chroma coding. It is a useful architectural lead, but no evidence links its particular algorithm to this payload. [Image block coding based on pixel-domain pre-processing operations](https://patents.google.com/patent/US10893272B2/en) gives broader transform/predictive alternatives; it likewise does not identify the camera's codec. No patent was treated as a recovered hardware specification.

## What this changes

Do not promote the existing color reconstruction to a working pixel decoder or port its heuristic scales into the camera patch. More bytes alone will not fix an incorrect entropy parser, although the full allocation and matching descriptor remain valuable. The next discriminating evidence is either a native compression/decompression specification or independent known-content captures that constrain header, anchor, coefficient count and termination together. Live metadata would settle geometry/depth flags but would not by itself specify the entropy code.

## Reproduce

work/yc-codec-recovery/check_bit_accounting.py instruments only extracted functions (no external top-level image writes). search_anchor.py, search_stream.py and search_stream_sign.py implement the independent candidate families. Compile search_groups.c with host GCC and run against zve10-vef295-snapshot.bin for the21952model sweep. enum_strings.py executes the original RTOS mappings. decomp_xrefs.py traces PC-relative diagnostic strings. Matching JSON/log/disassembly evidence is in this folder. All saved input captures remain unchanged.
