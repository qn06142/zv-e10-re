Flashed: a version string in DeviceInfo.xml

Date: 2026-09-28. Second hardware-verified change, and the first one delivered in
a single command.

## What changed

`/usr/share/pmbp/DeviceInfo.xml`, a 517-byte Apple-plist XML with CRLF endings:

```xml
<key>Version</key>
<string>1.3.00.19200</string>     ->  9.9.99.99999
...
<key>version</key>
<string>1.0.00</string>           ->  9.9.99
```

| | |
|---|---|
| original | `325881bdde84eb36d006ba13efb54eb5` · 517 B |
| patched | `9b2d8cc0f59d9b82c69e1f8e2478e545` · 517 B |
| changed | 12 bytes, length identical |
| `/usr` mount | back to `ro` |

Verified three ways on the device, not inferred: whole-file md5 equals the hash
computed locally from the intended edit; the live file was confirmed to be the
original `325881bd…` *before* anything was written; and 12 bytes read at offset
159 come back as `9.9.99.99999` with md5 `5c761a7f18235cfd92025af5e23f6269`.

## How it was delivered, and why this one was easy

The whole file is 517 bytes, so base64 is 692 characters and the transfer is a
single 739-character command — inside the ~1022 limit with room to spare. No card
staging, no chunking, no `dd` splice, and none of the `/tmp` problems. The
sequence was:

```
busybox echo <692 chars> | busybox base64 -d > /tmp/di.xml    # verify md5 first
busybox mv /tmp/di.xml /usr/share/pmbp/DeviceInfo.xml          # atomic rename
```

The link dropped twice during this — once after the remount, once after the
`mv` — and both operations had already completed. That is the argument for
staging to a temp file and renaming: an interrupted command is not an
interrupted install, and re-reading the state afterwards is all that is needed to
know which side of the rename we are on.

## What was dug out of the code to find it

The on-screen version is **not** in this file. `viewUnified6.so` contains:

```
LG_viewversionnumber::LayoutVERSION
LG_viewversionnumber::LayoutINITIAL_VERSION
LG_viewversionnumber::LayoutLAYOUT_VERSION_INFO
%2d.%02d
ViewVersionNumber
```

So the Version screen formats **two integers** as `major.minor` — displayed as
something like ` 1.00`. `1.3.00.19200` is a four-part version in a different
scheme, and that value appears nowhere else in the tree, so it is the PMBP
(PlayMemories Bluetooth) service's own descriptor.

`LayoutVERSION` is entirely unexported — only its five RTTI typeinfo names are
visible, so there is no symbol to read and no string to match. Finding the two
integers means disassembly, not a search, and that has not been done. A camera
whose *displayed* firmware version we can change is therefore still open, and
this change is a version string but probably not a visible one.

The version strings that were found and rejected as targets, with reasons:

- kernel module versions (`usbg_sen.ko` `01.05.000`, `kikilog.ko` `01.00.000`, and
  six others) — not displayed, and in loadable modules
- `Sony_DI_Icons.ttf` `Version 0.2023062610` and the `.ltt` bundles'
  `fileversion=02_08_123_00.20230626.01` — font metadata, not the camera
- `Dongle Host Driver, version 1.141.67` in `bcmdhd.ko` — the wifi driver, and it
  is printed in the kernel log at boot, which is not the camera's screen

## A note on busybox grep

`busybox grep -c 9.9.99.99999` on the patched file returned **0**, while the
whole-file md5 matched the patched build exactly. The two contradict. The byte
read at offset 159 resolved it: the content is correct and `grep` is wrong,
most likely because of the CRLF line endings combined with `.` being a regex
metacharacter in a pattern that was meant to be literal. The lesson is the one
this project keeps learning: a hash that agrees with the intended edit beats a
text tool that disagrees with it, but only if you go and check which one is
lying rather than assuming.

## Rollback

The original is 517 bytes, so it fits the same one-command path:

```
busybox echo UGxB...  | busybox base64 -d > /tmp/di.xml
busybox mv /tmp/di.xml /usr/share/pmbp/DeviceInfo.xml
```

Original md5 `325881bdde84eb36d006ba13efb54eb5`, and the file is also in the
local dumps at `dumps/camera_2025/usr_share/pmbp/DeviceInfo.xml`. The card also
still holds a full copy of the string-table restore.
