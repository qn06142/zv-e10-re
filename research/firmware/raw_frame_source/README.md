# Raw frame conversion and lease pipeline

`raw_live_source.h/.c` implements the adapter-driven live-frame lease path used by the revision 2.5 producer candidate. It validates explicit format/geometry/plane spans, maps camera planes readonly, converts or copies, unmaps and releases, retaining failed cleanup for retry. `raw_live_fill` must run only after the USB destination is reusable. It does not identify or subscribe to a Sony camera producer by itself.

`raw_frame_source.c/.h` retain standalone scalar converters and the historical synthetic-only lifecycle API for compatibility. **The old `raw_frame_source_acquire` remains a synthetic-only helper; the candidate uses `raw_live_fill` instead.** `RAW_FRAME_CONVERSION_ONLY` builds just the conversion subset for the ARM module, without the old lifecycle/host simulator. Metadata accessor offsets are useful evidence; semantic enums and ownership claims in the older report are not a verified backend contract.

Run `python -B -m pytest research/firmware/raw_frame_source/` from the repo root. The new native C harness exercises 26 cases with fake leases/mappings, in addition to the inherited 16 conversion/layout tests. These tests do not acquire a real camera frame. See [implementation report](../../../docs/uvc_live_frame_implementation.md).
