# Native LCD configuration and sequence reconstruction

18 November 2026. This recovers part of Sony's display control contract. It does **not** establish a complete physical LCD initialization recipe. No display payload was installed or activated for this investigation. Later hardware trials confirmed full-screen scanout with the panel timing inherited from stock firmware.

## Evidence and address spaces

The offline firmware reference has MD5 cdcae9d4fdbf66a33704a4c7564e346d and load base 0x635c6000. Function addresses below are **file offsets**, unless explicitly marked firmware VA or physical MMIO. Thumb callable pointers additionally carry bit 0. Current-body av-cam.bin has MD5 90096db2c76148f4f9db5d104e5c608c; these are different whole images.

One owner-authorized, read-only Senser session captured the current av-cam.bin, liro.ko, backup.ko and libObj.so, plus 328 selected display-related Backup units. It did not install files or write MMIO. Display code slices [0x503000,0x506000), [0x4c9000,0x4ca000), [0x808000,0x809000) and profile-ID list [0x1026af0,0x1026fb4) match the reference byte for byte. This does not establish matching runtime memory. The [body receipt](data/display-current-body.json) retains file/slice hashes and selected settings; raw binaries and terminal logs remain local.

The [offline contract report](data/display-native-contracts.json) records original-instruction tests and source identities. These are CPU instruction tests with recorded MMIO writes, not a peripheral simulation or physical display test. Reproduction tools are in the [atlas tool directory](../../research/device/zve10_hardware_map/README.md).

## Callback binding and settings

The firmware delegates settings reads through LiRo. Its loader copies the .init.data callback array to callback-table **+0x24**. Ignoring this prefix binds the wrong functions. The audit checks the original loader instruction, memcpy relocation, wrapper slot encoding and imported relocation names.

| Firmware wrapper | Callback slot | LiRo .init.data offset | Target |
| --- | --- | --- | --- |
| 0x1980c | 0x298 | 0x274 | Backup_read |
| 0x19828 | 0x264 | 0x240 | Backup_nread |
| 0x19860 | 0x29c | 0x278 | Backup_read_multi |
| 0x199b8 | 0x2e0 | 0x2bc | Backup_read_4Byte |
| 0x19208 | 0x188 | 0x164 | Vspin_lock |
| 0x19224 | 0x190 | 0x16c | Vspin_unlock |

Backup_read_4Byte looks up a property and returns its four-byte value, or zero for a missing/wrong-sized property. Backup_read_multi takes a zero-terminated ID array and a destination-pointer array. Values such as 0x00f9088f in this path are **Backup unit IDs**, not MMIO addresses.

Panel configuration loader 0x5034a4 populates eight byte-sized GPIO bank/bit slots at firmware VAs 0x64526746 and 0x64526735. Getter functions 0x5032fc and 0x503328 copy the respective arrays.

| Slot | Bank unit | Bit unit | Loading condition | Current-body values |
| --- | --- | --- | --- | --- |
| 0 | 0xf900ac | 0xf90068 | First flag array [0] | Both 0xffffffff |
| 1 | 0xf901ab | 0xf901ac | First flag array [1] | Both 0xffffffff |
| 2 | 0xf9088f | 0xf90890 | First flag array [1] | Bank 11, bit 20 |
| 3 | 0xf90375 | 0xf90376 | Unconditional | Both 0xffffffff |
| 4 | 0xf90377 | 0xf90378 | Unconditional | Both 0xffffffff |
| 5 | 0xf9040d | 0xf9040e | First flag array [3] | Both 0xffffffff |
| 6 | 0xf90560 | 0xf90561 | Second flag array [1] | Both 0xffffffff |
| 7 | 0xf90562 | 0xf90563 | Second flag array [2] | Both 0xffffffff |

First flags come from units 0x5f01d7..0x5f01da; current values are 0,1,0,0. Do not interpret an unused value truncated to 0xff as GPIO bank 255. The helpers reject banks greater than 17.

GPIO output helpers 0x808cca and 0x808cd6 dispatch to 0x4c95c0. Physical SET/CLR addresses are 0xf2910000 + (bank << 8) + 0x44/0x48, mask 1 << bit. Thus the selected slot maps to **0xf2910b44 / 0xf2910b48, mask 0x00100000**. Eighteen original-instruction cases checked bank/bit/direction arithmetic, plus an invalid-bank case. The pin's electrical role, polarity and timing are **unresolved**; it is not yet established as reset, power or backlight. No writes to this pin were made.

### GPIO configuration and observed active state

The native configuration wrapper at file offset `0x808c26` rejects bank numbers above 17 before taking Vspin lock 9. With the lock held, it interprets a 16-byte argument as follows. These are the effects of the reference instructions. The required LCD configuration order across the other registers and clocks remains open.

| Argument | Verified write for GPIO11 bit 20 |
| --- | --- |
| Byte `+0x00` (port selection) | Nonzero writes `0xf2910b34` for GPIO mode. Zero writes `0xf2910b38` for peripheral mode. |
| Signed word `+0x04` (direction) | Positive writes `0xf2910b04` for output. Zero writes `0xf2910b08` for input. Negative preserves direction and clears input enable. |
| Byte `+0x08` (input enable) | If direction is nonnegative, nonzero writes `0xf2910b24` and zero writes `0xf2910b28`. |
| Signed word `+0x0c` | Negative writes `0xf2912b44` then `0xf2912b58`. Zero writes `0xf2912b48` then `0xf2912b58`. Positive writes `0xf2912b48` then `0xf2912b54`. The electrical meaning of this secondary bank remains open. |

Every write in those cases uses mask `0x00100000`. The four original-instruction trials used mocked lock callbacks and recorded ordered MMIO writes. Sony GPL `drivers/gpio/gpio.c` and `gpio_inc.h` establish port selection, direction, input enable and data polarity for the primary bank.

During the expanded Senser snapshot, GPIO11 DIR, PORTSEL, WDATA and RDATA all had bit 20 set and INEN was zero. That is the controller state for a GPIO output commanded high, with input enable clear. In the saved stock live-view samples, RDATA also reported bit 20 high. Combined with the stock sequence's SET on startup and CLR on shutdown, this establishes the role of the pin in the firmware sequence. Its board-level signal name and voltage remain unverified. [Senser capture](../../research/device/zve10_hardware_map/evidence/20261119-display-senser.json) · [Live-view capture](../../research/device/zve10_hardware_map/evidence/20261119-display-live-view-ssh.txt)

## Profile loading

Loader 0x502a24 reads selector unit 0x5f0206 and chooses an ID-list pointer from firmware VA 0x645ecae8. Selector 0 uses list 0x645ecaf0; selector 1 uses 0x645ed21c. The current body reports selector **0**. Its list contains 304 one-byte units followed by a zero terminator. Backup_read_multi fills temporary storage; the native loader copies 0x130 bytes into profile firmware VA **0x6455fe88**.

The captured 304-byte profile has SHA-256 d0556483b795991551142cd359ca03a1711df62503823ac8c63f78db55a7688f and matches the selected profile from the identified saved Backup.bin. All selected pin/feature properties also match that saved file. This binds those settings to this body at capture time; it does not establish electrical meanings or reset values.

Loader 0x502b98 populates additional blocks, including a 0x180-byte profile at firmware VA 0x6455ffb8. Its destination-pointer construction handles wider fields. It must not be reconstructed by blindly concatenating one byte per unit. Complete field meanings, timer cadence and the association with physical output timings remain unresolved.

## Six-stage panel sequence

Native sequence function **0x504fa8** uses a bounded six-entry Thumb table branch and state at firmware VA 0x64429ab8. These are software sequence states, not hardware register enums.

| State | Branch target | Recovered behavior |
| --- | --- | --- |
| 0 | 0x504fca | Copy pin tables; conditionally configure/toggle slots; advance to state 1. |
| 1 | 0x50509a | Set/request mode state and derive a profile-dependent wait. Device/profile conditions can skip a stage. |
| 2 | 0x505130 | Perform a device-dependent step and wait. |
| 3 | 0x50516c | Invoke 0x505d94, then wait. This callee sets a software flag; it is not itself a proven serial transfer. |
| 4 | 0x505196 | Optionally invoke 0x506158, then wait. This callee consumes profile bytes; its physical role is unfinished. |
| 5 | 0x505234 | Check completion conditions, reset sequence state and return completion in the applicable branch. |

Wait helper **0x504190** increments a counter once per invocation. It advances only when the signed counter reaches the selected threshold **and** the applicable pending word at firmware VA 0x64560304+4 or +8 is zero; then it clears the counter. Eight original-instruction cases verify this gate. These waits are **not established milliseconds**. Function 0x5041b8 selects thresholds using profile bytes and device selection; the invocation period is not yet recovered.

LCD callback 0x505534 calls this sequence. Dispatcher 0x50b24c selects a handler through the table at file offset 0x8dbe0c using a selector byte at firmware VA 0x645603d1. The table includes off-handler 0x505bdc and LCD-handler 0x505534; another handler at 0x5055dc is an alternative-output lead. The scheduler, request producer, serial transfer and completion chain still need tracing. Calls in the bounded CFG are recorded, not recursively resolved. The boot graph has an outside-bound tail target. The corrected off dispatcher has four in-range table targets. Earlier analysis counted two extra entries by reading instructions past its table.

## Panel request path

The stage-3 helper at file offset `0x505d94` writes the supplied byte to firmware RAM `0x64526806` for device 1 or `0x64526b82` for device 2. The original instructions verified both values of the flag. Consumers at firmware VAs `0x63acfa18` and `0x63aced9c` apply profile-dependent bit masks to shadow register/value pairs. The worker at firmware VA `0x63ac8e8c` reaches the LCD sequence dispatcher at `0x63ac905e` and a separate profile update routine at `0x63ac90a8`. Its wrapper at `0x6371dc94` has two direct callers, at `0x637497f8` and `0x6374c2ca`. Static tracing confirms those calls carry a request pointer. The time source and interval for sequence advancement remain open.

Two generic builders at firmware VAs `0x63ace390` and `0x63ace244` accept type bytes 1 through 12. They construct a 64-byte descriptor and pass it to wrappers that send a synchronous OSAL message to endpoint `0x740017`. The request includes a pointer to the register/value pair buffer. The associated callbacks at `0x63acde54` and `0x63acbc54` clear the matching pending flags. The endpoint's hardware receiver and bus framing remain open.

For the selected body profile, the 304-byte Backup reconstruction matched the saved body SHA-256. Its type byte at `+0x00` is `0x10`, pair count at `+0x01` is zero, and selector at `+0x2f` is `0x60`. The reference decoder preserves the type byte in the software configuration. Both generic builders return zero for this type while leaving the descriptor untouched. Tests with types 1 and 12 reached the queue wrapper and types 0 and 13 returned early. This rules out that pair-list path for this profile as decoded. The GPIO, timing and other profile-dependent paths still need tracing for a cold start. No camera or MMIO access occurred during the instruction tests. [Audit data](data/lcd-profile-transport.json)

## Graphics-library API boundary

Current-body libObj.so SHA-256 is **bc0deb2f0e94218752e42ce6f5a3576d7456971eb63fbde705ffbd9b3a7fdeea**, matching the offline dump. It differs from the ELF identity guarded by the external QEMU presenter.

These six exported APIs have exact eight-byte bodies returning zero without processing their arguments in this identified ELF: GRM_screenGetOnBitmap, GRM_fbrmInitializeYUV, GRM_fbrmPrepareUpdateYUV, GRM_fbrmUpdateYUV, GRM_fbrmFillrectYUV and GRM_fbrmRectblitYUV. The audit checks each export and original body. A zero result from these functions does not demonstrate a framebuffer update.

GRM_bitmapGetPhysicalAddress instead dispatches via an object vtable; bitmap read-lock/unlock take another object path. The concrete bitmap subclass, buffer lifetime, physical address and scanout ownership remain unfinished. QEMU's fixed vtable offset is not portable across the two library identities.

## Remaining display contract

The pin lookup, selected profile and wait/state structure are now body-bound. The physical screen path remains incomplete: pin electrical role, panel command transport, clocks/reset dependencies, output mux, active timings, pixel source and frame/update acknowledgement. In particular, 640/480-related values in the 0xf3445000 bank do not prove that bank drives the physical LCD. The colour word at 0xf3445108 must not be treated as a self-contained LCD test-pattern command.

Continue with the native request/completion chain and output routing, then connect a known pixel producer to its physical output. Normal-shooting and post-shutdown state must remain distinct from these service-mode configuration reads. Another resident write trial should wait for that specific transaction to be understood.

## Wait thresholds from the captured body profile, 19 November

An offline Unicorn run executed the current camera image at file offset 0x5041b8 with selector 1 and the captured 304 bytes restored to firmware VA 0x6455fe88. All nine in-range request indices (0 through 8) returned zero with the mode byte at 0x645601bc set to 0. All nine also returned zero with mode 4. An out-of-range index of 9 returned zero in both runs. Each call returned through the supplied link register. The firmware compares the mode byte for equality with 4. Its actual value in shooting mode remains unknown.

The native literal pool selects the profile at 0x6455fe88 for selector 1 and the separate profile at 0x6455ffb8 for selector 2. These results apply to selector 1 with the captured inputs. A zero threshold still requires a call to the wait helper and a clear pending word before the sequence can advance. The result gives no elapsed time for the panel transition.

### Which pending word gates the LCD sequence

Across the recovered LCD sequence at file offset 0x504fa8, the calls to the wait helper pass selector zero. Its selected word is firmware VA 0x64560308. The profile selector passed to the threshold function has a separate meaning. Stage 1 checks the device byte at 0x64560316. For device 1 and zero at profile offset 0x123 (captured unit 0x5f0573), it requests state 3 directly.

Two offline runs entered the current body image at the stage-1 decision, file offset 0x505102, and stopped at 0x505120 after the state store. Both used the captured zero profile field, device 1, an initial counter of zero and threshold zero. With words at 0x64560308 and 0x6456030c set to (0,1), the stored state was 3 and the counter was 0. With (1,0), the stored state was 1 and the counter was 1. The first word therefore gates this transition even when the threshold is zero. The pending-word values and device selector were experiment inputs. Their shooting-mode values and the identity of the code that clears the word remain open.

### Stage 4 message transport

In the saved current-body image, the stage 4 device-1 branch checks profile byte +0x111 (Backup unit 0x5f0541, captured value zero). With that value, the call at 0x5051c4 requires the runtime byte at firmware VA 0x645603f2 to equal one. The alternative call at 0x5051d8 requires profile byte +0x111 to equal two. The service capture supplies the profile byte. The runtime condition during shooting remains unknown.

Inside 0x506158 a separate runtime byte at firmware VA 0x6452680d selects a message path. Value one selects identifier 0x28018b and helper 0x5060dc. Value two selects identifier 0x2801d4 and helper 0x506060. Both helpers request a five-byte buffer, pass five bytes through the transfer helper at 0x5223ec and call the synchronous OSAL sender. The zero-return path passes five bytes back through the transfer helper before freeing the message.

Current-body LiRo relocation bindings establish the transport. Wrapper 0x19710 uses callback slot 0x1f0 (osal_valloc_msg_wait), 0x19668 uses 0x1d8 (osal_snd_sync_msg), and 0x1972c uses 0x1f4 (osal_free_msg). These identifiers can now be followed into the receiving task to locate the hardware-facing operation. The selected endpoint during shooting, its handler, and its relationship to the separate pending word remain unresolved.

### Independent callers and five-byte reply layout

An additional caller at file offset 0x1d0cc4 requests five bytes for endpoint 0x2801d4, sets bytes 0 and 1 to zero, sends synchronously, interprets the reply and frees the message. The result goes to firmware VA 0x6450c981. Byte 2 must equal zero and byte 3 bit 0 must be set for the caller to store the low nibble of byte 4. Otherwise it stores 0xff. Five Unicorn runs of the current image from 0x1d0ce0 to 0x1d0d08 used synthetic replies. For (status, flags, data) of (0,1,0xab), (0,0,0xab), (1,1,0xab), (255,1,0xab) and (0,3,0x50), the observed byte stores were respectively 11, 255, 255, 255 and 0, all to the same address. The physical quantity represented by the nibble is unknown.

A second sender for endpoint 0x28018b sets bytes 0 and 1 to 1 and 0, updates bit 0 of byte 4, sends at 0x1d2a76, and returns byte 2 sign-extended. Both independent callers support interpreting byte 2 as a response status. The duplicated endpoint literals around 0x4d00bc and 0x4d03f0 are additional leads. Their presence alone does not identify a receiver.

### Registration targets for the five-byte messages

The two matching sets of endpoint literals belong to registration and unregistration routines. LiRo relocations identify slot 0x1ec as osal_reg_sync_msg_queue_cb and 0x1e8 as osal_unreg_msg_queue_cb. The registration routine begins at file offset 0x4cfe88. Executing its instructions in Unicorn through 0x4cfeee, with the registration wrapper intercepted and returning zero, produced these argument tuples in the current camera image.

| Endpoint | Handle storage VA | Callback Thumb pointer | Fourth argument |
| --- | --- | --- | --- |
| 0x28018b | 0x6455f91c | 0x63dd03c5 | 0 |
| 0x2801d4 | 0x6455f968 | 0x63dcffb9 | 0 |

Both callback targets decode to a single BX LR instruction (file offsets 0x80a3c4 and 0x809fb8). The following functions have separate entries. These registered targets return immediately with the incoming registers and message bytes intact. The unregistration path starting at 0x4d0248 uses the corresponding stored handles. The execution test establishes the arguments constructed by the registration routine. Its activation in shooting mode, runtime callback replacement, and any other transport processing remain open. A trace through the OSAL implementation or another active binding is needed to attribute physical display effects to either message.

### OSAL callback selection in the saved Linux driver

Both local copies of osal_uipc.ko have SHA-256 97444b61e2ff8a256bd0e94187d93fa7b05e307e307b1bfe4bdcaefa49349345. The following offsets are relative to its ELF .text section. The current-body capture identified liro.ko directly. The identity of the running OSAL module still needs independent confirmation.

The registration entry at 0x3068 checks endpoint bit 15 and passes the low 16 bits to the queue lookup. It saves the firmware callback pointer at callback-record +0x14, its context at +0x18, and the driver trampoline __default_cb at +8 (ABS32 relocation at 0x30e8). Under the queue lock, the helper at 0x2ff8 installs this record in queue +0x18 only if that slot is empty. An occupied slot returns 0xfffffc00. Earlier emulation intercepted registration with a zero return, so the actual registration outcome matters.

The send entry at 0x34d0 calls 0x3374 with its optional hook arguments zero. It uses the low 16 bits to look up the queue. For the two panel endpoints those keys are 0x018b and 0x01d4. Under the lock it loads the installed record from queue +0x18 and calls its +8 function at 0x3474. A missing queue or callback record returns 0xfffffc04. For the default trampoline (0x2434), the driver releases the queue lock, invokes the registered callback with the original payload pointer and saved context, reacquires the lock, and returns zero. The callback return value is discarded. Thus a BX LR callback can give a successful synchronous send while preserving every payload byte. This explains the transport return for that binding. Identifying the installed record during an actual panel request remains the evidence needed to tie it to the physical display.

### Stage 0 use of GPIO bank 11, bit 20

An offline run of the current-body instructions from file offset 0x505024 to 0x505046 followed both device-selector branches with the captured flag 0x5f01d8 and pin slots 1, 2 and 7. For selector 1, the firmware attempts to clear slot 1 (bank 0xff is rejected), then sets slot 2. Unicorn recorded one 32-bit GPIO write, mask 0x00100000 at the SET alias 0xf2910b44. For selector 2 the same block selects slot 7, whose bank is also 0xff, and produced zero GPIO writes. This establishes the commanded direction for this stage and profile. Electrical level at the panel, pin mux state and the connected signal still need physical evidence. Other blocks in stage 0 were outside this test.

### Complementary GPIO action during panel shutdown

The off dispatcher at file offset 0x5052c0 subtracts six from the state and accepts indices zero through three. The four valid states are 6 through 9. The index for state 8 enters 0x5053fa. A zero invocation counter enables the pin operations for this stage. With the captured feature flag and pin slots 1, 2 and 7 installed in simulated firmware memory, two Unicorn runs entered the actual off dispatcher in state 8 and stopped at 0x505440. Both executed the native pin-table getters. Device selector 1 produced one 32-bit write of 0x00100000 to GPIO CLR at 0xf2910b48. Device selector 2 produced zero GPIO writes through that point. The rest of state 8 was outside the experiment.

Together with stage 0, this establishes a complementary command pair for selector 1: SET during panel startup and CLR during shutdown. The pin's electrical function remains unknown. The counter and device selector were test inputs. No on-camera levels or elapsed timings were measured.

### Register packing in the candidate timing block

In the current-body image the call at file offset 0x4b880c passes a record in r0 to 0x807848. The callee reads fields spanning 24 bytes. Running the original callee and all twelve field setters in Unicorn produced twelve 32-bit writes in the order below. Each row represents two successive writes to the same physical address. Offsets and bit ranges are listed in write order.

| Physical address | First record offset and destination bits | Second record offset and destination bits |
| --- | --- | --- |
| 0xf3445004 | +0x02 → 25:16 | +0x04 → 9:0 |
| 0xf3445008 | +0x0c → 26:16 | +0x0e → 10:0 |
| 0xf344500c | +0x00 → 24 | +0x0a → 16 |
| 0xf3445014 | +0x10 → 26:16 | +0x12 → 10:0 |
| 0xf3445018 | +0x14 → 26:16 | +0x16 → 10:0 |
| 0xf3445038 | +0x06 → 25:16 | +0x08 → 9:0 |

For each field the offline experiment changed only that input from zero to all ones and compared the write traces with simulated registers initially all zero and initially all ones. The changed masks agreed for both starting conditions. The inputs for the two single-bit destinations were byte loads. The remaining inputs were halfword loads. The caller raises +0x02 and +0x04 to computed minimums and sets byte +0x00 when either is raised. It similarly sets byte +0x0a when it raises +0x0c or +0x0e. Which physical output consumes these values and their timing units remain open. The experiment did not measure timing or drive the camera.

### Six fields decoded from the November 18 service capture

The current-body routine at file offset 0x807946 consumes six consecutive little-endian halfwords. Its six writes go to three register pairs of fields. An offline run with all input bits set established the write order and masks. Single-bit inputs confirmed the bit positions for 0xf3445048 and 0xf344505c. Matching these masks against the [saved Senser readings](../../research/device/zve10_hardware_map/evidence/20261118-senser-registers.json) gives the effective field values below.

| MMIO word | Observed word | Input offsets in write order | Captured high and low field values |
| --- | --- | --- | --- |
| 0xf3445048 | 0x02800025 | +0, +2 (12 bits each) | 640, 37 |
| 0xf3445058 | 0x00000000 | +4, +6 (11 bits each) | 0, 0 |
| 0xf344505c | 0x01df01df | +8, +10 (11 bits each) | 479, 479 |

The captured values reconstruct the bits visible to these setters. The upper bits of the source halfwords are discarded. Whether 479 encodes a last line, and which output consumed these fields at capture time, remain open.

### Source of the two 479 values

The current-body caller at file offset 0x4b3340 builds the six-halfword record on its stack and passes it to 0x807946 at 0x4b33cc. Let A, B and C be its first three arguments. If helper 0x4b03cc supplies a nonzero flag, the six fields in record order are (A, C+5, 0, 0, B-1, B-1). Otherwise the caller requests four halfwords (p,q,r,s) from 0x4b79ac with selector 1. The fields become (A-r-s, C+r+5, p, p, B-q-1, B-q-1). Arithmetic is truncated to halfwords before register packing. The paired values at 0xf3445058 and 0xf344505c are deliberately duplicated.

Three offline runs executed the caller from entry through the return from the real register writer. Only the two helper outputs were supplied. A nonzero flag with (640,480,32) and a zero flag with (647,482,29) and adjustments (0,2,3,4) both reproduced all three captured words exactly. Replacing the latter adjustments with (9,7,3,4) changed the last two words to 0x00090009 and 0x01da01da. This establishes the minus-one arithmetic and explains why the two 479 fields match. The service snapshot by itself cannot distinguish the branch, the original input values or the physical panel route.

### Runtime inputs that distinguish the timing formulas

In the captured firmware, helper 0x4b03cc returns its result through an output byte. It writes 1 if either byte at firmware VA 0x64522f80 or 0x64522ba8 is zero. When both are nonzero, it copies the byte at 0x644be156. Thus the adjusted timing formula requires both first bytes nonzero and the third byte zero. Offline instruction execution with memory-read tracing confirmed the short-circuit paths and the three addresses.

For the adjusted formula, the caller supplies selector 1 to 0x4b79ac. That helper copies four consecutive halfwords from firmware VA 0x644c11c4 into the caller's working record, in p, q, r, s order. Selector zero reads a separate record at 0x644c124e. Both base addresses and all eight halfword read addresses were observed offline. A stock-mode observation of the three decision bytes and the selected eight-byte record during the timing update could distinguish the paths. The prior Senser register snapshot contains neither the decision bytes nor that record.

### Matched Senser timing inputs and register words

The November 20 read-only Senser session captured two sequential sets of firmware RAM and Output 0 reads. Both sets gave `A=640`, `B=480`, `C=32`, and the decision bytes at `0x64522f80`, `0x64522ba8`, and `0x644be156` were all 1. The four adjustment halfwords were `(26,26,0,0)`. The saved values therefore select the unadjusted formula. The sampled mode word at `0x6441ddb0` was `0x1b`. The observations do not identify the most recent dispatcher call.

Replaying the original `0x4b3340` instructions with the sampled input values and unmodified helpers through the native writer reproduced all three measured Output 0 words: `0xf3445048=0x02800025`, `0xf3445058=0`, and `0xf344505c=0x01df01df`. For both replays, changing only the third decision byte to zero routed through the saved adjustment record and changed the last two words to `0x001a001a` and `0x01c501c5`. Output 0 remained active during the capture and the current OSD0 address advanced. This connects the sampled Senser timing configuration to its programmed fields. An atomic record of the stock writer's invocation, the pixel-clock source and the cold-start ordering are still open. [Capture and replay results](../../research/device/zve10_hardware_map/evidence/20261120-senser-lcd-timing.json)

### Panel clock controls and active Senser values

The reference routine at firmware VA `0x63a60994` references `vph_clk_ctrl_set_async_panel`. It calls the panel port helper first and then configures the two-bit selection at `0xf2900000` and three divider/gate paths. Original-instruction runs verified the selector writes. Selector 0 clears bits 8 and 9, selector 1 sets bit 8 and clears bit 9, and selector 2 clears bit 8 and sets bit 9. The routines write the individual SET and CLR aliases.

| Divider register | Update word | Gate data and mask | Senser divider |
| --- | --- | --- | --- |
| `0xf2a01130` | `0xf2a01030` | `0xf2a00020`, bit 12 | 7 |
| `0xf2a11150` | `0xf2a11030` | `0xf2a10020`, bit 24 | 3 |
| `0xf2a12150` | `0xf2a12030` | `0xf2a10020`, bit 25 | 3 |

For admitted presets, each helper writes the raw divider value, commits by writing 1 to the update word, polls until the word is zero, and sets its gate bit. Argument `-1` clears the gate bit and `-2` sets it without changing the divider. These tests used simulated update completion and a mocked port helper for the higher-level mode cases.

Two read-only Senser samples taken with Output 0 active showed selector 2, all three update words zero, and all three corresponding gate bits clear. The reference routine with mode argument `0x1b` and option 0 reproduces the selector and gate bit state. That path leaves the divider registers alone. Mode `0x30` with option 0 programs divider 7 and sets the first gate bit, which differs from the observed state. This separates retained divider values from the selector and gate state used during the capture. No upstream PLL frequency, actual pixel-clock frequency or measurement of the physical panel signal follows from these samples alone.

The port helper's table at firmware VA `0x6441cdc4` holds four 12-byte rows of bank, bit and option. The initializer at `0x63a60adc` fills the table with `0xffffffff`, then reads the three fields for each row from Backup. Row 0 uses units `0xf90820`, `0xf90821` and `0xf90822`. On this body it contains bank 4, bit 26 and option 0. The other rows remain at the sentinel. Both port helpers skip rows with any sentinel field, and reject panel indices beyond row 3.

Executing the reference instructions with that row verified the enable helper at `0x63a60c10` writes mask `0x04000000` to secondary GPIO SET alias `0xf2912404`. The disable helper at `0x63a60b9c` writes the same mask to CLR alias `0xf2912408`. Option 1 additionally writes `0xf2912444` on enable or `0xf2912448` on disable, followed by `0xf2912458` for either operation. The port helpers and relevant GPIO instruction ranges match the saved body image byte for byte. The audit stubs diagnostic calls and records MMIO in emulated memory.

In two read-only Senser samples, Output 0 was enabled and Output 1 was off. The OSD0 DMA address changed between samples. GPIO4 bit 26 was clear in the primary DIR, RDATA, INEN, PORTSEL and WDATA words, and set in secondary word `0xf2912400`, which read `0x3fffffff` both times. The primary PORTSEL bit selects peripheral mode. The secondary word is a controller readback and supplies no measurement of the pad signal or pixel-clock frequency. GPIO11 bit 20 is separately controlled by the LCD startup and shutdown sequence. [Reference instruction audit](data/panel-clock.json) · [Senser clock capture](../../research/device/zve10_hardware_map/evidence/20261120-senser-lcd-clock.json) · [Senser pin capture](../../research/device/zve10_hardware_map/evidence/20261120-senser-lcd-clock-pin.json)

### Order of panel clock and VPH top programming

The VPH setup routine at firmware VA `0x63a67d24` calls the panel GPIO table initializer at `0x63a67d2e`, before reading further Backup settings. A separate panel switch routine at `0x63a696c4` takes four arguments in order: panel index, mode, enable and option. The active branch configures the panel GPIO, clock selector and divider gates before issuing six writes to VPH top registers. Mode `0x1b` and mode `0x30` with option 0 produce these same writes in order.

| Physical address | Value written | Active Senser readback |
| --- | --- | --- |
| `0xf3440050` | `0x0002062a` | `0x0002062a` |
| `0xf3440058` | `0x00200000` | `0x00200000` |
| `0xf3440054` | `0x00000033` | `0x00000033` |
| `0xf344005c` | `0x00000001` | `0x00000001` |
| `0xf3440040` | `0x00070077` | `0x00070077` |
| `0xf3440048` | `0x10010b77` | `0x10010b77` |

Two Senser samples matched all six words with Output 0 enabled, Output 1 off, selector 2 and the three clock gate bits clear. The `0x1b` transaction reproduces the sampled selector and gate bits while preserving the dividers.

A direct firmware caller at `0x63a67b08` supplies panel 0, mode 8, enable 0 and option 0. Replaying that call writes the VPH top disable sequence first. It then clears the three clock gate bits, selects mux value 2 and clears the panel port mask. The active and inactive tests run the original switch and MMIO writer instructions with diagnostic calls stubbed and divider update completion simulated. [Instruction audit](data/panel-clock.json) · [Senser top-register samples](../../research/device/zve10_hardware_map/evidence/20261120-senser-lcd-top.json)

### Panel switch arguments in Senser

The panel state machine at firmware VA `0x63a68b2c` dispatches through a check on the current mode. When the check at `0x63a68bd8` returns 1, the branch calls mode preparation and `0x63a89f8c`, then calls `0x63a6980c` at `0x63a68c06`. Otherwise, it calls mode preparation and the panel switch `0x63a696c4` at `0x63a68c36`, followed by a call to `0x63dc985a`. Both call sites source their four arguments from the same RAM fields. Two offline runs per branch exercised the original argument loading and stopped at the call. The common mode pointer was provided at entry, and the mode-preparation call was stubbed where it falls within the tested span.

| Argument | Firmware VA | Senser readback |
| --- | --- | --- |
| Panel index | `0x6441ddd4` | 0 |
| Mode | `0x6441de30` | `0x1b` |
| Enable | `0x6441de20` | 1 |
| Option | `0x6441dc40` | 0 |

Both snapshots showed these values alongside the active Output 0 and all six expected VPH top words. The native mode check at `0x63dc99c4` returned 1 only for modes `0x1a`, `0x1c`, `0x1d`, `0x30`, `0xd0` and `0xd1` across all 256 byte values tested. If the dispatcher reaches this check with the sampled mode `0x1b`, it selects `0x63a696c4`. That branch preserves dividers 7, 3 and 3. The snapshots do not record when the switch ran or who programmed the dividers before it. [Instruction audit](data/panel-clock.json) · [Senser switch-state samples](../../research/device/zve10_hardware_map/evidence/20261120-senser-lcd-switch-state.json)

### How a panel mode request reaches the switch

The service routine at `0x63a5d7b8` checks byte `0x6441af60`. For value 1, it passes the six-word request at `0x6441af64` to `0x63a680c4`, which copies it to `0x6441de00` and sets pending byte `0x6441ddfc`. The same service routine can call the request dispatcher at `0x63a69020`. On the tested transition, the dispatcher copies all six words to `0x6441de38`, clears the pending byte and passes control to the panel state machine.

Two read-only Senser samples agree across all three copies of the request. They contain `[1, 0x1b, 1, 0, 0, 0]`, with the pending byte clear, active mode `0x1b` and Output 0 enabled. Offline replay of that exact request from idle bookkeeping reached the panel switch with arguments `(0, 0x1b, 1, 0)`. The two synthetic comparison requests reached the alternate clock call for `0x30` and exposed a temporary mode 7 later overwritten by `0x47` for request `0x47`. The audit executed the native record copies, dispatcher and mode classifier and stopped before the clock call. It stubbed the mode-preparation and readiness calls listed in the report. The sampled records show the retained request. The timing and initial producer of the request during a cold boot remain open. [Clock instruction audit](data/panel-clock.json) · [Senser request samples and body code matches](../../research/device/zve10_hardware_map/evidence/20261120-senser-lcd-request.json)

The upstream queue path is visible in the firmware instructions. The wrapper at `0x6371f008` calls the request packer at `0x63a5c258`. For an accepted request, the packer copies six words to `0x64418eb8 + 0x20` and sets the byte at `+0x1c`. The send path at `0x63a5d288` passes the 720-byte message to endpoint `0x006603c4`. The receive path at `0x63a5f6b2` copies a message into staging at `0x64419e70`. The fan-out at `0x63a5eaa4` copies staging `+0x1c..+0x37` to destination `+0x20..+0x3b` when the dirty byte is 1. For staging selector zero, the destination is `0x6441af40`, so the resulting request starts at `0x6441af64`. The shared cleanup at `0x63dc839c` clears staging `+0x1c`. This upstream leg was traced offline by disassembly. Cold-boot request generation and timing remain open.

### Upstream clock setup and alternate modes

The firmware has separate setup sequences for clock blocks at `0xf2a01000`, `0xf2a11000` and `0xf2a12000`. The sequence at firmware VA `0x63a271a8` programs the first block, and the span `0x63a2733e` to `0x63a274b8` programs the other two. Each sequence waits for readiness, programs its control and several divider words, then writes 1 to the block's `+0x30` update word and waits for it to clear. Offline runs with the profile word at `0x645e5588` set to 0 and `0x60000` verified the address order and two control profiles. They seeded clock readiness, simulated update completion and started the read-modify-write control words at zero.

Those setup sequences leave the three panel divider words `0xf2a01130`, `0xf2a11150` and `0xf2a12150` untouched in both tested profiles. The first sequence writes 7 at `0xf2a01160`. The other two write 15 at `0xf2a11130` and `0xf2a12130`. Those are distinct addresses from the three panel divider words.

The original panel mode setter does write the panel dividers on other branches. Modes `0x1c` and `0x1d` program 3 in one auxiliary bank. With option 0 they choose mux 1 and program `0xf2a12150`. With option 1 they choose mux 0 and program `0xf2a11150`. Mode `0x14` uses the same selection pattern with divider 15. Mode `0x30` with option 0 chooses mux 2 and programs 7 at `0xf2a01130`. The audit verified these associations from MMIO writes. The three active Senser divider values therefore have matching setters elsewhere in the firmware, while the tested upstream setup code and active mode `0x1b` preserve them. Reset defaults and any earlier mode transition that wrote those specific words remain to be established. [Clock instruction audit](data/panel-clock.json)

### Timing inputs shared by two callers

Executing the captured body image from file offsets 0x4bef10 and 0x4c3af4 up to entry of 0x4b3340 produced the same five source reads. Arguments A, B and C are halfwords from firmware VAs 0x64626762, 0x64626764 and 0x644c12c2. The fourth argument is a word from 0x6441fd1c. The fifth is a byte from 0x6452321b passed on the stack. This identifies the input storage for both observed call sites.

The initializer beginning at 0x4bea28 loads 0x280 and stores it to A at 0x4bea68, then loads 0x1e0 and stores it to B at 0x4bea72. Thus the firmware explicitly configures the shared pair as (640,480) on this path. Other native blocks also write the pair. The initializer's invocation, later overrides and the physical sink at the time of the Senser capture remain unresolved.

### One mode-selection branch writes either 640 or 720 columns

At file offset 0x4c40e2 a branch selects among four dimension-setting routines. For r5 equal to zero or one, the firmware tests the byte at firmware VA 0x64523221. With a zero byte it calls 0x4befd4 or 0x4bf0cc respectively, both of which write (640,480) to 0x64626762 and 0x64626764. A nonzero byte selects 0x4bf1c4 or 0x4bf2c4 respectively, both of which write (720,480). Other r5 values take the 0x4bf2c4 branch directly.

Six offline runs started at this decision with r5 in {0,1,2} and the byte in {0,1}. The original instructions entered the predicted routines and produced the predicted dimension pairs. The tests covered their initial dimension stores. The complete timing configurations can differ even when their dimensions agree. Identifying the upstream mode and the source of the control byte is necessary to assign this branch to a physical sink.

### Inputs selecting the 640/720 branch

The mode dispatcher at file offset 0x4c3f8c preserves its first argument in r4. Argument 8 branches to 0x4c40e2. The second discriminator, held in r5, is a 32-bit read from firmware VA 0x6441dc40 via helper 0x4a0848. The dispatcher computes the control byte at 0x64523221 on entry, before the dimension decision.

With gate byte 0x64522f80 zero, the dispatcher stores zero. With the gate open, a 32-bit selector at 0x6441ddd4 chooses the source byte. Selector 1 uses 0x64522b4d, selector 2 uses 0x64522cb0, selector 3 uses 0x64522c76, and the default uses 0x64523091. Ten offline runs executed the original dispatcher from entry through the control-byte store using argument 8, distinct synthetic source bytes, both gate states and selectors 0 through 4. All produced the expected byte. The existing dimension-branch tests cover the subsequent use. For argument 8, a closed gate therefore selects 640 columns when the r5 discriminator is zero or one. Its other values select 720 even with the gate closed. The external meaning of these selectors and their live values remain unmeasured.

### Mode argument provenance at dispatcher calls

The current firmware contains multiple direct calls to 0x4c3f8c. The call at 0x499d96 preserves the value returned by getter 0x4a2574, a 32-bit load from firmware VA 0x6441ddb0. In contrast, the calls at 0x4a2be8, 0x4a2f0a and 0x4a3312 load their argument from 0x6441de30. These distinct storage locations matter when attributing a timing change to a caller.

The path at 0x4a2bd6 first tests the value from 0x6441de30 with predicate 0x8039c4. An offline execution of the original predicate for inputs 0 through 255 returned one for exactly 0x1a, 0x1c, 0x1d, 0x30, 0xd0 and 0xd1. For input 8 it returned zero, and the branch at 0x4a2bde skips the dispatcher call at 0x4a2be8. This excludes that specific call path when the tested word is 8. The other call sites and any changes to the mode word between test and reload remain separate possibilities.

### Native VPH display-update gate

The current-body routine at file offset 0x49deec selects a status path using the 32-bit word at firmware VA 0x6441da94. When the selector equals 1, it reads bit 10 of 0xf3440048. If that bit is set, it reads bits 15:8 of 0xf3440200. For other selector values the corresponding fields are bit 13 of 0xf3440068 and bits 15:8 of 0xf3440240. In each path, the return is one exactly when the status bit is set, the second field is nonzero, and firmware word 0x6441da78 equals 1. The caller at 0x49e3ec branches away from the following display-update work when this check returns one.

Sixteen offline runs used both selectors, both gate states, both status-bit values and second-field values of zero or three. The original code returned the expected boolean in all runs. The read trace showed one 32-bit status load, followed by the companion load only when the status bit was set. There were no MMIO writes in the tested helper. Separate code at 0x4a396c and 0x4a3986 uses matching masks 0x400 and 0x2000 on paired write targets, so the helper's reads and those native writes can be traced separately.

This supports a display-update gate, with the electrical event, output assignment and Linux IRQ number still unresolved. The November 19 snapshot omitted these two status registers. Its observed interrupt deltas alone cannot select either path or identify a VSYNC interrupt.

### Panel completion callback and Vsync-labelled diagnostics

In the saved body firmware the call at 0x50305e reaches the dispatcher from inside 0x502e8c. A wrapper at 0x157c94 forwards callers at 0x1837f8 and 0x1862ca into 0x502e8c. The former builds a descriptor on the stack. The latter passes a static descriptor from the SystemCmdSysv path, which contains the PanelSysvPrmGen diagnostic. These are verified software call paths. The periodic source and dispatch interval still need evidence.

Offline execution of the dispatcher at 0x50b24c confirmed selectors 1, 2 and 3 enter 0x505bdc, 0x505534 and 0x5055dc respectively. In the LCD-on and panel-off handlers, the request byte is at firmware VA 0x64560314. Completion clears that byte, calls the function pointer at 0x64560200 with argument zero if present, and clears the pointer. Four offline runs supplied both complete and incomplete outcomes to the original handlers and verified those effects. The on path uses the sequence return value. The off path tests the software byte at 0x64526757 after the off sequence.

The Vsync-labelled on and off messages in these handlers are conditional diagnostics. Both pass their completion text to 0x504464, which builds a 52-byte message with a leading halfword of 9 and sends it synchronously to 0x8f013a. Offline runs through that routine intercepted allocation, formatting, send and free and verified the arguments for both strings. The strings describe software completion and cannot by themselves identify a VSYNC interrupt, refresh cadence or a framebuffer-reuse fence.

### Configuration commands select the panel handler

The native service path at 0x50303c, 0x50305a and 0x50305e runs the configuration intake, then selector update, then dispatch. The intake at 0x503b34 processes the record at firmware VA 0x645601b8. In the branch for command IDs 1 through 3, with no request active and a nonzero callback, it marks the panel request active, copies the device and revision bytes and copies the callback to 0x6456031c. It stores the command ID at 0x645603d4 for the selector update. The firmware's diagnostic strings identify the fields as cmd_set_conf_id, cmd_set_conf_dev, cmd_set_conf_rev and cmd_set_conf_cb.

The selector update at 0x50b0cc uses a table of three-byte rows at file offset 0xa15a94. Each row holds current selector, command ID and next selector. For every current selector in {1,2,3}, command 1 selects handler index 2 (LCD-on at 0x505534), command 2 selects handler index 3 (0x5055dc), and command 3 selects handler index 1 (panel-off at 0x505bdc). Index 3 has yet to be tied to a physical output.

Three offline runs checked the intake stores for commands 1, 2 and 3, with the separate command-3 helper intercepted. Eighteen additional runs executed selector update and dispatch for every pair of current selector and command, with both values of the alternate path selector at 0x645603f6 and its secondary selector held at 2. These tests prove the verified route for those inputs. The configuration callback at 0x6456031c is a distinct storage slot from the LCD on/off completion callback at 0x64560200. The writer of pending word 0x64560308 and the cadence of the service path remain open.

### Initialization of the LCD wait words

The current-body initialization path calls 0x503104 from 0x503730. The callee loads a panel state pointer from the literal at 0x5032c0. It passes that pointer (firmware VA 0x64560304), zero and length 0x48 to the ARM fill routine at 0x522ad0 through the BLX at 0x5031ea. That range includes both wait words at 0x64560308 and 0x6456030c.

An offline run executed the Thumb call sequence from 0x5031e4 and the original ARM fill routine. All 72 target bytes were cleared and four sentinel bytes on each side stayed intact. Both wait-helper selections then advanced with a zero threshold and their initialized words. This establishes that the words start clear on this initialization path. Which operation can set them after initialization and what clears them during normal operation remain unverified.

### Checked OSD repeat-buffer writes

At firmware file offset 0x41d904 the checked writer calls 0x41c3b4 to read channel register +0x1c. Bit 14 clear selects the low-bit mask 7. Bit 14 set selects mask 1. It applies that mask to each of the three 32-bit addresses in the input record at +8, +0xc and +0x10. An invalid address returns -8 before any MMIO writes. The observed alignment requirements are 8 bytes with the bit clear and 2 bytes with it set. The physical mode represented by bit 14 remains open.

For accepted addresses, 0x41c18c writes the two packed repeat fields to channel +0x50, then the three addresses in order to +0x54, +0x58 and +0x5c. It reads back +0x5c before returning. The checked routine reads only +0x1c and that final readback. A successful return therefore establishes that the writer accepted its inputs and issued the stores. It supplies no observed frame completion or reuse fence.

Offline runs instrumented the saved current-body instructions for both OSD channels, both bit-14 states and isolated low bits in each address. The [reproducible VPH/AIF audit](data/vph-aif-contracts.json) independently tests 48 corresponding combinations on the reference image and verifies the return, read addresses and exact write sequence. Diagnostic logging is stubbed in the exercise. Physical latching and consumer ownership remain open.

### Native AIF stop sequence and timeout

The stop routine at file offset 0x41d978 clears bit 0 of channel +4, clears bit 0 of channel +0, then sets bit 30 of channel +4. It polls bit 31 of channel +4 through 0x41c2a8. The path tested here uses the existing 0x22b sentinel in the per-channel word array at firmware VA 0x643eb19c. An alternate event-handling path can return an earlier error and was outside these runs.

If the status bit remains set, the routine makes synchronous direct OSAL calls to endpoint 0x910041 between checks. The current-body LiRo callback relocation and wrapper at 0x19684 bind this call to osal_snd_sync_direct. The fixed call limit is 21. If the loop reaches that limit, the routine logs the stop timeout and returns -7. It sets bit 31 of channel +8 on both the success and timeout paths. A write to +8 alone therefore cannot establish successful stop.

Six offline runs covered both OSD channels with the bit clear initially, cleared after two intercepted OSAL calls and remaining set. The original firmware produced returns 0, 0 and -7 respectively, and the three start-of-stop register writes plus the final +8 write appeared in order in all six runs. Timing and hardware status effects were simulated. The meaning of the OSAL service, elapsed timeout and the point at which the physical buffer becomes reusable remain open.

### Timer request between AIF stop polls

The endpoint used by the AIF stop loop is registered by the saved utimer.ko (SHA-256 fad635877d64376d4d90670f3788d93772cfcab8f60e5760fb6a9ee1d9235ca9). The registration routine at ELF .text+0x19c0 registers 0x910041 with utimer_kif_delay at .text+0x18b0. The adjacent 0x910040 and 0x910042 bindings are the alarm and counter handlers. An offline execution resolved the function-pointer relocations and intercepted the three registration calls to verify the endpoint-to-handler arguments.

The original AIF firmware constructs a 40-byte direct-send record. Running the code from 0x41d9e6 to the send verified the complete record (ten little-endian words): 40, 0, 0, 0, 1, 0, 1, 0, 1, 0. The saved OSAL driver takes the payload from record +0x10. The timer handler therefore sees operation 1, a 64-bit deadline of 1 at payload +8 and time mode 1 at payload +0x10. Operation 1 calls utimer_udelay. Time mode 1 interprets the value as an absolute system-counter deadline. Mode 0 adds the current counter to form a relative deadline. The counter path in the timer module calls hwtimer_read_clock_cpu with CPU 0.

Two offline runs executed the original ARM timer handler with intercepted counter reads. With the stop request's absolute mode and counter already at 100, it returned success on the first comparison at 100. With mode 0 as a control, it polled until 101. Once the live counter is at least 1, the absolute request imposes no additional wait for a future timer value under this binding. The AIF limit of 21 calls is a retry bound. Its elapsed time depends on OSAL and execution overhead. The live timer module hash and queue binding have yet to be captured.

### Alternate AIF stop branch and secondary register handshake

When the per-channel word at 0x643eb19c is other than 0x22b, the stop routine additionally calls 0x41ddec. It passes an index obtained from the per-channel word array at 0x643eb40c. This index is distinct from the channel argument supplied to the outer stop routine. The helper validates its index and checks a per-index firmware word before touching MMIO.

For an admitted index N, the helper reads and writes one byte at 0xf2802000 + (N << 4). It clears bit 0, then checks bits 1 and 0. If either still reads as set, it retries through the same 0x910041 timer transport, up to three calls. The final operation sets bit 0 again. Exhausting the retry count returns -7 and still issues that final set. The hardware name and ownership of this register bank remain unconfirmed.

Six offline runs directly supplied indices 0x3b and 0x3c, producing byte accesses to 0xf28023b0 and 0xf28023c0. With status already clear, status cleared after two mocked timer calls, and persistent status, the observed results were zero, zero and -7 respectively. These synthetic indices test the address arithmetic. The actual per-channel index mapping and predicate values during shooting were not sampled.

Two separate runs of the outer stop routine supplied a synthetic index through its per-channel array. With a mocked zero result from the secondary helper, the outer routine continued to the primary status check and final channel +8 operation. With -7 it restored the 0x22b software sentinel and propagated the error before that final write. This differs from the primary polling timeout, which still issues the +8 operation.

### The secondary stop handshake depends on setup mode

The initializer at file offset 0x41d6f0 fills 156 entries in both software arrays. At firmware VA 0x643eb19c it stores 0x22b, and at 0x643eb40c it stores 16. The setup routine at 0x41d754 always resets the first word for the channel to 0x22b after successful setup. Configuration byte +5 equal to 3 is the branch that replaces it and writes configuration byte +4 into the secondary index array. That branch first writes 0x29a and then uses the task ID returned via the get_tid callback if it succeeds. A later call to 0x41d978 therefore selects the secondary handshake based on the software state and passes the index from configuration byte +4.

Offline execution checked all initializer entries and exercised successful setup for both OSD channels with modes 0, 2 and 3. Modes 0 and 2 left the sentinel at 0x22b and did not update the index. The mode-3 test supplied index 7 and a mocked task ID of 0x345 and observed both values in the arrays.

The OSD DMA producer at 0x4b5818 supplies config mode 2 for source addresses in 0xa0000000..0xafffffff or 0xe0000000..0xefffffff, and mode 0 otherwise. It uses either 0x3b or 0x3c according to its route argument. Six offline runs stopped at entry to setup and observed inputs for both routes across addresses in and out of those regions. A successful setup through this producer leaves the channel on the primary stop path. The hardware still needs to establish when a stopped buffer is physically reusable.

### OSD producer continues after a setup rejection

The checked AIF setup at file offset 0x41d754 returns -3 if bit 0 of channel +0 reads set. The OSD DMA producer at 0x4b5818 calls that setup and then replaces its result with the channel argument for the next operation. The producer also continues after the offset and repeat calls without branching on their returns. It tail-calls the channel mode setter, so its final return does not expose the earlier setup results.

Four offline runs executed the current-body producer tail with both routes and both values of channel bit 0. The first inner call returned zero with the bit clear or -3 with it set. In the latter case the initial source and size writes at +0x20 and +0x24 were skipped. The next calls still wrote offset/count, repeat and geometry fields, including the 31-bit buffer address at +0x4c. The tests used aligned inputs, so the checked offset and repeat calls each returned zero in all four runs. This is a partial update path in the firmware. Which fields latch while the channel bit is set, and on which frame boundary, remain unverified.

### OSD input geometry, byte stride and reverse row traversal

The caller of the DMA producer starts at 0x4b56ac with a route selector in r0 and a descriptor pointer in r1. On the tested branch, the descriptor carries a base address at +0, row pitch in pixels at +4, horizontal and vertical starting coordinates at +8 and +0xa, width at +0xc and height at +0xe. The pitch, coordinates and dimensions are unsigned halfwords. The caller rounds width upward to a multiple of four in place. It uses a separate adjustment for the minimum transfer width and 128-byte packing. A route-1 special case for descriptor word +0x1c equal to 1 changes the address formula and was outside these geometry tests.

The preprocessing helper at 0x805240 sets bytes per pixel to 2 when descriptor word +0x10 is zero and 4 otherwise. It selects a row step of two if byte +0x16 of its derived timing record is 2 or 3, or one for other values. These storage sizes do not yet give the component order or alpha encoding. Twenty-four offline runs verified both output bytes with the original instructions and a supplied timing-record result.

In the ordinary geometry branch the start pointer is base + bytes_per_pixel × (pitch × y + x). For a nonzero word at descriptor +0x20, the caller adds (height−1) × pitch × bytes_per_pixel and negates the row increments. The eight offline geometry runs used x=5, y=3, pitch=672, height=480, four bytes per pixel, and row steps one and two. Both widths 639 and 640 entered the DMA producer with rounded width 640 and a horizontal transfer count of 2560 bytes. The row increments were distinct from that count because the source pitch was 2688 bytes. Forward and reverse traversal started at 0x28201f94 and 0x2833c514 respectively for base 0x28200000. The line count argument was 479 with step one and 239 with step two. The tests supplied the helper outputs to isolate the geometry arithmetic. The actual pixel format and route selected during shooting remain open.

### OSD format selection and mixer-to-channel start order

The original OSD callers at 0x4b62ee and 0x4b6394 call geometry and DMA setup, then call 0x4b5b18 with the same descriptor. Route 1 pairs channel 0x3b with the Output 0 mixer, and route 0 pairs channel 0x3c with the Output 1 mixer. The format routine converts descriptor word +0x10 to a boolean. Route 1 writes it to bit 0 of 0xf3440404. Route 0 writes it to bit 0 of 0xf3440414. These are read-modify-write operations. Six offline runs used descriptor values 0, 1 and 0x1234 and verified both destinations and preservation of the other bits. The same descriptor word selects 2 or 4 bytes per pixel in the geometry path. The exact component ordering and encoding remain open.

After geometry and format, the route-1 tail at 0x4b62fa checks firmware word 0x6441df58, and the route-0 tail at 0x4b63a0 checks 0x6441dee4. With the respective word equal to 1, the tail sets mixer bit 1 at 0xf3440144 or 0xf3440184, then enters the checked AIF start at 0x7dc0f6. The start routine reads channel +0 bit 0. A clear bit leads to setting it and returning zero. A set bit returns -3 without writing the AIF channel. Four offline runs executed the original tail with both routes and both bit states. The observed order was mixer first, channel second when start succeeded. With -3 only the mixer write occurred. The selected mixer pairing is now verified in software. Neither test establishes which physical output drives the rear glass during shooting.

### Stock framebuffer profiles identify three software formats

The body-matched libObj.so contains 23 framebuffer profile records at ELF VA 0x13ee924 with stride 0x28. The GOT entry at 0x13dad54 resolves to that table. The indexed name-pointer table begins at VA 0x13eecbc. ELF relative relocations bind the GOT and string pointers. Every record's first word matches its name index, and the width and height at +0x14/+0x16 match the corresponding name.

| Stock profile name suffix | Bytes per pixel at +0x1c | Input format index at +0x20 | Format compared during profile selection at +0x24 |
| --- | --- | --- | --- |
| RGBA4444 | 2 | 1 | 3 |
| RGB565 | 2 | 6 | 2 |
| RGBA8888 | 4 | 2 | 0 |

The profile selector around 0x7002d8 checks width and height, calls the translation routine at 0x6fd2c0, and compares its result against +0x24. All 23 records were checked by executing that lookup in the identified libObj.so with each record's input format. The three 640×480 records without memory-placement suffixes have indices 2, 3 and 4 respectively. The table establishes that Sony distinguishes RGBA4444 from RGB565 despite their equal storage width. These are the library's framebuffer profile fields. A mapping to the lower-level OSD format record, channel bit positions in memory, and the profile active on the rear LCD still need evidence.

### Stock SenserIf carries the framebuffer profile ID into a message

The body-matched libObj.so path at ELF VA 0x700332 chooses a framebuffer profile ID. For a matched profile, the caller takes the first word of the selected 0x28-byte profile record. On the fallback branch, input format index 2 selects ID 4 (640×480 RGBA8888). Other input indices fall back to ID 2 (640×480 RGBA4444). The code logs those two fallback choices by name.

The library writes the profile ID at offset +0x18 in its 32-byte input record and calls 0x6fb28c. That routine constructs a message for endpoint 0x0080003b. For one input record its allocation is 76 bytes. It sets message byte 0 to 5, copies the 32-byte record to +8, and writes record count 1 at +0x48. The caller's distinct word 0x103 appears at message +0x18. The profile ID appears at message +0x20. ELF PLT symbols identify the allocation and send as osal_valloc_msg_wait and osal_snd_msg.

Six offline executions used original selector and message-building instructions, with allocator, selected-record lookup, memcpy and other external effects intercepted. With supplied matched records the profile IDs observed at the send boundary were 2, 4 and 3 for input formats 1, 2 and 6 respectively. Fallbacks for those inputs produced 2, 4 and 2. The profile ID carried here differs from the two- versus four-byte selector in the VPH descriptor. The receiver for this specific message and its mapping to the physical OSD channel remain open.

### The type-5 receiver uses storage width for the Dataflow OSD selector

The identified libObj.so command dispatcher at 0x7007d8 handles inner non-pin messages tagged with source 0x0080003b through 0x6f76f4. Message type 5 passes the record at message +8 and the count at +0x48 to the OSD builder at 0x6fe064. This path uses the type-5 byte rather than the 0x1000 pin-message branch.

On the sender side, 0x69d144 uses the requested input format index to look up a storage-width halfword. The type-5 caller at 0x7002ae places that halfword at input record +0xc (message +0x14). It yields 2 for input formats 1 (RGBA4444) and 6 (RGB565), and 4 for input format 2 (RGBA8888). The receiver reads this field and calls SetData_Image_Sel with selector 0 for 2 bytes or selector 1 for 4 bytes. It then commits the assembled entry through SetEntry_OsdImageSizeInfo. These call targets are identified by the ELF PLT symbols.

Nine offline runs independently varied the input format and the carried profile ID (2, 3 and 4). They executed the original size lookup and the dispatcher tail and OSD builder, with external Dataflow and file effects intercepted. Every run reached the entry commit. The selector depended only on the storage width, and neither this branch of the dispatcher nor the builder read the profile ID at message +0x20. In this path RGBA4444 and RGB565 therefore share the same Dataflow image selector. The RTOS consumer of the committed entry and any other field that distinguishes those two component layouts still need tracing.

### The RTOS VDF consumer, VPH OSD queue 0x6603c4, and IRQ 102/110 completion callbacks

Instruction inspection and relocated Unicorn execution extend the verified chain from `libObj.so` into the RTOS VDF and VPH handlers in [vph-aif-contracts.json](data/vph-aif-contracts.json) and [grm-contracts.json](data/grm-contracts.json):

- **`libObj.so` type-5 builder (`0x6fe064`) and Dataflow container serialization:** For each 32-byte record (`count` downward to `0`), `0x6fe064` calls 11 `C_DataflowInfra_Entry_OsdImageSize` setters via PLT: `+0x00/+0x02` (`Target_OffsetH/V`), `+0x04/+0x06` (`Target_SizeV/H`), `+0x08/+0x0a` (`SizeV/H`), `+0x0c` bytes per pixel (`2 -> Sel 0`, `4 -> Sel 1`), `+0x14` (`Address`), constant `1` (`Read_Orientation`), and `+0x10` flags (`flags & 3 -> Out_Target`, `(flags >> 10) & 1 -> Channel`, and `(flags & 0x10) != 0 && bpp == 4 -> Trans_Type 1` else `0`). `0x6fe3b0` translates the shared buffer and sends it via `0x6fa5e0` (`DataflowInfraPin::Send` PLT `0x109344`). Relocated execution of `C_DataflowInfra_StdData_OSD::C1` (`0x238dc`) and `SetEntry_OsdImageSizeInfo` (`0x2392c`) in `dataflowInfraFramework.so` produces a 32-byte `SSOS` header (`DataFormatVersion = 1`, `EntrySum = 1`, `FirstEntryOffset = 0x20`), a 32-byte `ETRY` entry header (`CateId = 0`, `CateVersion = 0`, `DataOffset = 0x40`, `DataSize = 0xa0`, `NextEntryOffset = 0`), and the `0x94`-byte `PIN_OSD_IMAGE_SIZE_INFO` payload starting at `+0x40`.
- **RTOS `VDF::VdfOsdImageSizeProcessor` (`0x15bfb0`, vptr `0xfbbc00`):** Executing original instructions in Unicorn against `SubsystemAccessor` (`vptr 0xfbd3b0`) reads `Image[0].Sel` (`+0x14` -> `sub_obj + 0x1a8c`), `Image[0].Trans_Type` (`+0x1a` -> `sub_obj + 0x1a90`), logs format tag `r1 = 0x4444` (`Trans_Type = 0`) or `0x8888` (`Trans_Type = 1`) via `0x72f47c`, branches to `vptr + 0x14` (`0x15be88`) or `vptr + 0x18` (`0x15bf1c`), and calls `0x721386` (`Target_SizeH == 0x1aa` -> `sub_obj + 0x1a88`). Neither field alone distinguishes RGB565 vs RGBA4444 component layouts on `Trans_Type = 0`.
- **VPH OSD queue (`0x006603c4`) and route fan-out (`0x498aa4`):** File offset `0x497550` carries OSAL endpoint `0x006603c4` (companion `0x006605a9` at `0x497554`). Executing `0x498aa4` (`staging 0x64419e70` -> `dst 0x6441af40`) across `[staging + 0x128]` values `0`, `1`, and `2` verified that `0` copies the 56-byte descriptor (`staging + 0x100`) to `dst + 0x378` and sets `dst + 0x374 = 1` (Route 0 / `OSD1` at `0x4b6340`), `1` copies it to `dst + 0x33c` and sets `dst + 0x338 = 1` (Route 1 / `OSD0` at `0x4b6298`), `2` populates both routes, and tail `0x80239c` clears staging dirty flags.
- **VPH VSYNC IRQs 102/110 (`0x806294` / `0x806352`) and completion callbacks (`0x4b59ec` / `0x4b5a84`):** Interrupt table entries at `0xfcc4d0` (`irq = 102`, `0x806294`) and `0xfcc4e0` (`irq = 110`, `0x806352`) update `0xf3440038` bits `15:0` (`0x49b42c` -> `0x807230` -> `0x49360c`, bits 9 and 10) and call OSD completion handlers `0x4b59ec` (`OSD0` / Route 1) and `0x4b5a84` (`OSD1` / Route 0). Executing `0x4b6298` and `0x4b6340` verified latching of `[desc + 0x2c]` token and `[desc + 0x30]` callback into `(0xf5d191, 0xefb180, 0xe57eec)` and `(0xf5d194, 0xefb15a, 0xe57f88)`; executing `0x4b59ec` and `0x4b5a84` delivered the 16-bit token in `r1` (`cb(r0=0, r1=token, r2=route)`) and cleared the pending flag (`0xf5d191`/`0xf5d194 = 0`). Consistent with Output 0 active in the November 19 Senser snapshot (`186` reads, all 13 `av-cam.bin` code slices matched), `GIC liro-102` advanced by `11` in `0.2198 s` (`~50.0 Hz`) while `GIC liro-110` remained at `0` with Output 1 disabled. The live readback also observed `0xf3440404 = 0` (`OSD0` bit `0 = 0`, 2-byte storage width), `0xf3440048 = 0x10010b77` (`ubfx bit 10 = 0`), `0xf3441004 = 0x00000101`, `OSD0` AIF `0xf3441300 = 3` (then `2` in repeat samples), `0xf3441304 = 0x80000000`, `0xf3441310 = 0x22c99600`, and `0xf344131c = 0x00002a0b` (`bit 14 = 0`, 8-byte alignment mask). The pixel component bitfield in memory and normal-shooting state remain to be captured.


### Stock OSD0 descriptor and completion readback

The 19 November pinned SSH session after a camera restart used bounded read-only transfers from `/dev/mem`. LiRo reported `adr = 0x635c6000`. The running `liro.ko` hash matched the saved body module, whose `os_phys_to_virt` and `os_virt_to_phys` establish the low-bank `VA = PA + 0x60000000` mapping used here. Four live instruction ranges at the translated physical addresses matched both saved firmware images before reading descriptor state. The callback body and its live GOT entry were checked separately. [Raw word transcript](../../research/device/zve10_hardware_map/evidence/20261119-stock-osd-descriptors.txt)

- File offset `0x4996b2` calls the bounded queue consumer `0x49cfb8` with handle from VA `0x6441cdac`, staging VA `0x64419e70` and size `0x2d0`. The word at staging +0 selects which block receives the fan-out from `0x498aa4`: zero selects VA `0x6441af40`, nonzero selects `0x6441919c`. The call at `0x498212` supplies both blocks' Route 1 descriptors at block +0x33c, and their dirty bytes at +0x338, to the OSD0 setter. Both 60-byte slots were sampled. The first held the live descriptor and the second stayed zero in this session. The sampled dirty bytes were zero.
- The live descriptor showed `+0x04 = 0x01e00280` (640-pixel pitch in the low halfword), zero source x/y, `+0x0c = 0x01e00280` (640×480), `+0x10 = 0` (two bytes per pixel), and zero at +0x1c and +0x20. On the verified ordinary geometry branch this is a 1,280-byte row pitch and a 614,400-byte frame. The base at +0 cycled among `0x1968f000`, `0x19725000`, `0x197bb000`, and `0x19851000` in physical RAM. Adjacent bases are one frame apart. Later AIF address samples all fell within those four spans, even when the separately sampled descriptor named a different span.
- The descriptor's token `0x000e` and Thumb callback `0x63733989` matched the retained latch values. The callback file offset is `0x16d988`. Its verified instructions increment a byte modulo 256 at VA `0x64246d49` via the GOT entry at VA `0x6463d700`. That byte advanced during capture while IRQ 102 also advanced. The pending byte happened to be clear at the sample points. The callback uses the status and token in its downstream dispatch, so a counter increment alone does not distinguish a successful frame from any other invocation. The observations establish the rotating scanout allocation and a live completion path. They leave exact component packing, producer release timing and panel-specific routing open.
