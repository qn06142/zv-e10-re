# Verified YC source components

These helpers recover native metadata/message layouts. They do not acquire a live frame, establish pixel format or register a Sony source backend. Last working hardware output remains permanent 2.4p synthetic bars/counters.

- `sony_yc_metadata.h/.c`: 31 fields verified against actual Sony getter execution in `dataflowInfraFramework.so` and `libObj.so`, plus bounded resolution of one already-owned DMM span. Also provides verified decoders for Category 1 (`sony_yc_state_decode`, 6 bytes) and Category 0x11 (`sony_yc_multiple_segment_decode`, 288 bytes), along with segment slice extraction (`sony_yc_segment_extract_image_size`, matches RTOS `0x63cebf24`) and dual-strip reconstruction (`sony_yc_segment_merge_image_size`, matches RTOS `0x63cec0d8`).
- `sony_yc_pin_wire.h/.c`: native 52-byte SEND decoder and 44-byte COMPLETE encoder. Keep producer/input property order, per-pin completion order and mapping lifetime. SEND_WITH_DATA is unsupported.
- `sony_yc_sds.h/.c`: bounded version 1 SSYC/ETRY lookup of Category 0 (`ImageSizeInfo`), Category 1 (`YcStateInfo`), and Category 0x11 (`MultipleSegmentImageInfo`); no Sony C++ object calls, I/O or ownership operations.
- `evidence/`: original-code execution reports, fixtures, input hashes, verification outputs, and disassembly with source labels covering:
  - VDF DMM IPC commands: Command 1 (alloc), Command 2 (share), Command 4 (immediate free), Command 5 (open handle mapping), Command 6 (close handle mapping), Command 13 (delayed sync free).
  - VDF ownership manager vtable `0x645852c8` and logging wrapper `0x64585300` across all 18 call sites.
  - Pin completion and frame release handler `VDF::VdfInputReleasePinAndMem::Execute` (`0x63728000..0x6372889c`).
  - Multi-segment geometry split/merge helpers (`0x63cebf24`, `0x63cebfbe`, `0x63cec0d8`).

Full findings: [source recovery](../../../../docs/uvc_yc_source_recovery_20261025.md). Ready-to-paste continuation prompt: [next agent](../../../../docs/90-session/YC_NEXT_AGENT_PROMPT.md).

From `C:/Users/qn061/Documents/Codex/2026-10-22/chec` or `D:/02_Development_And_Projects/pmca-re`, using `D:/02_Development_And_Projects/pmca-re/.venv/Scripts/python.exe -B`, run:
- `verify_pin_protocol.py`: verifies native SEND/COMPLETE framing against Sony `SendComp`.
- `verify_sds_reader.py`: verifies bounded SSYC container traversal for Category 0 and Category 1 against Sony SDK constructors.
- `verify_individual_getters.py`: executes all 31 Sony SDK scalar getters in `dataflowInfraFramework.so`.
- `verify_metadata_decoder.py`: compiles `sony_yc_metadata.c` for Cortex-A5 and verifies all 31 fields, truncations, and DMM span resolution in Unicorn.
- `verify_vdf_metadata_builder.py`: executes the genuine RTOS VDF metadata builder `0x6374ae88` across all 4 geometry slots.
- `verify_multi_segment.py`: compiles multi-segment helpers for Cortex-A5 and verifies segment extraction and dual-strip reconstruction against actual Sony RTOS code (`0x63cebf24` and `0x63cec0d8`).

Emulation tests validate recovered code paths; they are not hardware webcam tests.


26 October continuation: [native640x480 source findings](../../../../docs/uvc_yc_live_source_20261026.md). Run verify_preview_geometry.py for seven original-code table selections with no external stubs, and verify_preview_update.py for five native changeSSYCData cases (message accessor and fixture mapping intercepted). The latter does not validate address translation. Evidence is in evidence/yc-live-20261026. Neither test acquires live pixels. The previous universal DMA-alignment and18-entry geometry claims are superseded.
