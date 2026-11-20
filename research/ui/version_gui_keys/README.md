# Version-screen button mapper

18 November 2026. Display-only input probe installed and byte-verified through Senser. The normal GUI observation and physical button mapping are pending. This follows the [owner-confirmed 88.88 marker](../version_gui_probe/README.md). It implements neither a launch sequence nor an OS handoff.

## On-camera check

Fully restart with USB disconnected and a brief battery removal, then open Setup → Version. The body-version field should initially show GUI KEYS. For accepted local input families it should show E: followed by six hexadecimal digits, for example E:010042. Press Up, Down, Left, Right and Center individually and record the code shown for each. If normal button behavior leaves the page, reopen it. The probe preserves the original transform results; it does not swallow navigation or globally intercept input.

These strings are expected from the offline test. Physical rendering, button identity, filtering and event ordering need owner observations. No specific numeric code is labeled as a physical button yet.

## Implementation

- The Version factory's constructor call is redirected to a wrapper that invokes the original constructor and resets 16 bytes of private zero-initialized state.
- Only this Version screen's state-1 transform pointer at virtual address 0x8c7a0 is redirected. The original transform still runs, and its result is returned unchanged.
- Capture is limited to event families 0x1501 and 0x1502, with a valid Version object in state 1 and boot element 1. It records the raw event and calls the original screen layout callback on the existing GUI thread.
- Only the primary version formatter call at 0x41872 is redirected. The new formatter writes at most the supplied capacity, formats the code as text and leaves the underlying version words unchanged.
- The recipe adds an RX load segment at virtual/file offset 0xa0000, containing the relocated six-entry program-header table and position-independent hooks. It retains the original ARM exception-index segment, dynamic table and non-executable stack. The existing RW zero-initialized data segment is extended for private state at 0x97b30. No existing function body is reused as a code cave.
- New hook frames have no unwind descriptors. Exceptions unwinding through these wrappers have not been tested. External GUI APIs and the unknown-event fallback are controlled mocks in the offline fixture; they do not establish every runtime behavior.
- The payload has no file operations, allocation, kernel transition or OS-loading code. The existing installed Sony boot target is unchanged.

## Reproduce and verify

From the repository root, with pyelftools, Unicorn and GNU Arm Embedded tools:

```powershell
.venv/Scripts/python.exe -B research/ui/version_gui_keys/build.py --input .local/dumps/camera_2025/usr/usr/lib/viewUnified6.so --out .local/out/version-gui-keys
```

The recipe accepts only the exact stock input or the verified 88.88 marker input, normalizes to stock and builds a fresh candidate. Generated Sony-derived files stay under ignored local storage.

[Offline verification](offline-verification.json) executes original constructors, event transforms and layouts. Twenty-six event cases across two load biases preserve the tested transform return values; local input events reach controlled text widgets. Six state/boot-element controls suppress capture, two constructor resets clear history, the original relocation resolves the new transform pointer, and checks enforce stack/callee-saved registers and restrict writes to the object, private state and stack. External functions are mocked, including identity behavior for unknown-event fallback. This is not a complete GUI-framework or dynamic-linker test.

## Installation and rollback

[Installation record](installation-20261118.json) confirms complete candidate and prior-marker backup readbacks. The installer (local checkout: `research/ui/version_gui_keys/install.sh`) checks both identities, creates a hard-linked backup, stages a separate inode, atomically replaces the library pathname, syncs and returns /usr to read-only. All installation steps completed successfully. The earlier remount-busy problem did not recur. The exact current av-cam.bin hash was unchanged before and after installation.

The previous 88.88 marker is retained at /usr/share/version-gui-keys-v01/viewUnified6.previous-marker.so. The factory GUI backup is separately retained at /usr/share/version-gui-probe-v01/viewUnified6.stock.so. Host downloads preserve both prior inputs. A rollback must stage the chosen verified backup into a separate file on /usr, verify it, then atomically restore /usr/lib/viewUnified6.so and sync before a full restart. Do not copy over the active mapped inode in place or overwrite either backup. Read current hashes and mount state before any rollback.

[Access and recovery](../../../docs/ACCESS_AND_TOOLS.md). The next implementation milestone is a deliberate screen-scoped sequence and confirmation based on observed key codes; payload loading remains a separate later milestone.
