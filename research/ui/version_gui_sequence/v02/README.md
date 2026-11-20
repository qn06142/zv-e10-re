# Direction-only Version-screen sequence, revision 2

18 November 2026. Installed, byte-verified and owner-confirmed to reach ARMED OK through the normal GUI. This revision follows a hardware failure of the [first sequence](../README.md): the owner reported only Up worked properly and requested that Center retain its exit function.

## User interaction

After a full restart, open Setup → Version. Press and release **Up → Down → Left → Right**, then **Up** to confirm. Expected display:

| Completed input | Body-version field |
| --- | --- |
| None | UP FIRST |
| Up | 1D xxxxx — next direction Down |
| Down | 2L xxxxx — next direction Left |
| Left | 3R xxxxx — next direction Right |
| Right | UP=YES? |
| Subsequent Up press | ARMED OK |

The five hexadecimal digits are the low 20 bits of the last accepted direction event. They preserve the source-family digit and key/state suffix for diagnosing a failed step. Center always keeps its original transform result and normal exit behavior; it is not a sequence or confirmation key. This is a marker-only demonstration, not an OS launch.

## Corrections and limits

The first implementation accepted only family 0x1501 and cleared progress on unrelated 0x15-family notifications. Either restriction could explain lost progress; neither has been established as the hardware root cause. Revision 2 accepts both 0x1501 and 0x1502 for directions, matching the mapper's capture families. Those families are not classified as local versus remote here because their transport origin was not established by the owner's suffix-only report.

Directional press, release and hold events are consumed only while the Version object is in state 1 and boot element 1. A fresh suffix-2 press advances; duplicate downs and suffix-4 holds do not. Suffix-1 releases clear the latch, and switching directions replaces a missing prior-key release. Repeated final Right never confirms: confirmation requires Up. Unrelated input notifications preserve progress. A wrong direction cancels or restarts at Up. Center key-down clears progress and passes through; the existing Exit wrapper also resets state. Idle time alone does not expire a partial sequence.

The [offline verification](offline-verification.json) exercises original ARM constructor, transform and layout code at two load biases. It includes mixed-family streams, missing prior releases, background notifications, hold/duplicate rejection, a distinct confirmation key, original Center transform results, Exit chaining/reset, scope controls, neutral-event transition outputs and bounded text buffers. Imported GUI and Exit calls remain mocked. This is not a full application-dispatch test. New hook frames still have no unwind descriptors; exceptions across wrappers and multiple/cached Version instances remain unverified.

The constructor/vtable/RAM-state and ELF injection architecture is inherited from revision 1 and the [button mapper](../../version_gui_keys/README.md). No file I/O, payload loading, kernel transition or OS handoff is present in the GUI payload.

## Reproduce

```powershell
.venv/Scripts/python.exe -B research/ui/version_gui_sequence/v02/build.py --input .local/dumps/camera_2025/usr/usr/lib/viewUnified6.so --out .local/out/version-gui-sequence-v02
```

Installer source (local checkout: `research/ui/version_gui_sequence/v02/install.sh`) guards the exact first sequence input, preserves its mapped inode with a hard link, stages a distinct file, atomically replaces the library pathname and restores /usr read-only. [Installation record](installation-20261118.json): complete installed and backup byte readbacks passed; /usr is read-only and av-cam.bin matched before/after hashes. The prior sequence is retained at /usr/share/version-gui-sequence-v02/viewUnified6.previous-sequence-v01.so. The factory GUI backup and prior button mapper backups remain separate. Generated Sony-derived binaries stay in ignored local storage.


## Owner-confirmed hardware result

On 18 November, the owner answered Reaches ARMED OK to the full-restart check for Up → Down → Left → Right followed by Up confirmation. This establishes the direction-only GUI sequence and confirmation marker on the physical camera. The response did not separately test Center exit, duplicate/hold rejection or re-entry reset; those retain their source/offline evidence. No independent screen capture or post-restart boot/mount readback was collected. The installed payload still performs no loading or OS takeover.
