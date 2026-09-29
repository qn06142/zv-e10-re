# The updater code-exec route is open — the documented blocker was stale

## The correction

`ATTACK_SURFACE.md` route (A) reads:

> (A) Overwrite /usr/bin/udtrbody.bin then run crypter.elf.
>     BLOCKED: /usr/bin is READ-ONLY squashfs in service mode
>     (Verified live: "touch /usr/bin/_wtest: Read-only file system".)

That is no longer true, and the reason it is wrong is worth stating because it
changes how the whole service environment should be read.

**`/usr` is ext2, not squashfs.** It is `/dev/nflasha15`, mounted
`ro,relatime,errors=continue`. And `mount -o remount,rw /usr` **succeeds**:

    RW
    USRBIN_WRITABLE          # wrote /usr/bin/_wtest2, verified

`/usr/bin/udtrbody.bin` is present and writable:

    -rw-r--r-- 1 57285 1000 143360 Mar 14  2025 /usr/bin/udtrbody.bin
    -r-xr-xr-x 1 57285 1000  39084 Mar 14  2025 /usr/bin/crypter.elf

A marker file written to `/usr/bin` **survived a power cycle**, so this is
genuine persistent storage and not a tmpfs illusion. `/usr/bin/_marker3`,
`/usr/share/_marker4` and `/usr/share/pmbp/_marker2` all persisted, while a
marker written to `/usr/share/app` was wiped — so the "wiped at boot" behaviour
is specific to `/usr/share/app`, which is where the main firmware rewrites its
UI resources, and is *not* a property of `/usr` as a whole.

The original observation was presumably made when the service environment
mounted `/usr` differently. It should be re-verified rather than inherited.

## What the primitive actually needs

`crypter.elf`'s `.rodata` literals, in order, give the whole flow:

```
le.cpp
/tmp_updater/updater
/tmp_updater/updater/bodyimg
/usr/bin/udtrbody.bin
/root/IAMUPDATER
/tmp_updater/updater/bodyfs
/tmp_updater/updater/bodyfs/bodylib/libupdaterbody.so
```

So: read `/usr/bin/udtrbody.bin`, extract to `/tmp_updater/updater/bodyfs/`,
`dlopen` the `bodylib/libupdaterbody.so` inside it, `dlsym` one symbol, call it.
Body header magic is `0100UDTRFIRM`.

**The symbol name does not have to be reverse-engineered.** There are exactly
two plain, unmangled C identifiers in the binary — `Dec_ScrambleInit` (0x1d7f)
and `Fsys_Init` (0x1e12, 0x67eb) — which is what a `GetSymbol()` argument looks
like. A replacement library can simply **export both names**, and whichever one
is looked up will resolve. No disassembly required.

`Updater::DllHandler::Open(char const*, int)` and
`Updater::DllHandler::GetSymbol(char const*)` are both present as mangled
symbols, confirming the mechanism.

The `dlopen` happens inside `crypter.elf`, **before** any script runs. That
matters: `startupdate.sh` exits immediately unless `/root/IAMUPDATER` exists
(`/root` is read-only, so that flag is created by the real update flow), so the
*update* cannot be driven from here. But the *code execution* does not depend on
the update proceeding — the library is loaded and called regardless.

## Tooling available

No `arm-linux-gnueabi-gcc`, but the venv has what is needed to hand-build the
library:

- `keystone-engine 0.9.2` — ARM assembler
- `capstone 5.0.9` — disassembler, for verification
- `pyelftools 0.33` — to emit the `.so`
- `unicorn 2.1.4` — to test the emitted ARM code before it ever runs

The body is "Compressed ROMFS" (magic `453dcd28`); the repo already contains an
extracted copy at `udtrbody_extract/` including the stock
`bodylib/libupdaterbody.so` (106,156 B) and the whole updater toolkit, so a
packer can be written against a known-good round trip. The integrity check is
`CrcChecker` / `uc_crc32sum.elf` — CRC, which is forgeable, not a signature.

## The risk, stated plainly

This is the highest-risk operation available on this camera. It is the firmware
updater. A malformed body can leave the **service side** unable to boot, and
that would cost the shell — which is the only way back in. There is no second
door.

Mitigations that exist:

- The stock `udtrbody.bin` is in three local copies plus the SD card, so the
  body itself is always restorable.
- The updater runs on the service CPU, isolated from the main firmware.
- `crypter.elf` can be invoked by hand, so no reboot is required to try it, and
  a wedged process can simply be killed.

What is *not* mitigated: if the write to `/usr/bin/udtrbody.bin` succeeds and
crypter then wedges the service side in a way that prevents a normal remount,
the recovery is "restore the stock body", which itself needs the shell.

Given the project's standing rule about not bricking things, this should be a
deliberate decision rather than something to start unilaterally.

## Alternatives, cheaper

- **UIPC injection** (`sndcmd.elf [osal_id] [size]:[data]`) already reaches the
  main firmware with RC=0. The blocker is knowing real `osal_id`s, which live
  in the encrypted `av-cam.bin`. Could be recovered by *observing* live traffic
  on `/dev/uipc` rather than by disassembling.
- **The camera's own network stack.** It runs a WiFi Direct group owner on
  `192.168.122.1`; Sony cameras expose an HTTP control API on that link. Zero
  risk, and it is the main firmware's own interface rather than a side door.
  Not yet reachable because the PC is not associated with that radio.
