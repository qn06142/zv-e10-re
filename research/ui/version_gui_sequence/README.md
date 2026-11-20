# Version-screen sequence demonstration

18 November 2026. Historical revision 1, superseded after the owner reported that only Up worked and Center exited the menu. See the [installed direction-only revision 2](v02/README.md). Offline ARM-verified GUI candidate using the [owner-observed key pattern](../version_gui_keys/owner-key-mapping-20261118.json). The candidate is installed and fully byte-verified; physical sequence behavior is pending. No payload loading or OS handoff exists.

## Intended on-camera interaction

Open Setup → Version in normal shooting. The body-version field should show GUI IDLE. Press and release **Up, Down, Up, Down, Center** individually. Intermediate markers show SEQ 1/5 through SEQ 4/5; the final Center displays CONFIRM?. Release Center, then press it again to display ARMED OK. This is a confirmation marker in the version field, not a separate dialog and not an OS launch.

A hold event or duplicate down cannot advance the sequence or confirm. A fresh non-confirm key at the prompt cancels. After ARMED OK, another fresh key clears the demonstration. Leaving the Version screen resets progress through the original Exit operation. No time-based expiration is implemented; idle time alone does not cancel a partial sequence while this screen remains open.

The local event assumptions are Center 0x15010042, Up 0x15010052, Down 0x15010062, Right 0x15010072 and Left 0x15010082. Suffix 1 releases the per-key pressed latch and suffix 4 marks a hold. The owner reported the low key/state pattern; the full prefix is carried from the mapper and remains part of the hardware check. Remote-family inputs and unrelated input keys cancel progress and cannot advance it.

## Implementation and checks

The [button mapper](../version_gui_keys/README.md) supplies the original-instruction fixture and ELF injection helper. The sequence uses the same constructor, state-1 transform and primary formatter boundaries, and the same RX-segment/RW-state separation. Private state grows to 432 bytes. The constructor copies the primary vtable with its RTTI header to private RAM and wraps that instance's Exit slot. It saves the resolved original Exit pointer, clears progress on Exit, and calls the original pointer. The remaining virtual entries and secondary subobject retain Sony behavior.

Recognized sequence steps return neutral event 0 after recording progress; unrelated normal input retains the original transform result. Original Version-screen main instructions were exercised with neutral event 0 and leave transition outputs unchanged. This checks the local state transition; it does not simulate the complete application dispatcher.

[Offline verification](offline-verification.json) executes original ARM constructor, transform and layout code at two load biases with controlled widgets/imports. It checks ordered steps, wrong keys, holds, duplicate downs, separate fresh confirmation, explicit cancellation, imported Exit chaining/reset, six state/boot-element scope controls, twelve output-capacity controls, two neutral-event transition controls, stack/callee-saved registers, model version words and bounded memory writes. A regression run reproduces the prior button mapper's exact output SHA-256 after shared-helper changes.

External GUI functions and imported Exit are mocked. The new hook frames lack unwind descriptors, so exceptions across them remain untested. Cached/multiple Version instances and event delivery on hardware still need observation. These are GUI candidates; offline tests do not certify recovery after a system takeover.

## Reproduce

From the repo root with pyelftools, Unicorn and GNU Arm Embedded tools:

```powershell
.venv/Scripts/python.exe -B research/ui/version_gui_sequence/build.py --input .local/dumps/camera_2025/usr/usr/lib/viewUnified6.so --out .local/out/version-gui-sequence
```

The base helper accepts the exact stock or 88.88 marker input and normalizes to stock. The deployed input mapper is a separate prior revision, not a generic patchable input. Generated Sony-derived binaries remain local. The manifest records normalized SHA-256 source identities, including shared helpers. The build invalidates the previous success manifest before compilation and publishes the candidate only after verification.

## Deployment

Use the same checked backup, hard-link, staged atomic replacement and full-readback method as the mapper. Preserve its exact installed input and the earlier factory backup. A full restart is required before observing the new code. No change to av-cam.bin, persistent boot selection or USB behavior is part of this demonstration.


## Installed checkpoint

[Installation record](installation-20261118.json): the complete installed library and hard-linked prior mapper backup passed byte-for-byte readback. Storage was synced, /usr returned read-only, and av-cam.bin matched its pre-install hash. The owner was asked to fully restart and verify CONFIRM? followed by ARMED OK with a separate fresh Center press. This installation establishes bytes only; the GUI sequence remains unverified until that observation.
