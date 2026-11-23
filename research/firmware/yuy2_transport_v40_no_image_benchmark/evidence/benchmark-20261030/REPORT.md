# Revision4.0 benchmark: timing evidence recovered

30 October2026. Camera remains4.0. User reports crash when stream ended, then returned camera in MSC. No new firmware, reboot or log deletion in this collection. Service closed job004 WORKBENCH_CLOSED/Done.

## Measured results

| Measurement | Result |
|---|---|
| Complete host frames |15, no trailing bytes |
| Distinct payload SHA256 hashes |15 |
| Received payload bytes |9,216,000 |
| First-to-last host receipt span |5.9442842seconds |
| Host receipt cadence |2.3552037fps, excluding initial device open |
| Host interarrival median / mean |400.581ms /424.592ms |
| Host interarrival min / max |1.498ms /765.609ms; delivery can be buffered/bursty |
| Camera submission1->2 |425.151ms |
| Camera submission2->3 |445.496ms |
| Early camera submission rate |2.2971422fps over two intervals |
| Capture process wall time |9.7685seconds |
| Advertised/requested rate |60fps ceiling, not observed throughput |

BENCH_USB timestamps are112594041,113019192,113464688microseconds from camera CLOCK_MONOTONIC, after successful submissions. These prove slow camera-side submission cadence; it is not solely a slow OBS preview. The intervals include source availability, DMM/metadata processing, resizing, copy, hardware/host backpressure and submission overhead. They do NOT isolate SDF time or identify a single bottleneck. Only the first3timestamp records persisted: next periodic checkpoint would be frame30, beyond this host capture. Runtime HOST_WAIT/HOST_RESUMED messages show intermittent EBUSY during frames4..16 but have no durations. Host receipt rate is not sensor exposure fps or proof of unbuffered camera transport.

FFmpeg returned0but logged "Error during demuxing: I/O error" and ended after15frames, not the requested8seconds of media. This is NOT a clean sustained benchmark. User reported camera crash at stream end; fault cause/order remains unproved. Do not infer success from exit code0. Media timestamps advanced about100ms/frame while format metadata advertised60fps; timestamp generation requires separate audit and must not be mistaken for measured wall-clock throughput.

## Missing measurements and why

vga.log contains ONLY MAPS_READ and QUEUES (79B). New4.0backend counters were deliberately buffered and deferred to stop/fault to reduce benchmark flash I/O. The crash/restart lost those RAM counters before a flush, so BENCH_LOOKUP/BENCH_SDF/BENCH_FINAL/BENCH_NO_IMAGE timings were NOT recovered. No no-image branch hit count, clean disconnect, resize timing or cleanup success is proved by this run. This telemetry design limits crash diagnosis; next instrumentation must persist small periodic stage summaries from a separate logger outside hot hardware/ownership locks, or another retained channel. Do not invent values from total frame time or saved host hashes.

No rejected-source.yc38, input/destination SDS or native-first dump exists for this run. No persistent STOP_ENTER/FINISH_ENTER message identifies a shutdown location. Absence is not a proved fault PC: frontend log writes are not fsynced, and a crash can lose recent writes. Current dmesg is post-restart and has no identified panic/oops/fault; binary system logs remain preserved without claiming full decoding. ThreadMonitor.bin is0B.

## Preservation and state

Fifteen data files6,212,377B plus1303B manifest downloaded and camera-MD5 verified. Local logs .local/outputs/vga-v40/benchmark-first-01/logs/. Initial collection uptime93.64s, boot1ddd6c5e-c953-41f2-851c-439b3247407f, ssboot=idle, original logger01.00.000. Camera originals retained. /usrread-only, exact4.0producer6fbc0edeab4895fbc81fd690e84a5810/wrappercef5b31d4abfb2374a8196e3cc6b904f/kernel388799d95bbb524ca581c66b077b6dc2persist; stock common/original logger unchanged. Free /usr10015744B,/log345440256B,/tmp5242880B;4096B/tmp write/readback passed.

First real frame first-frame.yuy2 was decoded unchanged to first-frame.png and visually inspected: recognizable scene with plausible colors. Only this first frame's bytes were retained; remaining frames have receipt timestamps/hashes. Distinct hashes alone do not establish sensor freshness. README headline remains unchanged.

Next: improve crash-resilient timing observability, then measure source/DMM/SDF/copy/USB-completion stages separately. Preserve hardware fences; no artificial timed sleeps remain in our4.0module, but native driver/thread scheduling and synchronous calls are not yet timed. Investigate shutdown separately before claiming stability. No new patch or further trial queued.
