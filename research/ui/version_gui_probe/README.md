# Version GUI marker probe

18 November 2026. The 88.88 marker was installed, byte-verified and confirmed by the owner in the normal GUI. It has since been superseded by the [button mapper](../version_gui_keys/README.md). No OS handoff has been performed. Dated checkpoints below retain the earlier observations and limits.

## Result and limits

Located ViewVersionNumberToInstance in viewUnified6.so, resolved its constructor and screen-specific vtable, and followed its layout callback through the original ARM instructions. The marker recipe changes four instruction bytes so the primary version field in the tested boot-element-1 path formats as 88.88. It preserves the underlying version/model values. This is a visual probe, not a reported firmware version and not a button-sequence trigger.

The verifier executes the original layout callback and render routine in Unicorn. Controlled widget/model memory and mocked external GUI APIs record text assignments. Four current/offered-version combinations verify the primary marker, unchanged optional offered-version text, the same widget selection and restored stack/callee-saved registers. Controls verify unchanged states 0 and 3, unchanged boot-element-2 layout behavior, refusal of an already patched input, equal file length and exactly four changed bytes. Physical scanout, normal-shooting screen selection, event delivery and runtime library identity still need hardware confirmation.

[Offline verification](offline-verification.json) records the generated hashes and observed assignments. Never interpret it as a hardware result.

## Reproduce

Run from the repository root with pyelftools and Unicorn in the research Python environment:

```powershell
.venv/Scripts/python.exe -B research/ui/version_gui_probe/probe.py --input .local/dumps/camera_2025/usr/usr/lib/viewUnified6.so --out .local/out/version-gui-probe
```

The input is strictly guarded by SHA-256 e6459c22859d8978195baa1ef2e93ad6d5f4fcb3dd89c2c2f02c325b46616090. Generated Sony-derived ELF files remain under ignored local storage. The recipe does not upload, install, reboot or contact the camera.

## Recovered addresses

All addresses below are link-time virtual addresses, not live ASLR addresses. File offsets differ from virtual addresses in the library's writable/relocation segments.

| Boundary | Link-time address | Evidence |
| --- | --- | --- |
| Exported factory | Thumb 0x41235 | Allocates a 0x178-byte object and calls constructor 0x4108c. |
| Constructor | Thumb 0x4108d | Calls ViewBaseProduct constructor; installs vtable at object +0 and secondary table at +0x28. |
| Primary vtable address point | 0x8c7c0 | Constructor GOT slot 0x9033c contains table header 0x8c7b8, then adds 8. |
| Screen main callback | Thumb 0x41281, slot +0x120 | Calls ViewBase::GetEventId and reads state at object +4. ProductMain in viewUnified2 calls this slot at 0x59e678/0x59e67c. |
| Trigger-table selector | Thumb 0x41069, slot +0x124 | Selects a transform function using state at object +4 and calls View::requestTriggerTable. |
| Trigger function pointer table | 0x8c79c | State 0: null; state 1: Thumb 0x3f421; state 2: Thumb 0x3f58d. Key names remain unresolved. |
| Action dispatcher | Thumb 0x41579, slot +0x12c | Dispatches action indices 0 through 3. No payload loading behavior added. |
| Layout callback | Thumb 0x41a0d, slot +0x130 | State 1 calls 0x419d0, which selects render 0x417e0 for boot element 1 and 0x41710 for boot element 2. |
| Primary tested formatter | 0x41872 | Calls snprintf with 9-byte destination and format at 0x77518. |
| Version field sources | Object +0x154 and +0x158 | Packed words split into upper/lower 16-bit formatting arguments. Meaning must be tied to the physical screen. |

The first patch at file offset 0x41868 replaces sxth r2,r3 (1ab2) with movs r2,#88 (5822). The second at 0x4186e replaces asrs r3,r3,#16 (1b14) with movs r3,#88 (5823). No shared format string or generic input handler is overwritten.

The state-1 trigger transform recognizes several 0x1501/0x1502-family events. Their physical button mapping and whether the desired sequence survives focus/filtering must be observed in normal shooting. Do not label a numeric event as MENU, center or a long press from its value alone.

## Hardware checkpoint

The owner supplied SSH host 192.168.137.171. Two pinned-key SSH connection attempts timed out before authentication. No boot identity, live library hash or library mapping was obtained, and no camera file was changed. See [access instructions](../../../docs/ACCESS_AND_TOOLS.md) for the key/host-key setup; keep private keys outside the repository.

Next: establish SSH in normal shooting, preserve a same-body library backup and read back its identity, inspect whether this library is already mapped, then choose a deployment method that avoids changing pages under an active mapping. Confirm the marker physically on the Version screen and verify exit/re-entry and ordinary shooting. After that, observe the screen-scoped event transform and add a deliberate sequence plus confirmation. Do not infer a GUI trigger from Senser command acceptance.

[RAM iteration architecture](../../../docs/imaging/RTOS_ITERATION.md). The stock boot target remains the fallback; no RTOS, kernel or boot-selection change is part of this probe.


## Senser inspection on 18 November

The later authenticated Senser inspection verified a 589,336-byte live viewUnified6.so matching the guarded input SHA-256 exactly. A host backup was downloaded and verified against camera MD5 before and after transfer. [Inspection summary](senser-inspection-20261118.json).

im.elf PID 151 still mapped the library in this service session. Do not infer an absent GUI application from entering Senser, and never patch the mapped inode in place. wlan0 had only link-local IPv6 and no IPv4 address; /proc/net/tcp had no rows. These are service-mode observations, not an explanation of the previous normal-shooting network state.

Automatic approval review rejected the proposed persistent installation because explicit approval for this exact library replacement was required. No camera files were written. The prepared installer (local checkout: `research/ui/version_gui_probe/install.sh`) is source only and has not run. It expects the candidate at /log/version-gui-probe-v01/viewUnified6.gui-probe.so, guards both identities, preserves a stock backup under /usr/share/version-gui-probe-v01, stages a separate inode, atomically replaces the pathname, checks the installed hash and returns /usr to read-only. It does not reboot, change boot selection or replace av-cam.bin. Existing mappings retain the old inode until their users exit; a later load can see the new file, so use a restart before the GUI observation. Physical Version-screen output and normal boot remain unverified.


## Approved installation on 18 November

After explicit user approval, the marker was uploaded and installed through Senser. Complete readback verified the installed candidate and the camera's stock backup byte for byte; av-cam.bin retained MD5 90096db2c76148f4f9db5d104e5c608c. [Installation checkpoint](installation-20261118.json).

The installer's final read-only remount failed with EBUSY. A separate verification session confirmed all installed/backup bytes, synced storage and reproduced the remount error. im.elf PID 151 retains the original library inode 18287 as a deleted mapping. This is a likely explanation of the remount failure; an exact kernel-path audit was not performed. USB reconnects retained boot ID 1a4dd4b9-d4d6-4140-9522-e55a07914e39 and did not release that mapping. The owner has been asked for a full restart with battery removal, followed by a normal-shooting Version-screen observation. At this checkpoint /usr remains writable, GUI output is unverified and no OS takeover exists.

For later installer revisions, retain the original inode with a guarded hard link before atomic replacement; a copied backup preserves bytes but does not retain the inode referenced by an existing mapping. The checked-in install.sh remains the exact source used for this installation, including its failing final remount. Do not rerun it against the installed candidate: its stock-input guard will refuse it. Verify read-only mounts and the new boot identity when hardware access resumes.


## Owner-confirmed normal GUI marker

On 18 November, after the requested full restart and normal GUI navigation, the owner reported: body version is 88.88. This confirms the visible marker on the physical Version screen. The observation is owner-reported; no display capture or post-restart SSH/Senser boot identity and mount readback has been collected. The previous EBUSY belongs to the installation boot; the mount state after restart remains unknown. The installed change still only alters the displayed number. A deliberate button sequence, confirmation prompt, payload loader and OS handoff remain unimplemented.
