# Original YC dataflow protocol recheck - 29 October 2026

Offline reverse engineering only. No camera access, flash, reboot, mode change or live IPC occurred. Last known installed revision remains 3.4; its zero-frame capture and reported shutdown crash are unresolved. The unfinished local 3.5 draft is not a deliverable; its earlier build predates later source edits. No 3.5 package was created.

This recheck supersedes the 28 October team's claims that YC1Pin is an established receiving subscription and Category 2 is a proven completed-frame lease. It does not negate independently verified DMM results. It does not establish the cause of the observed shutdown crash.

## Method and reproducibility

Original ELF32 ARM libraries were loaded in Unicorn, with R_ARM_RELATIVE/ABS32/GLOB_DAT/JUMP_SLOT relocations resolved against their real symbols. Getters, pin construction, pin message serialization and selected native dispatch branches ran as original instructions. OSAL transport was intercepted for wire inspection; libc memory operations were emulated. Native type-1 dispatch stopped before real connect side effects or abort execution. Receiver/dispatcher identification executes constructor prefixes only, then follows the genuine vtable/typeinfo pointers. No guessed connection was sent to hardware.

PLT annotations resolve the actual GOT slot encoded by each ARM stub. A fixed `plt + 20 + 12*index` formula is wrong for these mixed ARM/Thumb stubs. The corrected resolver matches all 160 PLT relocations in dataflowInfraFramework.so. See firmware-input-hashes.json for exact inputs (framework MD5 f70f50f931e9c2cf415cc2728e324f60; libObj MD5 0b4be3fb599b539c69c782bd400dd8e9).

All addresses below are original library-relative virtual addresses, Thumb bit cleared. Linear disassembly includes literal pools; text after a function return is not automatically executable. Call scans are candidates rather than a proof of reachability or completeness.

Recipes are in recipe/. They require Python with pyelftools, capstone and unicorn, the local firmware dump at the recorded path, and the retained SSYC capture in the original workspace. Run from the workspace root, in order:

```
python -B <recipe>/collect_evidence.py
python -B <recipe>/verify_category2_and_pin.py
python -B <recipe>/verify_pin_wire.py
python -B <recipe>/inspect_native_receive.py
python -B <recipe>/verify_native_type1.py
```

Scripts write .local/outputs/yc-subsystem-offline-20261029/. Firmware binaries and raw captures are deliberately not bundled.

## 1. Category 2 layout is verified; completion semantics are not

Original `C_DataflowInfra_Entry_ImageOutTimInfo` constructor is at framework+0x2453c. Logical payload is 28 bytes, stored at object+0x14. The retained ETRY allocation is padded to 32 bytes. Do not treat allocation padding as a field.

| Payload offset | Bytes | Original getter | Retained value |
| --- | --- | --- | --- |
| +0x00 | 8 | CreateStartTiming, +0x245bc | u32 words [0x1979, 0] |
| +0x08 | 12 | DataTransTiming, +0x245dc | [0x197c, 1, 0] |
| +0x14 | 4 | Id, +0x245f4 | 0x7600 |
| +0x18 | 1 | RecordingState | 0 |
| +0x19 | 1 | MainStreamStartTrigger | 0 |
| +0x1a | 1 | MainStreamStopTrigger | 0 |
| +0x1b | 1 | Struct padding | no semantic claim |

Original GetData_All copies 28 bytes. Source capture SHA256 is 9c60c7088da03631af4cd06fbd8f9d444d084e9104ead87cb0147ef76ac45f9c. Execution confirms layout and values, not timing units, ID monotonicity, producer completion, pixel write coherence or lifetime. One captured ID cannot establish a monotonic sequence. A DMM Share of metadata does not establish any of those semantics either.

Evidence: category2-and-pin-original-execution.json; ImageOutTimInfo-original.txt.

## 2. YC1Pin is not the receiver established by the team report

Executing libObj+0x6f5958 constructs RTTI `dmpNative::YC1Pin`, property words [1,3,1,0x0080003b], with its internal DataflowInfraPin pointer initially null. libObj+0x6f5994 allocates a 0x38-byte pin; +0x6f5a38 calls its outgoing Send. The scalar argument becomes Send's first u32 argument; the second u16 and third u32 arguments are zero on that branch. This does not establish a frame-receive subscription.

The native connection wrapper at +0x6f5bbc checks incoming property words and route high-half 0x59 before calling DataflowInfraPin::Connect. These checks establish connection handling, not a pixel lease or callback contract.

The earlier claimed consumer ingestion address +0xe48d30 lies in generic YC metadata accessor code: it constructs the standard YC object and fetches ImageSizeInfo, YcStateInfo and ImageOutTimInfo. A metadata accessor is not by itself a task/queue receive entry.

## 3. Genuine native receive loop and dispatcher found

Constructor-prefix execution identifies these original objects by RTTI:

- libObj+0x7009a0: `dmpNative::CmdQueue`.
- libObj+0x700734: `dmpNative::CmdDispatcher`.

CmdQueue's loop +0x700a2c calls DataflowInfraReceiver::ReceiveASync at +0x700a42 with timeout -1. It passes the received message to CmdDispatcher+0x7007d8, clears the message, and loops while dispatch returns zero. Its queue literal at +0x700a74 is 0x0080003b (same route as the native pin properties).

For inner message header 0x1000, CmdDispatcher reads the u32 at message+0x10. Value 0 goes to +0x6fcf7c; value 1 goes to +0x6f71e8. This word's field name is not inferred from the dispatch alone.

Critically, the type-1 handler +0x6f71e8 routes:

| Opcode | Branch | Proven behavior |
| --- | --- | --- |
| 0x0100 CONNECT | +0x6f7070 | wrapper calls YC1Pin connect handler +0x6f5bbc |
| 0x8100 CONNECT_COMP | +0x6f70ac | wrapper calls YC1Pin connection-completion handler |
| 0x0102 SEND | +0x6f7124 | unconditionally calls abort PLT +0x10b888 |
| 0x8102 SEND_COMP | +0x6f712c | unconditionally calls abort PLT +0x10b888 |

All four branches were executed in Unicorn with controlled opcode inputs, stopping at connect wrappers or the abort PLT. The SEND paths do not first inspect a connected-state flag. This native handler is not a drop-in video-frame receiver; manufacturing a SEND toward it could abort the application. No such message was sent to the camera. Other endpoints may receive video; this finding does not establish that none exist.

Evidence: native-receiver-rtti.json, native-type1-dispatch-execution.json, native-receive-dispatch.txt, native-type1-handler.txt, native-type1-endpoints.txt, native-pin-receiver-regions.txt.

## 4. Original generic pin wire protocol executed

Controlled fixture only: own properties [1,3,1,0x0080003b], peer [1,3,1,0x0059000e]. These constants are not an authenticated subscription recipe. Generic pin constructor +0x21abc starts state 1. Send before Connect returns -26 and sends nothing. Connect+0x22158 checks property compatibility, stores peer properties and enters state 0. Its completion opcode is 0x8100, not 0x8101.

For ordinary Send+0x21e6c, the 52-byte 0x0102 payload is:

| Offset | Width | Value |
| --- | --- | --- |
| +0x00 | u16 | 0x1000 |
| +0x02 | u16 | 0x0102 |
| +0x04 | u16 | 52 |
| +0x06 | u16 | 1 |
| +0x08 | 4*u32 | own properties |
| +0x18 | 4*u32 | peer properties |
| +0x28 | u32 | first Send argument |
| +0x2c | u16 | second Send argument |
| +0x2e | u16 | 0 in this path |
| +0x30 | u32 | third Send argument |

The generic signature is Send(unsigned long,unsigned short,unsigned long). For a particular producer, SDS placement must be traced at that caller. The native YC1Pin wrapper does not put its input scalar at +0x2c. This does not disprove that a different RTOS producer passes an SDS in the second argument.

SendComp+0x21fc4 emits 44-byte 0x8102: peer properties at +8, own properties at +0x18, status i32 at +0x28. It does not echo an SDS or pixel handle. This suggests connection/endpoint state associates completions with outstanding work; that state and ordering still need tracing. Do not treat SendComp(0) as an arbitrary handle-based release primitive.

No DMM Share/Open/Free occurred in the executed generic Connect/Send/SendComp fixture. Message construction alone does not acquire a frame reference. A separate public-CPU transfer branch uses 64-byte opcode 0x0103; it was inspected, not executed by the plain-route fixture.

Evidence: pin-wire-original-execution.json; DataflowInfraPin-original.txt.

## 5. Generic ReceiveASync is not frame subscription

Framework+0x228d8 receives an OSAL message, copies at most 256 bytes into its DataflowInfraMsg storage, classifies it and frees the OSAL message. The plain path does not call a user-supplied frame callback. Its public-CPU 0x0103 path can allocate/open DMM storage, copy transferred bytes, close it and rewrite the payload to 0x0102; this distinct branch must not be confused with borrowed RTOS YC ownership.

RegSyncCb+0x226dc wraps osal_reg_sync_msg_queue_cb. Its name and code are for synchronous-message callbacks; registration is not evidence of an asynchronous YC subscription.

Evidence: DataflowInfraReceiver-original.txt; libObj-pin-receiver-call-candidates.txt.

## Remaining offline work

1. Find the real receiving endpoint for the target YC producer. Trace RTOS output-pin connection construction and an actual consumer's dispatch, rather than reusing CmdQueue/YC1Pin because its names look relevant.
2. Recover which Send argument carries SDS for that producer, when metadata and pixels are shared, and what route/CPU receives each reference.
3. Trace outstanding-frame tracking through SEND_COMP, disconnect and teardown. Establish exactly who releases which DMM references and when producer reuse becomes possible.
4. Trace ImageOutTimInfo writers and consumers to establish timing/ID semantics. Keep completion, freshness, lifetime and cache/DMA coherence separate.
5. Return to SDF acceptance and output packing only after the source ownership path is established. Range acceptance and a successful mocked call do not prove live hardware conversion or YUY2 layout.

No new flashing package is justified by this evidence alone. The 3.4 shutdown crash remains open; these findings explain why the prior proposed receive design is not established, not why the deployed camera restarted.
