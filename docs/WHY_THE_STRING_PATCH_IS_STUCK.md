# Why a 349 KB file cannot be written to this camera

Date: 2026-09-28. Outcome: **the string patch was not delivered.** The patch is
built and triple-verified; the transport cannot carry it. This is the record of
why, because four separate routes were tried and each failed for a different,
specific reason.

## The patch that is ready

`string_english_f.uxc`, 349,020 bytes, three `Playback` → `OPENCODE` labels at
0x041bb0, 0x0476dc, 0x04cbc0. Three independent methods produce the identical
result and the identical hash `9853d47ad4197d3387f10babdc8728b9`:

| method | result |
|---|---|
| direct byte patch at the three offsets | 24 bytes, hash matches |
| `sed` with `\x` escapes | 51 bytes — **wrong**, see below |
| `sed` with a backreference | 24 bytes, hash matches |
| line-addressed `sed` (`780s/`, `1040s/`, `1147s/`) | 24 bytes, hash matches |

The live file's md5 was confirmed as `349711603d2e16c1fc620e4e8bf30be0` before
every attempt, and the three target sites were confirmed to contain exactly
`Playback` on the device by `dd`-ing 8 bytes and md5-ing the slice.

## The four transports, and why each failed

**1. The SD card — the designed path — no card.** `zx send <card-file>` reads the
file from the card *on the camera* and base64-encodes it there, which is exactly
how it avoids the terminal length limit. But `/proc/partitions` lists only
`nflash*` devices: there is no MMC or SD block device at all. The card is in the
PC's reader at `F:\RE_DUMP`, with both the patched file and the restore file
staged there. `/tmp/sd` exists but is a directory in the `/etc` vfat partition
(it mirrors `etc/sd/fuzz`), not a card mount.

**2. The USB terminal — 1022-char cap, and bulk writes kill the link.**
`busybox echo <4000 chars> | busybox base64 -d > /tmp/big` produced
`md5sum: can't open '/tmp/big'` — the command was silently dropped, exactly as
the toolbelt README warns. Worse, the failure mode is not a clean rejection:
sustained writes abort the USB link partway through. Observed partial results:

| attempt | bytes written of 349,020 |
|---|---:|
| `dd` splice into `/tmp` | 75,724 |
| `dd` splice into `/tmp` | 186,712 |
| `sed -i` on the real file | 0 (temp file discarded) |

The link dying is not the same as the write failing destructively, and that is
the one mercy here: every writer in play — `sed -i`, and any splice — builds a
temporary file and renames, so an interrupted write leaves the original intact.
The live file's hash was still `34971160…` after every failure. Small writes work
fine: a 70-byte `sed -i` completed and hash-exact.

**3. Network — no address.** `ftpget` and `ftpput` are both present in busybox,
which would have solved this in one short command. But `wlan0` has only a
link-local IPv6 (`fe80::da10:68ff:fe34:b645`) and no IPv4, so there is no route.
Joining a network would need an SSID and passphrase and is a project of its own.

**4. Backgrounding — dies with the shell.** Running the three `sed`s inside `( … ) &`
so the device would finish after the link dropped produced no `/tmp/after.txt`
at all: the job was killed when the terminal session was torn down. There is no
`nohup` or `setsid` in this busybox.

## What this busybox actually has

The toolbelt README's applet list is incomplete. `busybox --list` gives **198
applets**, including ones that matter here:

`sed` `xxd` `hexedit` `ftpget` `ftpput` `truncate` `fallocate` `shred` `sync`
`cut` `paste` `sort` `uniq` `expr` `bc` `crc32` `sha256sum` `xz` `lzop` `mke2fs`

Confirmed absent, as the README says: `printf` `od` `df` `which` `head` `tr`
`find` `strings` `nc` `nohup` `setsid`.

### `dd` has no `conv=notrunc` — the one that could have bricked it

`busybox dd --help` lists `if` `of` `bs` `count` `skip` `seek` `status` and
**nothing else**. No `conv=notrunc`. An in-place seek-write
(`dd of=file bs=1 seek=269232 conv=notrunc`) is therefore impossible, and any
`dd of=<live file>` **truncates the file to the write offset** — 269,240 bytes of
a 349,020-byte file. The first attempt hit this; it printed usage and refused
because `conv=` was unrecognised, and the file was verified intact immediately
after. Had it accepted the argument and ignored it, the string table would have
been destroyed.

### `sed` will not match across bytes >= 0x80

`sed -i 's/\(Display.....\)Playback/\1OPENCODE/g'` on the real file ran clean,
printed nothing, and changed nothing. The span contains `0xb5`, `0xee`, `0xa0`.
The workaround is a line address, which keeps the pattern pure ASCII: the file
has only 1,298 newlines, so `780s/Playback/OPENCODE/` is unambiguous. On line
780 `Playback` occurs four times but the target is the first, so a
non-`/g` substitute is exact.

## A mistake worth recording

My first `sed` simulation replaced `(Display.....)Playback` with
`Display.....OPENCODE` — literal dots, not the matched bytes. That would have
written 51 changed bytes and destroyed three record ids (`47 b5 1b 1e` and
friends), plausibly breaking the whole string table. It was caught only because
the simulated hash was compared against the independently built file and
**differed**: `91096ab1…` versus `9853d47a…`. A length-preserving pattern is
not automatically a value-preserving one; the wildcards in the *replacement* are
the trap, and a backreference is the fix.

Separately, I hand-typed a hex string to verify a device-side test file and got
it wrong — the file is 70 bytes, not what I typed — which would have made a
working `sed` look broken. The project's own rule, never hand-type base64 or
hex, generate it programmatically, exists because of exactly this. The error was
in the *verification*, which is the worst place for it.

## State left behind

- `/usr/share/app/string_english_f.uxc` — **unchanged**, md5
  `349711603d2e16c1fc620e4e8bf30be0`, confirmed after every attempt.
- No app resource was written. The only hardware-verified change remains the
  magenta palette.
- `/usr` was `ro` at session start; I set it `rw` to attempt the write and
  **could not set it back** — `mount -o remount,ro /usr` fails with
  `Device or resource busy` because the running application holds `/usr` open.
  It needs the app stopped, or a later session after reboot.
- Scratch files under `/tmp` were removed.
- Staged on the card, unused: `F:\RE_DUMP\strings\string_english_f.uxc.OPENCODE`
  (md5 `9853d47a…`) and `.RESTORE` (md5 `34971160…`).

## What would actually unblock this

1. **Put the SD card in the camera.** The staged files are already on it. This is
   the designed path, it needs no terminal transfer, and `zx send` would base64
   the file on-device where there is no length limit. It is the cheapest fix by
   a wide margin.
2. Failing that, get the camera an IPv4 address, and `ftpget` pulls the file in
   one command.
3. Failing that, find the largest write that survives the link and build the file
   in verified appends. The threshold is untested; 70 bytes is known good and
   75 KB is known bad.
