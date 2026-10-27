LATEST VERIFIED PROVENANCE ADDENDUM — 26 October 2026

The source has now been traced beyond a coincidental configuration-table ID:
Sony's VEF producer reads table-record +0x28, writes it to the YC
ImageSizeInfo.unit_type field, passes that same value to its native RDV DMM
allocator, and attaches the returned allocation handle as ImageSizeInfo's
unit_handle. For the real selected records that value is 0x295. This establishes
a video/YC IMAGE-ATTACHMENT allocation family, not an arbitrary workspace or
an address selected merely because its size looked like an image.

Exact code path in the camera-matching RTOS firmware:
- 0x6374cdd8 / 0x6374cde0: record +0x28 -> metadata unit_type (+0x04).
- 0x6374d08e / 0x6374d09c / 0x6374d0a2: record +0x28 -> allocator argument r0
  -> call 0x637545ec.
- 0x6375462a / 0x6375463c: native allocator writes that type into request +0x04
  and sets command 12 (0x0c), routed to DMM queue 0x0061003c.
- 0x63754662 / 0x63754666: allocator response handle -> native allocation record.
- 0x6374d0ce / 0x6374d0d0: that handle -> ImageSizeInfo.unit_handle (+0x08).

These ORIGINAL RTOS instructions were executed in Unicorn, not reimplemented
as a guessed structure. OSAL messaging/kernel allocation replies and virtual
owner getters were mocked. Three real geometry records passed; a fourth taint
control changed the record's type and mock returned handle, and BOTH propagated
to the descriptor and allocation request as expected. Relevant code and table
regions are identical in the stock dump and the exact patched firmware image
whose MD5 matches the camera: 90096db2c76148f4f9db5d104e5c608c.

DECODING CLUES FROM THE ORIGINAL METADATA-BUILDER CODE
Chosen geometry   unit_type   yc_compress   strip_width
1920 x 1080       0x295       1             64
1280 x 720        0x295       1             64
 640 x 480        0x295       0             64

All three tested paths also set:
unit_data_offset=0, data_site=0, iib_number=0,
data_transfer=0, data_placement=1, data_content=2, data_scan=1.
Canvas, valid and target sizes follow the chosen table record. The numeric
placement/content codes are native enums; their pixel-layout meanings have NOT
been established here. strip_width=64 is the native field value, not proof of
a particular byte stride or tile layout. yc_compress distinguishes the HD
records from the VGA record; the actual compression codec remains unidentified.
The exercised builder does not assign yc_bit_depth, so no bit depth is proven.

LIMIT: THIS IS NOT LIVE METADATA FOR THE SUPPLIED PACKET
The same unit type is reused across geometries and compression settings. We
did NOT capture the live ImageSizeInfo corresponding to this exact packet, so
we cannot identify which of the above configurations was active from these
checks alone. Allocation capacity is not that missing metadata. The role of
the buffer family is verified; exact plane/geometry/packing and a complete,
completed image are still unverified. The file is still only the first 614400
bytes of the native allocation. The binary and its SHA-256 are unchanged.

Verification scripts/reports, if the shared workspace is available:
 work/native-dmm-v28/verify_provenance.py
 outputs/native-dmm-v28/provenance/vef295-allocation-metadata-verification.json
 outputs/native-dmm-v28/provenance/installed-firmware-region-verification.json

-----------------------------------------------------------------------
ORIGINAL CAPTURE HANDOFF (retained below)
-----------------------------------------------------------------------

