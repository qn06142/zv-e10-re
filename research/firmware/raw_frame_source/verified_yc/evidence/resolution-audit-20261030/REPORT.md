# Native frame resolution audit and recovered 3.9 logs

30 October2026. User requested log recovery and a deterministic way to resolve frame identities before another patch. Camera remains3.9; no new flash, reboot, process-memory write, or log clearing. Service closed job003 WORKBENCH_CLOSED/Done.

## Recovered evidence

Sixteen data files6,398,590B plus1363B camera-MD5 manifest downloaded and verified. Local .local/outputs/vga-v39/capture-first-01/logs/. Collection boot ID620e50d5-5653-42e2-8dee-b9f968f5db41, initial uptime125.49s, ssboot=idle. Original logger01.00.000; USB streaming kernel not currently loaded. Installed wrapper/module/kernel hashes remain exact3.9. Current free /tmp5242880B with4096B write/readback passed, /log345620480B, /usr10267648B. Original system-managed files preserved.

Appended vga.log contains4worker segments,49logged COMPLETE events,1529SEND events and10METADATA_SETTLED events. This is a lower bound on completed frames: bounded per-worker trace buffers can stop recording before runtime does. Runtime records at least66successful USB submissions across its runs; one run reaches SUBMITTED0x3c=60. Neither log has per-frame monotonic timestamps; exact fps, per-stage latency and correlation to each user-reported crash are unavailable. The earlier commentary's66resized frames conflated the USB submission lower bound with logged resize completions: use these separate counters. The OBS screenshot proves a recognizable image, not sustained rate/stability/bit-depth.

## Critical new distinction: metadata can have no pixel attachment

The exclusive8272B rejected-source.yc38 record belongs to the first saved rejection; later runs cannot overwrite it. SHA256e4ee15a700c0025e75c08dedede49441b426b3ba6f506ae05219180ba37574fb. EVENT_REJECTION_SAVED status0 confirms save. Final two4096B reads are identical. Native SSYC category0and1parse; category0x11absent. ImageAttach=0,type=2,handle=0, mask0x60. The preceding attempt masks were0x0e,0x1e,0x60: a changing/temporarily malformed descriptor settled into a parseable descriptor WITHOUT an attached image. Do not call that final snapshot malformed solely because it has no pixels, or assume type2's enum meaning without further evidence.

Original Sony RTOS getter0x63c60f76 ACCEPTS this exact final descriptor, as do original exported Linux C_DataflowInfra_StdData_YC::GetEntry_ImageSizeInfo and Entry_ImageSizeInfo::GetData_All. Both original platforms reject the old3.8malformed snapshot. Five RTOS cases execute original pixel Open0x63691ebc, Share0x63691f94, Close0x63692218 and Free0x63c868c0. The real3.9no-image descriptor generates ZERO pixel DMM operations. A valid attached reference generates5/2/6/4for its current pixel handle. Controlled attach0/nonzero-handle and attach1/zero-handle cases also skip pixel operations. Original pixel-open checks at0x63691eda..0x63691ee8 require a nonzero handle AND attachment; the release wrapper similarly checks both. Metadata Close6andFree4(mode2) still occur through separate original helpers. Tests invoke helpers individually with DMM/physical mapping/cache lookup mocked; this does not prove full asynchronous ownership or SendComp ordering.

3.9instead insists that every parsed SEND have type0x295/nonzero-handle, then quarantines the source when an image is absent. This is a demonstrated policy mismatch with the original helpers, and a concrete cause of one source-worker failure. It is NOT a proved cause of the camera reboot. It also does not explain the separate pixel Open refusal in segment3: metadata SEND0x1c6e led to pixel0x13ad; correlated Open reply0xfffb8005/native0xfdfb, no physical/capacity. Never map that failed reply, treat it as a good frame, or guess a replacement handle.

## Deterministic resolution contract

| Object | Authoritative resolver | Guard/lifetime |
|---|---|---|
| Exported methods | dlopen/dlsym by exact mangled symbol from Sony ELF | Exact library hash/prologue guards; retain loaded library |
| Hidden libObj methods currently used | Exact ELF-relative offset plus current loader mapping base | Mapping extent and16-byte instruction guards; this is address rebasing, not a frame-pool signature scan |
| Current SDS identity | Matched type0 SEND packet: class0x1000/op0x0102,len52; source/destination pin properties; type+0x28,handle+0x2c,offset+0x30 | Private native queue; validate endpoint/type/length; no historical handle reuse |
| SDS address/capacity | Correlated DMM Open5on that CURRENT SDS handle | Exact echoed command/handle/reply queue/status/site; use returned physical address and size, never pool guesses |
| Current image identity | Bounded stable SDS category0 / native GetEntry_ImageSizeInfo/GetData_All | Check image presence BEFORE asserting a pixel handle exists; keep metadata lifetime and coherence distinct |
| Pixel address/capacity | Correlated DMM Open5on current attached image handle | Require expected format/site/span and granted reference; Open/Share/Close/Free are separate operations |
| VGA destination | Native pair allocator plus original YC accessor, then DMM Open | Current allocation result and attachment, never nearby memory signatures |

Runtime3.9already follows the SEND->DMM->typed-metadata chain. It does NOT discover source frames by scanning /proc/udm pools or searching memory for SSYC/ETRY magic. The source-listing buffer is used to read /proc/self/maps for hidden library rebasing. Signature searches in saved diagnostic bytes are offline analysis only and must never promote guessed addresses to live handles. Original Linux getters offer an exported API for metadata resolution; retain bounded container validation before calling native getters on potentially damaged input.

## Next correction should be narrowly grounded

Add an explicit metadata/no-image outcome, separate from malformed metadata, valid attached pixels and uncertain DMM outcomes. For a stable, structurally valid descriptor matching observed ImageAttach0/handle0, do not invent/Open/Free a pixel reference or send SDF. Retain separate metadata bookkeeping and follow the independently verified Close/Free2and event completion sequence. Test no-image->valid-image transitions and stop/disconnect while no-image is pending. Do not turn all malformed metadata or pixel Open failures into this benign case. The RTOS helpers prove presence gating and isolated metadata cleanup; complete transfer-credit and SendComp ordering must remain independently checked before a deployment change.

Keep the pending-frame backpressure path from acquiring every unneeded pixel while a published copy waits; optimize only after establishing exact metadata/pixel credit handling. Add monotonic timing around SEND/Open/parse/SDF/publish/USB completion to distinguish slow stages; do not conclude1fpsis inherent from frame counts or remove all pacing blindly. Source FLAGS show yc_compress1 at1920x1080 and destination FLAGS yc_compress0 at640x480: the successful path uses native decompression/resizing into an uncompressed output. Color/gamma/bit-depth still need dedicated evidence.

No new binary built or flashed. README headline remains unchanged per user hold. Crash fault PC not identified from these files; current dmesg is post-restart evidence and system binary logs are preserved without pretending they were fully decoded.
