# UI resource layer: the `.uxc` colour palette

Newly found, and the first *legitimate, whole-filesystem* route to a visible
effect. This replaces the ioctl/msgid approaches as the preferred path.

## Where the UI lives

`/usr/share/app/` — ~200 files, all read off the camera in one tar:

```
/tmp_bt/ui.tar  30720 B  md5=529b5ec9f4a210f37d0c7ac46c1cf253
```

Three container magics, all sharing a header shape:

| magic  | version word | what |
|--------|--------------|------|
| `uxa`  | 9 | `global.xdb` — 3063 u32, a directory of all ~200 resource filenames |
| `uxb`  | 9 | `lang.uxb`, `style.uxb` — u32 offset tables |
| `uxc`  | 8 | every screen (`view*.uxc`) and shared resource |

Files that are *not* containers and are plain text:

- `fontlist.dat` (360 B) — tab-separated `NAME<9>path`, e.g.
  `FONT_UNIVERS → /usr/share/app/UniversOTS-SJ_wIcon.ltt`
- the `string_*.uxc` files are per-language UI strings
- `image_*.uxc` are the large bitmap sets (up to 27 MB)

## `color_cmn.uxc` — decoded, byte-exact round-trip

312 bytes. This is the shared colour palette the UI draws itself with, so a
one-quad edit recolours real screens using the engine's own code path — no new
syscall, no message id, no driver poking.

Header (`uxc_color.py`):

```
0x00  3 bytes  magic 'uxc'
0x03  u8       format version (7)
0x04  3 bytes  zero
0x07  u8       zero
0x08  u16      stream version: 8 for .uxc, 9 for .uxb/.uxa
0x0A  u16      0x004a  (file-specific, not a checksum)
0x0C  u16      0x4023  = one past the highest id (high-water mark)
0x0E  u16[]    sparse id→slot index, 0xffff = absent
0x58            body: 28 records of exactly 8 bytes
```

Record layout, stride 8, covering `0x58..0x137` = all 312 bytes exactly:

```
+0  u16  id       sequential 0x4000 .. 0x4022
+2  u16  const    0x3a09 in every record
+4  u8   r
+5  u8   g
+6  u8   b
+7  u8   a
```

The palette, with names inferred from the RGB values:

| id | rgba | reads as | | id | rgba | reads as |
|----|------|----------|-|----|------|----------|
|4000| `ffffff` | white | |400f| `33333380` | dark grey ½α |
|4001| `dddddd` | light grey | |4010| `dd5500` | orange |
|4002| `00000099` | black 60% | |4011| `dd5500` | orange |
|4003| `00000088` | black 53% | |4012| `dddddd` | light grey |
|4004| `dddddd` | light grey | |4013| `dd6600` | yellow |
|4005| `dddddd` | light grey | |4015| `dddddd` | light grey |
|4006| `dddddd` | light grey | |4017| `00000099` | black 60% |
|4007| `dd0000` | **red** | |4018| `00000044` | black 27% |
|4008| `00dd00` | **green** | |401b| `000000cc` | black 80% |
|4009| `0000dd` | **blue** | |401f| `dddddd` | light grey |
|400a| `cccccc80` | mid grey ½α | |4020| `dddddd` | light grey |
|400b| `cccccc80` | mid grey ½α | |4021| `ffffff` | white |
|400c| `33333380` | dark grey ½α | |4022| `0000004c` | black 30% |

Two things worth stating because they were the things I had to get right:

- **There is no checksum.** Nothing in the file validates its own payload, so
  a single-quad edit cannot be rejected on integrity grounds. The only risk is
  semantic: an out-of-range or garbage quad.
- **The ids are consecutive, `0x4000`–`0x4022`.** What look like gaps are the
  `0xffff` holes in the separate *index* table at `0x0E`, which is a sparse
  id→slot map, not the colour list. I initially misread it as the colour list
  and patched the wrong id; the round-trip test is what caught it.

`uxc_color.py` enforces this: it parses, re-emits, and asserts byte equality
before it will produce a patched variant.

```
re-emitted 312 bytes
BYTE-EXACT MATCH -- container decoded, patch is trustworthy

single-quad patch demo: changed 2 bytes at offsets 0x94, 0x96
  (id 0x4007, red -> ff00ff)
```

`dumps/camera/app/color_cmn.patched.uxc` is written for review. **It has not
been pushed to the camera.**

## Why this is the right target

Against the requirements:

- **Visible.** `color_cmn.uxc` is the common palette; `view*.uxc` screens
  reference it by id. A changed accent colour appears on real screens.
- **Unmistakably ours.** Magenta/cyan on a Sony UI is not a plausible factory
  value.
- **Non-crash, no brick.** A 312-byte resource edit, restorable byte-exactly
  from the tar. No firmware region touched; `/system/av-cam.bin` untouched.
- **Legitimate path.** The engine already opens and parses this file. We are
  not injecting calls, not touching the display driver, not guessing a struct.

## Open questions, in order

1. **Is `/usr/share/app` writable?** Not yet established. `mount` output was
   never captured — the session died on `Mass storage read error` before it
   ran. `/setting` is nflasha2, `/log` is nflasha11; the root is nflash. If
   the root is read-only, this route needs a different staging path (SD card,
   or `/log`) plus whatever the loader consults.
2. **Does the engine re-read the palette at runtime, or only at boot?** If only
   at boot, the effect still shows but needs a restart to observe.
3. **`id 0x4007` (red) may be load-bearing** — Sony's UI uses red for record
   indicators and warnings. Recolouring it is more likely to be noticed *and*
   more likely to look like an error state. A less semantic target is
   `0x4013` (yellow) or the greys.

## Also found this session

- `im.elf` (`/usr/bin/im.elf`, 23,240 B) is pid 157, the process holding 417 of
  the 857 uipc message queues. It imports `IMDB_find_entry`, `IMDB_get_entries`,
  `IMDB_find_target_bit` from `libIMDB.so`, plus the full `osal_*` msg API.
- `libIMDB.so` (37,044 B) turned out to be a *kernel module loader*, not a
  command-id table. Its `.rodata` names 16 module paths (`/kmod/dmm.ko`,
  `/kmod/stream.ko`, `/kmod/hdmi.ko`, `/usr/kmod/liro.ko`, …) and a second
  config path `DmmConfig=/usr/share/dmm/DmmConfig.bin`. No command names —
  `Panel`, `Display`, `CMD_` all occur 0 times.
- `ldec` is **not** in any on-disk module. `/proc/modules` gives it 10,106 bytes
  with flag `(P)` = statically allocated core, so its code is linked into the
  kernel image. `dmm.ko` (85,588 B), `stream.ko`, `stream2.ko` all pulled and
  checked: no ldec symbols. This closes the "read ldec_ioctl from the .ko"
  idea that would have replaced the earlier `/dev/mem` dead end.
- `stream.ko`/`stream2.ko` do export `stream_mmap`, and `stream2`'s walks a
  5-entry table in `.data` at 0x8c calling `remap_pfn_range` per entry. Not a
  display surface — it is a scatter-gather buffer mapper. Noted, not pursued.

## Camera state at the end of this session

The camera wedged mid-session (`Mass storage read error`, then
`libusb0-dll:err [_usb_reap_async] timeout error`, then a bare
`AssertionError`). `pnputil`-based USB reset returns rc=5 (needs an elevated
shell), so **a manual unplug/replug is required** before the next session.
Nothing was mid-write; `/tmp_bt/ui.tar` completed and verified first.
