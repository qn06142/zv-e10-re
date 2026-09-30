# Remaining blockers to RE, and to issuing our own commands

Answering the question directly. Short version: **RE is not blocked, command
issuance is.** One hardware dependency gates everything on the second.

## The camera is currently disconnected

```
Looking for Sony devices
No devices found. Please make sure that the camera is connected.
*** link never came up after every attempt ***
```

`research/device/zve10_retry.py` cannot reach it. Everything below that needs
the device is blocked on plugging it back in — nothing else.

## Issuing our own commands

### What is already done

We have **arbitrary code execution as root on the camera**, demonstrated and
then restored (`docs/HANDOFF.md` §1, `docs/SERVICE_AUDIT.md`). Not theorised:
a 66-byte Thumb-2 payload of raw `svc #0` syscalls was injected into
`/usr/lib/libtestcmd.so`, `/tmp/ox` appeared containing `OPX`, and the library
was restored to stock md5 with its original mode and ownership.

So "can we run our own code" is answered. The blocker is not capability.

### What is actually blocked, in order

**1. `libIMDB.so` → `im.elf` is a one-way door, and it is untested.**
`im.elf` (PID 157) owns 417 message queues and 310 callbacks, mounts every
filesystem, and `dlopen`s what `libIMDB.so`'s manifest names. Replacing that
one library would give persistent root code execution at boot, in the process
that owns the message bus.

It is untested because a malformed replacement means `im.elf` never starts and
the service shell never appears — recovery is the SD card. **This needs the
camera present and a deliberate decision**, not more analysis. It is the
single highest-value action available.

**2. Even with code execution, there is nothing to command.** The application
core is absent: `appFw.so`, `gui.so`, `libNVM.so`, `libInfraWebApi.so` are all
not deployed. The service filesystem has the rendering engine, the view layer
and 81 MB of assets, but not the program that uses them. So an injected process
can talk to `im.elf` and the RTOS, and there is no application to issue
commands *to*.

**3. Boot mode.** `BOOTMODE=NORM`, no `/setting/sen/smode`, no `dmode`, no
kernel flag — yet the application is not loaded. Either the reported mode is
wrong or the service USB personality itself holds the system in the launcher.
Testing means giving up the shell. **This is the actual reason the subsystems
are unreachable**, and it is the one open question that no amount of offline RE
will answer.

**4. The message bus is addressable but not yet writable from our side.**
`0x00dc0000` is the liro/RTOS endpoint and `sndcmd.elf` posts to it with RC=0,
so firmware accepts messages. The MWF message format is now known in detail
(`docs/MWF_MESSAGE_VOCABULARY.md`), but that is the *Linux-side* framework.
The RTOS-side format in `av-cam.bin` is a separate, unsolved problem — and
`sndcmd` posting successfully does not establish that a message does anything.

### The honest summary

| | status |
|---|---|
| run our own code as root | **done, proved** |
| persistent code execution at boot | blocked on decision + camera |
| command the RTOS subsystems | blocked on the RTOS message format |
| command the application | blocked: not deployed, and boot mode unexplained |
| observe the firmware | `tmonitor` is writable and idle (`mask=0`) — untested |

## RE: not blocked, and I have been working on it

All the libraries needed are on disk, so this continues with the camera
disconnected. I started on the largest untouched item.

### `DefInh::sm_refTbl` — geometry recovered

This is 96.7% of `libSysDef.so`: **3,158,400 bytes**, an exported data symbol,
untouched until now. The two accessors are the only clue to its shape, and both
are red herrings for the layout:

```
DefInh::GetFactorIdMax()    -> movw r0, #0x18fd   = 6381   factor ids
DefInh::GetFactorTblMax()  -> movs r0, #0xc8     = 200    table slots
```

Neither divides the size. But **3,158,400 / 800 = 3948 exactly**, and 800 is
visible in the data: the first non-zero byte after the leading word is at
`+0x320`, then `+0x640`, then `+0x960` — gaps of exactly 0x320. The non-zero
bytes also cluster at a handful of residues mod 800, which is what a
fixed-stride array of mostly-zero records looks like.

`research/firmware/factor_table.py` dumps it. Findings:

- 3,948 records of 800 bytes; 88.2% populated; only 2.1% of the bytes non-zero
- 24 field offsets in use, none above 20.5% of records
- fields-per-record is **bimodal**: 1,610 records carry one non-zero word,
  thinning to a minimum near 40, then rising to a second cluster at 64–70, with
  one record at all 200

That bimodality says **tagged union** — some factors are a single scalar, some
are a 64+-value block. Consistent with a camera adjustment table, which is a
different axis from the message vocabulary.

**A claim I had to retract:** I initially read the `+160`/`+164` pair in record 1
as a signed 24-bit min/max range — `0xffe00000` and `0x001fffff` are adjacent
24-bit values and it looks convincing. Records 39–44 put `0x01000000/1`,
`0x02000000/2`, `0x04000000/4` in those words: a doubling sequence, not a
range. The fields are independent. Looking at one record and pattern-matching is
the same mistake as the contact-sheet misreads in the font work, and the
docstring now says so.

Semantics remain open: naming the fields needs the id→record index, and
6381 ids against 3948 records fits an indirection rather than a direct array.

### Still open offline, by value

1. **The RTOS message format** in `av-cam.bin` (17 MB, locally). This is what
   `sndcmd.elf` sends, and nothing has decoded it. It gates item 4 above.
2. **The id→record index** for the factor table.
3. **`DefRsrc::scm_refTbl`** (98,778 B) — indexed by `AcsrId_t`.
4. **FaceRecorder dispatch geometry** — names are known, table layout is not.
5. **The `0x4xxx` id family** — real, named by nothing.

## What I would do next

**Plug the camera back in**, then in one session:

1. Do **not** touch `libIMDB.so` yet. First collect the things that need the
   device and are risk-free: `tmonitor` params, another `/proc/osal/uipc`
   capture to diff against, and the `0x4xxx` ids.
2. Then decide on `libIMDB.so` deliberately, with the SD card as the recovery
   path confirmed working.

The offline work continues regardless — the RTOS message format is the highest
value item and needs no hardware.
