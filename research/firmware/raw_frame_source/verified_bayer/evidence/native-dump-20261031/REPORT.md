# Native RAW dump route and completion-domain correction —31October2026

Offline only. No camera access, flash, restoration or native RAW capture.

## Important correction: resolved completion bridge belongs to resize

Resolved engine lookup0x63a4427c: GOT0x64640320 points storage0x64412ff4. Its initializer0x63a46cc4 calls constructor0x63a44264, which installs vtable0x6458d7b0. RTTI is8RcResize, NOT a demonstrated sensor/DFE capture engine. Slot+0x14 is0x63dc3d21 and+0x28 is0x63a45431. Thus the prior native event0x16 callback/mask bridge is concrete resize-operation machinery, not by itself sensor DMA completion. Do not reuse it as a sensor completion certificate. The named capture read-end mask may aggregate different operation completions; each contributor needs its own identity.

## Stronger acquisition route: firmware already exports opened buffers

Native0x639088a0 checks debug gate0x63d893f4, refuses0xffff handle, opens current handle throughCapture_MemOpen0x63d8a42a, forwards span address+16/size+20 to0x63908820, then closes via0x63d8a480. Four original-instruction cases verify disabled/invalid/open-failure/success control flow with external services mocked. This supports observing existing native dump transaction rather than holding arbitrary sensor buffers for USB.

0x63908820 checks selection gate0x6390878c(tag), logs filenameFILE%04x/address/size, calls0x6396f33c with tag=(tag|sequence<<8), address,length,mode0. The mode0 writer constructs24-byte message: u16operation1,+2tag,+4address,+8length,+12bytecontext,+13byteconfig,other control fields. It sends to endpoint0x012802f1 via0x635df64c, waits for reply through0x635df6a0 with300000 timeout units, then releases message/reply resources. This is not yet proved durable file completion: receiver must be decoded.

Native dump path strings/methods include MemAreaMSDebug_RAW at0x6390897c and /mnt/FILE%04x.dat referenced at0x639a2cc8 and0x63b97636. RAW handler can optionally decompress based on configuration+0xf6; the raw-byte experiment must preserve the existing source form and record encType, rather than enable implicit conversion.

Global dump gate0x63d893f4 checks whether0x6396e358(1)!=9. Selection gate0x6390878c uses configuration object fromGOT+a2f4: profile byte+0xf0 and individual tag bytes+0xf1..+0xf5. No configuration was edited. In named ReadEndBase0x638f4018, native call0x6390897c receives contextRAWhandle+0x67b6 on a guarded branch (config+0x6c), otherwise alternate+0x67b0. Existing native consumer placement is a much stronger capture boundary lead than guessed event bits, but form/completion/coherency still need verification.

## Proposed practical first RAW patch

Observe/enable only the native RAW dump transaction at its existing native call site. Capture the real handle, geometry/encType and address/byte count while native open/close handles ownership. Trace endpoint0x012802f1 to determine successful copy/storage acknowledgment and storage location, then spool the saved bytes over existing USB carrier slots independently. This may avoid a48MB private snapshot and any new sensor mode command. Do not activate debug profiles blindly; boundedone-shot selection, capacity, endpoint behavior and error cleanup must be verified. No flashable candidate yet.

Next exact targets: receiver of endpoint0x012802f1, /mnt/FILE formatting code at0x63b97636, and configuration loader/setter of dump-selection fields. Trace native RAW dump caller geometry and compression without assuming14bit/RGGB.

## Native dump protocol executed

Four original-instruction tests now cover writer0x6396f33c mode0: successful request, send error, receive error, busy refusal. Exact first12message bytes for tag0x701,address0x20000000,length4096 are010001070000002000100000. Endpoint0x012802f1,24-byte request and300000-unit reply wait confirmed. Successreturns0; send/receivefailure maps-4; busyreturns-3. Message services/logging are mocked. Existing caller0x639088a0's open->dump->close ordering separately has4cases. No test certifies receiver persistence or Bayer format.

Second /mnt/FILE%04x.dat reference0x63b97636 belongs to another file/control path with endpoint0x008f013a; do not conflate with native dump0x012802f1 without a proved bridge. The first reference0x639a2cc8 lies in an alternate debug writer state machine. Neither reference alone proves the full dump-service receiver path. Full receiver dispatch remains unresolved.

## Exact Linux receiver found and executed

Scanning original Linux libraries for endpoint0x012802f1 found CameraOnDemandSaver.so at fileoffset0x15dc. Its original receiver thread+0x1c8c dispatches operation1 by byte+0xd:0->fsys_write(+0x1af4),8->linux_write(+0x174c),6/0x20->fsys_write_phys_direct(+0x19d0),other->failure. Six original-instruction cases verify writer-before-reply-before-free ordering and success/failure forwarding with writer/OS calls mocked. Reply snd_msg gets the received header identity and writer bool; sender RTOS wait does NOT inspect that bool, so RTOS return0 cannot certify a successful file.

Mode0fsys_write chooses native media and builds paths from /dev/ms/FILE, /dev/mmca/FL or /dev/mmcb/FL plus tag. Maps supplied address through /dev/mem read-only, then uses malloc+memcpy+Fsys_WriteAndFlush or chunkedfile_write_exe; closes and unmaps before thread replies. Native file persistence depends on actual media and errors; do not substitute Linux /log paths into Fsys namespace without proof.

IMPORTANT mode8linux_write is not a generic safe dump: only tag0 opens its compiled /setting/psd.bin path. Nonzero tags are rejected. Never select this mode to capture RAW or overwrite psd.bin. Candidate should intercept mode0RAW-specific requests or use a new explicitly scoped save method, preserve other requests and report completion independently.

Physical mapper+0x16c8 opens/dev/mem read-only, computes page offset via getpagesize/divmod, mmap(PROT_READ,MAP_SHARED) exact supplied physical page plus length. No arbitrary source scanning. Existing receiver has limited validation/short-write handling; new receiver adapter needs checked physical range/span, bounded length, checked mmap, complete-write loop and own exclusive output files.

Concrete integration design now: native MemAreaMSDebug_RAW request at original capture boundary -> existing synchronous endpoint -> selected RAW-only Linux receiver adapter -> bounded saved file+exact24Bpacket sidecar -> reply after verified copy/write -> later read file into USB614400Bcarrier publisher. This avoids inventing sensor triggers and a separate48MB DMM allocation. Still missing activation of one-shot native dump selection, authoritative current RAW metadata/depth, and guarded receiver integration. A working patch is not yet certified.
