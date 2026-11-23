# Sensor Bayer path: offline first pass, 30 October 2026

Objective: acquire one genuine sensor Bayer frame, preserve native bit depth and packing, transfer for PC analysis, and eventually replace the failing YC/SDF path. No live commands, firmware changes, restoration, reboot or capture in this pass. Camera remains revision4.2. Existing USB chunk infrastructure is a possible sink, not a proved RAW transport.

## Verified against the exact firmware

av-cam.bin MD5 cdcae9d4fdbf66a33704a4c7564e346d, base0x635c6000. String references identify native DUALREC_BAYER acquire0x63b322a0, release0x63b32344 and start0x63b324d4. Actual caller0x638f2048 acquires,0x638f230a starts,0x638f2398 releases. Surrounding caller is a larger camera operation, not an independently proved webcam producer.

Acquire reserves resource class4 through0x63df188c. Optional claim/configuration occurs if request byte0 is nonzero; resource allocation follows via0x63b3120c. Allocation failure unwinds reservation with0x63df1872. Eight original-instruction acquire/release cases verify success, failed reservation, failed allocation, optional handle and release failure with resource callbacks mocked.

Start resolves existing buffer handles at parameter offsets+0x1a,+2,+0x18,+0x30,+0x40; optional+0x42 uses0xffff sentinel. Offsets+4,+8,+0xc,+0x10,+0x14 are added to the buffer at+2; offset+0x1c is added to buffer+0x1a. It checks address/geometry alignment and uses resource lookup before submission. One original-instruction fixture reaches the shared hardware-submission boundary with five mapped handles. It stops before executing hardware; fixture1920x1080 is not evidence of a supported sensor mode.

Release visits handles at+0x18,+0x1a,+0x30,+2,+0x40, and optional+0x42, then releases resource references and undoes class4 reservation. This lifecycle is not equivalent to the YC SEND/SendComp contract and must not be substituted blindly.

DFE_0_STORE_RAW is referenced from an enum/name table at0x645d145c (preceding numeric word4); this is NOT a callable capture address. DFE_SET_RAWB and ShareMem_StlRaw8 remain string leads. Raw8 in a name does not certify8-bit pixels. Likewise DUALREC_BAYER does not yet establish a continuous sensor output or an uncompressed Bayer representation.

## Still required before capture code

Trace source of the caller's parameter handles (notably camera context+0x67de,+0x67e0,+0x67e2) back to allocation and sensor routing. Identify which is producer input vs processing output and their capacities, bank and lifetime. Trace completion/mailbox semantics and expose only a completed frame, with a matched release path. Establish packing and precision from producer setup plus payload evidence; do not infer12/14-bit or RGGB from names. Prefer observing an existing native RAW transaction before issuing new sensor mode commands. Obtain one bounded frame before streaming performance work.

Earlier project notes called SDF a sensor-driver framework and presented RAW dimensions/precision/performance as established. The resizeRotate SDF path is not evidence of a sensor tap; those historical claims are not validated by this pass. No RAW frame or flashable RAW patch yet.

## Follow-up: handle resolution and submission boundary

Traced0x63b31b14: queries native resource lookup0x63970228 with class5, requires span field+8==1, translates address field+16 via0x63c48e0c(address,16), otherwise returns0xffffffff. Three original-instruction cases verify lookup failure, unsupported span kind and success. This is resource-handle resolution, not a scan for Bayer signatures.

Start tail0x63b32704..0x63b3274c copies parameter geometry into the resolved resource state and sets fixed0x80/0x80/1 fields. It constructs two additional state blocks, then invokes0x63df189e with operation4 and mailbox/result pointers. Returning from this call and immediately releasing in the native caller requires tracing that call's synchronization; do not assume a successful start means pixels are complete.

The caller's initial0x6390897c invocation opens an existing handle passed in r1 and reads/copies metadata; it does not by itself establish where sensor pixels are allocated. A separate conditional allocation uses unit0x1df in that helper. Buffer role and sensor-source origin remain unresolved. No guessed RAW patch built or live command sent.

## Follow-up: start waits for a response, not yet proved pixel completion

0x63df189e forces response-count1 and calls0x63b31990. That routine submits through0x63b31358, then invokes0x63b318ec. The latter receives command0x41 via0x63b31828, matches returned ID to requested ID, copies16 response bytes and one flag, and returns after the requested number of responses. Four original-instruction cases verify one/two responses, receive failure and count>3 rejection. Hardware/message receive mocked. This disproves an immediate fire-and-forget return, but command0x41 may acknowledge setup rather than completed pixels; do not call it a DMA fence until its producer is traced. Next trace0x63b31828 and producer of0x41.
