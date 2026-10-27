# Revision2.6 raw-byte diagnostic transport

Built offline; not installed; no real Sony source backend is supplied yet. Permanent2.4p remains the last camera-tested transport. This recipe deliberately removes pixel-format interpretation as a prerequisite for capturing bytes.

## Payload behavior

The USB descriptors remain640x480/YUY2/10fps with614400 bytes per frame. `raw_live_fill_opaque` copies exactly614400 bytes from an acquired source's plane0 readable span, starting at configurable byte offset0 by default. It ignores source format, color flags, width/height and stride; it does not interleave planes, crop, scale, convert, draw bars, overlay a counter or append metadata. This makes YUY2 the transport label, not a claim about source byte packing. Sources smaller than the window fail; larger sources provide one contiguous window. Multiple physical spans are not concatenated.

`yuy2_live_bind(ops,opaque)` binds the existing callback interface before streaming. `yuy2_raw_set_offset(offset)` selects the window before streaming. The source must still provide a real stable reference plus physical span/capacity and implement bounded acquire/release/map/unmap. A pointer guessed from an old DMM address is not supplied. Default no-backend state logs RAW_SOURCE_ERROR and submits NO frames. Acquisition timeout, invalid span, map error or unresolved release also submits no frame. The original synthetic fallback has been removed from the worker, so bars cannot count as a successful diagnostic capture.

The worker retains the proven USB readiness gate: while the host is busy it neither acquires a source nor changes the owned USB staging allocation. Source bytes are copied to the exclusive USB staging unit0x276, source mappings and reference are released, and then that staging buffer is submitted. Failed cleanup retains the source reference and blocks further acquisition/submission until retried successfully. Known YUY2/NV16/NV12 converters remain in the inherited source tree but are not used by this worker.

## Build and verification

From a working directory where outputs can be written:

```
python -B build.py --repo D:/02_Development_And_Projects/pmca-re --output <candidate> --streaming-image <19461091c07aa6900829defb0060fcd6 baseline> --stream-base 0x0a61e000
python -B persistent_stream.py --input <same baseline> --output <candidate>/libInfraStreamingUsb.persistent.so
python -B verify_opaque.py --repo D:/02_Development_And_Projects/pmca-re --output <candidate> --streaming-image <candidate>/libInfraStreamingUsb.persistent.so --stream-base 0x0a61e000
python -B verify_persistent.py --stock <same baseline> --candidate <candidate>/libInfraStreamingUsb.persistent.so --module <candidate>/yuy2_640_v26raw.so
python -B verify_isa.py --module <candidate>/yuy2_640_v26raw.so
```

The compiler is C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe. The build inherits obsolete RAM helper artifacts; do not execute those against a camera or replay their example bases. No installer is provided. Use the existing proven2.3 kernel when a real source is ready and deployment is authorized. Do not replace permanent2.4p with this unbound diagnostic module merely to obtain bars: it intentionally will not produce any.

13 compiled ARM integration cases pass, including byte-identical614400-byte output with UNKNOWN format, flags0, stride0 and foreign dimensions; unaligned window offsets; USB backpressure; bounds/overlap/wrap rejection; timeout; retained-reference recovery; no backend; no synthetic fallback. Hardware and source callbacks in these tests are fixtures, not a Sony acquisition implementation. The32 inherited lease/conversion cases and11 PIC/ELF checks also pass. ISA audit finds no NEON in mapped module code regions; external libc is outside the audit.

## Preserve bytes on the PC

`capture_opaque.py --output <new-directory>` uses FFmpeg DirectShow with input640x480/YUY2/10fps and OUTPUT `-c:v copy -f rawvideo`: no decode/re-encode, pixel conversion or image filtering. It saves capture.bin, ffmpeg.log, capture.json and each complete614400-byte packet as frame-NNNN.bin, with SHA256 and trailing-byte accounting. Default10 frames,30-second timeout; it refuses an existing output directory. `--dry-run` prints the command without touching hardware; `--existing <file>` splits an existing capture offline. The splitter was checked against two exact fixture packets plus a seven-byte partial tail. It does not establish that received bytes came from a sensor.

Actual local build: C:/Users/qn061/Documents/Codex/2026-10-22/chec/outputs/yuy2-v26raw/candidate/. Implementing and binding the real camera-buffer source remains required before any real byte capture is possible. Source format is intentionally no longer required at that stage.
