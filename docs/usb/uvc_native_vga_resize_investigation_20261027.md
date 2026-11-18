# Native VGA and Sony resize path — 27 October 2026

Offline investigation only. No camera access, new installation, RTOS table edit or live VGA success in this investigation. Installed revision remains 2.9. Evidence is in the adjacent repository evidence directory; workspace originals are `outputs/yc-vga-test/` and `outputs/yc-codec-audit/vga-*.txt`.

## Native VGA configuration

The existing VEF table at RTOS 0x645b580c has 56-byte records. Record 5 at 0x645b5924 sets all input/valid/canvas dimensions to 640x480, unit type 0x295, compression marker 0. Original metadata builder 0x6374cdd4 maps this to yc_compress=0. It still writes strip_width=64 unconditionally; this field does not prove compressed packet size. Earlier original-instruction lookup/builder verifications already cover this record. This is configuration evidence, not evidence that the camera currently runs this mode. Current UVC 640x480 describes our transport envelope, not its native source configuration.

## Actual Sony resize2VGA implementation found

In dumped `libObj.so`, 0x19fd94..0x19ffb4 prints `SequencePinDeliverStartArtfilterCmd::resize2VGA()`. It:

1. Allocates two paired SDS/image work buffers using helper 0x206c56 with image unit type 0x220.
2. Sets width 640 and chooses height by aspect: aspect values 1/2/3 map to 426/360/640; other values use 480. Thus its VGA name alone does NOT establish 640x480 for every invocation.
3. Sets record and valid sizes, zeroes valid/target offsets, and stores image metadata for both outputs through 0xe49160.
4. Resizes source reference `this+0x88` into the first work buffer via helper 0x19fc88.

Allocation helper 0x206b58 allocates SDS unit type **0x000e0b00**, then image unit type supplied by its caller (0x220 here). Helper 0x206aec calls DmmCh::allocNew; the returned MEMORY_SET has u16 handle at +0, u32 unit type at +4, allocation address/size at +8/+12. The +4 field is NOT a physical address or data_site. Helper 0x206bf4 creates YC SDS metadata with 0xe490a4, attaches image handle/type with 0xe488d2, stores entries with 0xe493ac and checks its validity with 0xe493e8. `YcSdsAcsr` metadata structure is at object+0x124; image entry stores handle/type separately from the metadata allocation.

This provides a concrete existing paired allocation/metadata route. Its 0x220 destination is a different route from selecting VEF record 5/type0x295. Do not conflate the two or assume 0x220 can be shared as the existing VEF source.

## SDK request layout executed, not guessed

Two actual libObj callers, 0x18a58c and 0x19fc88, call libBizFw SdfCh::resizeRotate. Six Unicorn fixtures executed their original instructions with three distinct source/destination references each; original SDK wrapper 0x369b4 also executed. Logging, SdfCh lifetime in the caller, and hardware send/receive are mocked. Full 68-byte commands match independently constructed expectations.

SDK request fields: +0=0x2000, +2=3, +4=68, +6=0, +8=7; +0xa..+0x12 repeat low16 private queue. Body: source unit type u32+0x18, source handle u16+0x1c, destination unit type u32+0x38, destination handle u16+0x3c; byte+0x25=1 in both actual caller recipes. Other body bytes are zero in these callers. Their requester ID is 0x35. Exact meanings of every zero/flag remain to be traced.

The references are to SDS metadata containing the actual pixel attachment, not a bare existing VEF pixel allocation. Original RTOS metadata reader 0x636ba47c checks **SSYC** (literal 0x63f39c58), locates metadata, then converts its image entry through 0x63ca27f8. Merely placing our 0x295 image handle into this command is insufficient.

The inspected RTOS ApiResizeRotate parser 0x63cade3a copies 124 bytes and accesses source/destination references at +0x34/+0x54. This differs from the 68-byte Linux SDK layout. The translation/dispatch between these layouts has not been established. Use the SDK wrapper rather than issuing this compact request directly to a guessed RTOS queue. The SDK synchronous wrapper waits indefinitely for ACK/CMP; a live test needs bounded asynchronous ownership handling, not this call on the camera UI or stream worker.

## Buffer-size arithmetic verified in original RTOS code

Function 0x63ca47b8 resolves metadata and passes canvas_width * canvas_height * (yc_compress==1 ? 1 : 2) to 0x63ca46ea. Four original-instruction fixtures verify:

| Canvas | Compression | Requested bytes |
| --- | --- | --- |
| 640x480 | 0 | 614400 |
| 640x480 | 1 | 307200 |
| 1920x1080 | 0 | 4147200 |
| 1920x1080 | 1 | 2073600 |

Metadata reading and actual capacity operation are mocked; this proves arithmetic/control flow, not pixel packing, bit depth, successful hardware resizing, or codec acceptance. HD compression-off requires more than our existing USB output allocation capacity 0x320000 (3276800). Do not flip a global compression flag and reuse the old allocation.

## Remaining work before a live uncompressed test

Recover the actual source SSYC metadata/reference belonging to the selected native image; trace paired SDS/image allocation and release fully; derive destination metadata from Sony's initializer and VGA recipe; establish accepted compressed-input/uncompressed-output policy and channel routing. Verify completion and cancellation before reading/freeing a destination. A copied/pinned allocation does not by itself promise a coherent frame.

Prefer a bounded, one-shot resize into an owned destination and read it back through existing transport before changing continuous streaming. Preserve source refs until hardware completion. Independently verify output dimensions/compression/packing from returned metadata and bytes. No guessed global VEF/RTOS edits.

Before another live test, clear stale runtime state with a fresh boot: after the last 2.9 stop, the retained USB output handle/mapping was absent from the DMM listing. That unresolved reuse issue is independent of the new VGA investigation. Follow the regular archive/hash-verify/clear procedure for known logs and captures, preserve system /tmp files, and verify free space.

## Reproduce

Use repository .venv Python (Capstone, Unicorn, pyelftools). From the original workspace run `work/yc-vga-test/verify_resize_request.py` and `verify_capacity_check.py`. Ten original-instruction fixtures passed in total. Supporting caller/parent/allocation/attachment extraction scripts and annotated disassemblies are preserved. `resize-request-example-NOT-FOR-DEVICE.bin` contains synthetic fixture handles only and must never be sent to hardware.
