# Revision 2.5 — lease-based live-source integration candidate

**Offline candidate; not installed; Sony live-source backend not yet bound.**
The camera retains the tested permanent revision 2.4p. This candidate preserves its kernel/USB lifecycle and adds a complete bounded adapter-driven acquisition, validation, readonly mapping, scalar conversion and release path. It does not turn unverified findings into camera IPC commands. With no adapter registered, output remains the existing bars/counter pattern.

`yuy2_live_bind(const raw_live_ops *, void *)` registers an in-process backend while streaming is inactive. Registration is rejected while a manager or uncertain USB DMA is retained. This internal callback ABI is defined in `raw_live_source.h`; it is not a Sony ABI. The backend must acquire a completed, stable frame lease, supply actual physical plane addresses/strides/bounds and explicit YUY2/NV16/NV12 plus BT.601 limited-range format, and return the lease on successful release. Its acquire timeout is capped at 10 ms and must be honored by the backend. Missing or unverified metadata is rejected. No automatic symbol resolution or fabricated lease-return call is supplied.

The worker waits for USB source readiness before any acquisition or mutation. It copies into exclusive unit 0x276, unmaps source planes, releases the upstream lease, then submits that owned USB source. Failed unmap/release retains ownership and blocks further acquisition until retry succeeds. Explicit stop/finish retry upstream cleanup after the original worker stop. Source errors restore the entire synthetic image, including after a live frame. Host EBUSY preserves pixels and performs no upstream acquisition. Live pixels receive no synthetic counter overlay.

Build/verification commands from this recipe directory:

```powershell
python -B build.py --repo <repo> --output <out> --streaming-image <19461091-baseline> --stream-base 0x0a61e000
python -B persistent_stream.py --input <19461091-baseline> --output <out>/libInfraStreamingUsb.persistent.so
python -B verify.py --repo <repo> --output <out> --streaming-image <out>/libInfraStreamingUsb.persistent.so --stream-base 0x0a61e000
python -B verify_persistent.py --stock <19461091-baseline> --candidate <out>/libInfraStreamingUsb.persistent.so --module <out>/yuy2_640_v25.so
python -B verify_isa.py --module <out>/yuy2_640_v25.so
```

`verify_live_integration.py` with the same arguments as verify.py runs only the five new integration cases. Native ownership/error tests live in `../raw_frame_source/test_raw_live_source.py`. Existing kernel recipe is unchanged; use the proven revision 2.3 kernel. The compiler now explicitly targets Cortex-A5, soft-float ABI, VFPv4-D16 allowance, and disabled loop/SLP vectorization. Instruction audit checks actual ARM/Thumb code intervals and excludes compiler-marked literal pools. External libc implementation is outside that scan.

Legacy RAM bootstrap/helper files emitted by build.py are not used for persistent activation. No new installer is supplied: deploying this candidate without a verified backend would still produce synthetic frames. See [implementation report](../../../docs/uvc_live_frame_implementation.md) for findings and missing camera binding.
