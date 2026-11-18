# Next major push: genuine 4K / 12-bit pipeline

27 October 2026. User paused camera testing after the VGA flash and requested this next direction. Continue offline; do not resume camera experiments automatically.

## Current state and findings

Revision3.0 experimental VGA is installed and survived reboot. Exact readbacks: producer98acd3ba3d6628e006fe51d88dda25dc; streaming library2a4c08511526f2b525c57a1d9bac9bad. /usr is read-only, normal error logging restored, recovery preserved, service workbench closed. No3.0 FFmpeg/OBS test occurred. Its live SDF acceptance, pixels/packing, source frame coherence and frame rate remain unknown. Leave the camera as installed; no rollback or further flash was requested by the pause.

Before flash, six logs (7642bytes) were archived/downloaded/hash-verified, rechecked and individually removed; system/tmp/fonts/tools were preserved. Guarded dependency-first installation and exact downloaded readbacks passed. A fresh post-install boot verified both files, recovery hashes and inactive cold maps. Evidence: ../../research/firmware/yuy2_transport_v30_vga/evidence/install-20261027/. The installer passed10 simulated failure/rollback cases. Reboot jobs lack a terminal completion marker because the terminal stopped during kernel restart; fresh postboot verification passed.

## Preserve the actual colour-bars control binaries

The proven colour-bars baseline is **2.4p**, not3.0. FFmpeg delivered ten exact frames on first capture and ten on same-session reopen; the user confirmed OBS worked. These are synthetic8-bit YUY2 values and counters, not a native high-bit-depth sensor signal or proof of sustained10fps. Source report: ../uvc_yuy2_patch_v24p.md.

A hash-verified reference bundle is preserved at ../../research/firmware/4k12bit_baseline_20261027/:

| Artifact | MD5 | Evidence status |
| --- | --- | --- |
| v24p-proven-bars/yuy2_640_v24p.so | 9181ef744955190d04728cf4ef7965c5 | Tested colour-bars producer |
| v24p-proven-bars/libInfraStreamingUsb.so | 5fde77e394572ebcf420f8941575f6c4 | Tested matching persistent gate |
| transport-kernel-v23/usbg_video.ko | c1cad400372e26eca729e4b9bc47a237 | Proven paired USB transport kernel |
| v30-experimental/yuy2_640_v30vga.so | 98acd3ba3d6628e006fe51d88dda25dc | Installed; live resize untested |
| v30-experimental/libInfraStreamingUsb.so | 2a4c08511526f2b525c57a1d9bac9bad | Installed matching persistent gate |

The bundle is an offline comparison/reference set, not an instruction to install all files or mix their dependencies. In the original workspace the proven files are outputs/yuy2-640-v24p/candidate/yuy2_640_v24p.so and libInfraStreamingUsb.persistent.so. The earlier similarly named non-persistent libInfraStreamingUsb.so is superseded.

## Next milestone

Use the VGA binaries, disassembly, metadata parsers and source as a known control to reconstruct the complete producer -> SSYC image attachment -> allocation -> image-processing -> sink path, then identify where an actual4K/12-bit source can be preserved. The major result should be a verified firmware path and a concrete guarded candidate, with any remaining camera validation stated explicitly. Do not scale the VGA descriptor and call that a4K/12-bit patch.

The useful new native call chain is:

- libObj resize2VGA0x19fd94 -> paired SDS/image allocator0x206c56 -> image unit0x220, SDS type0xe0b00.
- Sony geometry setter0xe48a10 and metadata store0xe49160 -> SdfCh::resizeRotate wrapper in libBizFw at0x369b4.
- SDK request has68bytes: source SDS type/handle+0x18/+0x1c, destination SDS type/handle+0x38/+0x3c. Existing caller byte+0x25=1. Do not guess meanings for other fields or send the compact SDK layout to a guessed RTOS queue; the inspected RTOS parser uses a different expanded layout.
- Native metadata resolver/capacity function0x63ca47b8, SSYC image reader0x636ba47c and metadata converter0x63ca27f8 link actual image metadata to hardware configurations.
- Metadata yc_compress+0x2f, strip_width+0x34 and yc_bit_depth+0x36 are verified field offsets. The separate RTOS log mapper0x63a06dfc maps0/1/2/3 to DEPTH_8/10/12/14, but equivalence to the SSYC bit-depth enum and current live pixel depth has NOT been established.

Inspected SDK hashes: libObj.so0b4be3fb599b539c69c782bd400dd8e9, libBizFw.so6416a5a6780bbe829eb30d85fc8e8dad. Preserve addresses as offsets/firmware VAs with their exact file hashes; never reuse a prior process base or frame physical address. See ../uvc_native_vga_resize_investigation_20261027.md and ../uvc_vga_v30_candidate_20261027.md for native evidence and implementation.

## Offline work sequence

1. Reproduce the known VGA caller/request/geometry/ownership fixtures. Compare2.4p transport with3.0 source replacement; identify the exact producer and sink boundaries. This keeps a working control while investigating another source.
2. Trace bit-depth selection from actual sensor/ISP configurations to buffer metadata, SDF conversion parameters and each consumer. Identify any fixed8-bit conversion/truncation before selecting an output. The resize SDF API's name is not proof of a sensor RAW tap. Promoting8-bit samples or relabelling metadata is not12-bit acquisition.
3. Trace a real4K recording/readout path and its complete allocation/stride/plane/ownership configuration. Separate genuine sensor readout, processed YC, resized preview, encoder input and recorded stream. Existing open-gate enums/profile strings alone do not verify full-height readout, an enabled codec profile or12-bit output on this camera.
4. Define and verify which12-bit signal is available: Bayer RAW, YUV420 or YUV422, packed or16-bit-container storage. Require matching source metadata/configuration and independent payload validation; nonzero low bits alone are not sufficient. Trace input precision and final encoded precision separately if internal recording is the sink.
5. Audit real DMM pool capacities/aliases, full spans, alignment, DMA and frame-completion/return semantics. Preserve source references through hardware completion and give consumers immutable metadata. Do not replace allocation limits or dimensions blindly, or equate a pinned allocation with a coherent completed frame.
6. Prepare the smallest offline-verified prototype: ideally one genuine high-bit-depth frame/bounded burst before continuous delivery. Reuse the established byte-preserving diagnostic framing or another explicit sink rather than pretending the VGA YUY2 envelope carries a directly viewable4K frame. A later authorized live test must archive/hash-verify/recheck/clear logs, use bounded capture, and preserve rollback.

## Correct payload arithmetic before choosing a sink

For UHD3840x2160, tightly packed, without padding, metadata, double buffering or protocol overhead:

| Assumed signal | Bytes/frame | Payload bytes/sec at24fps |
| --- | ---: | ---: |
| Bayer12-bit, one sample/pixel | 12441600 | 298598400 |
| YUV42012-bit, 1.5 samples/pixel | 18662400 | 447897600 |
| YUV42212-bit, 2 samples/pixel | 24883200 | 597196800 |

These are arithmetic requirements, not camera throughput measurements.16-bit storage containers increase the payload. The older~11.87MiB UHD figure corresponds to12-bit Bayer (or8-bit YUV420), not12-bit YUV420. For3240x2160, packed12-bit YUV420 is15746400bytes, about15.02MiB.

The current USB2 VGA transport is a control/diagnostic sink, not a demonstrated continuous4K/12-bit/24fps path. Treat native precision,4K geometry, internal encode/record support and sustained delivery as separate proofs. USB3 remains future work; do not silently change that earlier scope. Bounded full-frame captures/chunking can diagnose a source without proving continuous transport.

## Completion criteria for this next push

Produce an evidence-backed call/field/allocation map from an actual high-bit-depth source to its chosen sink, identify every precision-reducing stage, and prepare a guarded patch only where configuration and ownership are proved. Report the actual outcome: offline candidate, successfully captured native frame, measured sustained stream, or verified recorded bitstream. Do not relabel synthetic bars, an untested resize request, a compression flag or nominal metadata as a working4K/12-bit recording patch.
