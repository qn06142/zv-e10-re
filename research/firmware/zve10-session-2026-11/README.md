# ZV-E10 Bayer, USB and recovery findings

The session established candidate sensor modes and reproduced firmware control-path failures offline. A continuous 24 fps Bayer buffer and a working SuperSpeed patch remain unverified. The camera was unavailable for the final Bayer investigations.

| Area | Finding | Evidence |
| --- | --- | --- |
| Sensor cadence | Modes 5 and 7 use uncompressed 12-bit packet configuration and calculate nominal rates of 59.94 and 47.952 fps. Modes 1f and b5 calculate 23.976 fps with compression type 3. Packet format and nominal cadence establish candidates. | [Movie Bayer report](movie-bayer-audit/REPORT.md), [native parameters](movie-bayer-audit/movie-native-param-results.json) |
| Bayer route | The fast sensor path configures MIPI Tx. The native AIF diagnostic maps logical 7/8 to read channels R0/R1 and 5/6 to write channels W0/W1. Across 186 drive lookups, all 104 AIF geometry slots in the 13 returned headers are null. | [Geometry and routing](movie-bayer-audit/RAW-GEOMETRY-FINDINGS.md), [catalog results](movie-bayer-audit/aif-geometry-catalog-results.json) |
| W0 configuration | With supplied geometry, native setup and start program a destination and arm W0. Packed encoding 3 at width 1996 programs 124 formatter blocks and 125 DMA blocks per line. The capacity check runs after register writes and accepts some descriptors exceeding the supplied span. | [Paired fast-mode traces](movie-bayer-audit/fast-w0-route-results.json), [geometry tests](movie-bayer-audit/raw-geometry-offset-results.json) |
| W0 completion and ownership | Stock completion fires with W0 held busy in the emulator. Release with a dynamic W0 flag leaks its reservation. Including W0 in the default flags clears the reservation and permits a competing acquisition while busy is still asserted in the model. | [Completion and teardown](movie-bayer-audit/RAW-GEOMETRY-FINDINGS.md) |
| DFE images | The normal loader selects the embedded ARM image. The external image path is a fallback. The system archive supplies a separate bootstrap. Native tests cover the parameter ABI, register programming and different DMA error/timeout contracts in the two images. | [DFE image audit](movie-bayer-audit/DFE-IMAGE-FINDINGS.md) |
| Recording configuration | The `+0xf9` producer quantizes an input and its getter forwards the value to configuration `+0x36` before later gates. This establishes the field provenance, with no demonstrated connection to ADC precision or per-frame metadata. | [Quantizer verifier](producer-depth-audit/verify_config_quantizer.py) |
| USB and YUY2 | Fault injection exposes speed-state and registration failure cases. The 1080p YUY2 containment candidate uses USB High-Speed at 5 fps and preserves the stock registration path. Its frontend, chunking, capacity and DMA fence checks use mocked services. | [Speed results](usb-speed-audit/results.txt), [containment notes](uvc-containment/README.md), [teardown verifier](uvc-teardown/verify.py) |
| Pico diagnostics | The v16 audit identifies GP28 TX, GP27 reset, 48 kbaud and a 10 µs reset pulse. The connected carrier test recorded zero edges. With the camera unplugged and GP28's weak pull-up enabled, the Pico recorded 64 edges at a median 125 µs spacing. This verifies the local 4 kHz carrier. Reset delivery and camera execution remain unconfirmed. | [Pico audit](pico-python/AUDIT.md), [diagnostic](pico-python/diagnose_link.py) |

The remaining Bayer work is to establish the fast-mode producer's route into a writable buffer and verify a frame boundary and ownership fence. The W0 fixture geometry represents a test input. The native packet stream, Bayer order and physical DMA behavior are outside the RAM-backed model.

## Reproduction and provenance

The Bayer verifiers take the repository root as a positional argument and use local firmware inputs under `dumps/`. The native ARM/Thumb harness requires Unicorn and Capstone. Use the exact `av-cam.bin` identified by the movie audit. Some probes additionally require archived files or build inputs specified in their sources. The derived result JSON files are beside their verifiers.

```sh
python research/firmware/zve10-session-2026-11/movie-bayer-audit/verify_fast_w0_route.py .
```

The publication preserves notes, authored verifier and patch sources, results, and input hashes. Long local disassembly listings, firmware binaries, compiled replacement objects, and device logs stay local under the repository's provenance rules. Historical file references in the reports refer to those original local artifacts. The Pico diagnostic is an addition to the v16 audit host tools and expects their `pico_link.py` module. The Pico manifest records the historical bundle hashes.
