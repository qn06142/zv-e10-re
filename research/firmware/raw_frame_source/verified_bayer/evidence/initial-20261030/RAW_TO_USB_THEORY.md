# One native Bayer frame into the existing USB framework

Status: evidence-backed architecture with explicit unresolved acquisition gates. This is not a flashable patch or proof that uncompressed Bayer is available in movie mode. Camera4.2unchanged; no restoration.

## Acquisition boundary

Do not call DUALREC_BAYER_acquire expecting pixels. Verified code reserves a processing resource, start resolves pre-existing buffers, then submits a command and waits for one matched0x41 response. Its caller immediately invokes release. The response producer and meaning remain unknown: it may report configuration/mailboxes, not image completion. The submitted parameter handles must not be called input/output RAW solely from their offsets.

First prototype should observe an existing native still/RAW transaction, rather than program sensor registers or manufacture a new mode. Trace the native RAW-buffer allocation, producer and consuming transaction into the exact frame-complete point. Obtain its current handle, resource type, offset, capacity, stride, geometry, format/depth controls and completion generation. Follow the real transfer identity; never search DRAM for plausible images or replay an old handle.

Observe the frame before its existing native release. Acquire an additional reference using the same resource subsystem's proven share/open mechanism, if supported; a share pins lifetime but does NOT guarantee the producer will not overwrite it. Prove content stability independently from the native producer/consumer handshake. Do not assume the YC SEND/SendComp mechanism applies to Bayer. If no extra ownership can be established, copying requires a proven synchronous completion-to-release window; do not sleep or wait for USB inside that window.

## Separate the snapshot from sensor ownership

Preallocate a private snapshot with checked capacity and non-overlap before acquiring a frame. Copy the exact completed byte span once while its content is stable, with the native cache/coherency operations demonstrated for that allocation. DMB alone does not clean/invalidate CPU caches. Then release every added reference with the matched native protocol and let the original transaction proceed. Do not redirect the camera's native release or retain a stale physical address.

A tightly packed6000x4000x12-bit example is36MB;14-bit is42MB,16-bit containers48MB, before padding. These are sizing examples, not verified camera layouts or available memory. Private snapshot allocation/mapping and timely copying remain gates. If no suitable snapshot exists, use native-owned storage/export facilities or a smaller demonstrated native RAW mode; do not extend a DMM pool by capacity alone.

## Carry bytes through USB without invoking SDF

Use the working small staging/source allocations and chunked transfer machinery, not the rejected full-HD conversion. Replace only the published-buffer source with the immutable snapshot. Do not convert Bayer to YUY2 or truncate it. First transport is a diagnostic byte carrier, not a normal-viewable RAW webcam.

For a host-compatible carrier, keep640x480YUY2 slots of614400 bytes. Each slot contains a64-byte binary record header plus up to614336 raw bytes, padding the rest. Header: magic8B; version u16; header-size u16; capture-id u32; total-bytes u32; offset u32; payload-bytes u32; chunk-index u32; chunk-count u32; payload-CRC32 u32; format-tag u32; width u32; height u32; stride u32; flags u32; reserved u32. Multi-byte fields little-endian. Format-tag0means unknown; flags identify first/last. True producer metadata is preserved separately, never inferred from the YUY2 carrier declaration.

Each carrier slot is one complete UVC frame: toggle FID per slot, EOF at its final packet. Reuse existing614400-byte source mapping, original staging allocations and DMA-completion fences. Publication remains immutable until completion, EBUSY retries the same offset, and uncertain DMA quarantines. Advance raw offset only on accepted carrier submission; host reconstruction detects gaps and CRC failures. No need to pretend a whole36MB RAW image is one4.1MB UVC frame or resize it to fit. Host restart must resume by capture-id/index or explicitly require a new transfer.

Host captures with FFmpeg rawvideo/stream-copy or a byte-preserving DirectShow reader: no scaling, pixel conversion, range normalization or image encoding. Host strips64-byte headers, reassembles by capture-id/offset, rejects gaps/overlap/conflicting duplicates, validates CRC and saves one .bin plus metadata .json. A known-byte software transport fixture must first demonstrate exact preservation through the chosen host capture path. A carrier image in OBS is meaningless; stop OBS for this test.

This carrier is an implementation proposal; existing firmware still advertises1080p and has a one-session-per-boot restriction. A new candidate must explicitly change its descriptor and source publication contract together, preserve native cleanup, and pass host byte-integrity tests. It has NOT been installed.

## Evidence required to call the result sensor RAW

Tie payload to a demonstrated sensor/DFE producer and live frame completion; establish packing/compression from actual producer settings, consumer parsing and payload. Bayer labels and nonzero low bits alone do not certify depth, CFA order, uncompressed data or movie-rate availability. Preserve original bytes even if compressed and label them accurately. Capture lens-covered and illuminated controls only after acquisition is proven, then decode on PC. First success criterion: one complete, independently reconstructable sensor-origin frame with documented ownership and no camera failure. Continuous video follows separately.

## Concrete next reverse-engineering targets

1. Trace native class5resource lookup and context handles+0x67de/+0x67e0/+0x67e2 back to allocation and DFE producer; assign actual buffer roles.
2. Trace the sender of response0x41, and any later pixel-done interrupt/event. Start wait currently proves only a response, not DMA completion.
3. Identify a completed native RAW transaction's transfer/release boundary and cache operations. Use that boundary for a bounded observer before writing capture code.
4. Validate snapshot capacity and copy lifetime; only then build RAW publication and640carrier transport, with no SDF calls.
