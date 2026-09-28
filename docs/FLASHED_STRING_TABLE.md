Flashed: the string table edit is on the camera and verified

Date: 2026-09-28. `zx` could not be used — see
`docs/WHY_THE_STRING_PATCH_IS_STUCK.md` for the four transports that failed.
The SD card unblocked it, and the mechanism turned out to be simpler than the
toolbelt.

## What is on the camera

| | |
|---|---|
| file | `/usr/share/app/string_english_f.uxc` |
| before | `349711603d2e16c1fc620e4e8bf30be0`, 349,020 bytes |
| after | `9853d47ad4197d3387f10babdc8728b9`, 349,020 bytes |
| changed | 24 bytes: `Playback` → `OPENCODE` at 0x041bb0, 0x0476dc, 0x04cbc0 |
| `/usr` mount | back to `ro` |

Verified on the device, not inferred: whole-file md5 equals the hash computed
locally from the intended edit, the length is unchanged, and an 8-byte slice at
0x041bb0 md5s to `04fbbbde1afb0c4bafde6ba5ce069ac6`, which is md5 of `OPENCODE`
and not of `Playback` (`8dc55bfc…`).

Three independent methods produced that same target hash before anything was
written: a direct byte patch, `sed` with a backreference, and line-addressed
`sed`. Two independent readings of the device produced the same before-hash.

## How it was actually delivered

The card mounts at **`/dev/mmca1` on `/tmp/sd`** — note `/dev/mmcca1` also exists
and is a *different* controller's partition 1, and `/proc/partitions` reports the
card as `mmca10` / `mmca10p1` while the node is `mmca1`. The mount point `/mnt`
is read-only, so `/tmp/sd` is the one to use.

With the source local to the device, no base64 staging is needed at all. The copy
is eleven `dd` appends of 32,768 bytes:

```
dd if=<card file> bs=4 count=8192 of=/usr/share/app/str.tmp      # first chunk
dd if=<card file> bs=4 skip=N count=8192 >> /usr/share/app/str.tmp
```

Everything is a multiple of 4 — the file length, and all three patch offsets — so
`bs=4` is exact and the chunk boundaries need no rounding.

Two properties make this safe to retry, which matters because the USB link
dropped once mid-sequence:

- `>>` never truncates, so an interrupted chunk leaves a *short* file rather
  than a corrupt one. Checking `wc -c` and resuming at `skip=size/4` is exact.
- the destination is a **temp file**, and the live file is only replaced by
  `mv`, which is an atomic rename within the same filesystem. The live file is
  never in a partial state, and the temp file's md5 was checked against the
  intended hash *before* the rename.

## Why the earlier failures were not about size

Three attempts died partway: 75,724 and 186,712 bytes into a 349,020-byte
splice, and `sed -i` on the live file which produced no change at all. The
common factor was not the byte count — 32,768 and 131,072 byte writes went
through without incident. The first two targeted `/tmp`, a vfat volume that also
holds `/etc` and is probably close to full. The `sed -i` failure is separate and
still unexplained: it reported no error and left the file untouched.

So the correct statement is narrower than "bulk writes kill the link": **writes to
`/tmp` died, writes to `/usr` did not.** That is worth knowing before the next
attempt, and it means the earlier conclusion in
`docs/WHY_THE_STRING_PATCH_IS_STUCK.md` was too broad.

## Rollback

The stock file is on the card, byte-identical to what the camera shipped:

```
/tmp/sd/RE_DUMP/strings/string_english_f.uxc.RESTORE   md5 349711603d2e16c1fc620e4e8bf30be0
```

Copy it back with the same eleven-chunk procedure and `mv` it into place. The
card is still mounted at `/tmp/sd`, so a revert is immediate.

## Unquantified, and the thing to watch

- The change only shows if the camera is set to **English**.
- `Playback` occurs three times in this table, so all three labels change.
- The other 67 language files are untouched, so switching language shows the
  original text.
- **Whether the engine measures text width before drawing is still unknown.**
  Equal length in a proportional font can occupy a different pixel width, so a
  centred or right-aligned label may sit slightly differently. That is a
  rendering difference, not a structural one.
- If the app fails to start, the file is the first thing to restore; the restore
  is on the card and the procedure is above.
