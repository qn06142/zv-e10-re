# Magenta framing lines: earlier hardware milestone

**The first confirmed, tangible, on-screen modification on the Sony ZV-E10.**

By reverse engineering Sony's proprietary `.uxc` user interface resource format, we successfully recoloured the live-view framing guides (rule-of-thirds grid lines) on the physical camera LCD from factory stock translucent grey (`#333333` @ 50% opacity) to vibrant **magenta** (`#FF00FF` @ 100% opacity).

```
Stock:   0x400c: 33 33 33 80  (Grey @ 50% opacity)
Patched: 0x400c: ff 00 ff ff  (Vibrant Magenta @ 100% opacity)
```

### Why this is the load-bearing tangible result
- **100% Hardware Verified:** When the camera powers on in standard shooting mode, the framing guides appear in bright magenta directly on the LCD display and viewfinder.
- **Conclusive Proof of the UI Architecture:** `#FF00FF` appears **zero** times anywhere in Sony's stock palette. The appearance of magenta on the LCD settles the mechanism beyond debate: Sony's UI engine parses `.uxc` resource tables at boot, and entry `0x400c` is authoritative for framing guides.
- **Safe & Reversible:** Operates via a surgical 4-byte edit in a 312-byte user-space palette file (`/usr/share/app/color_cmn.uxc`). Does not touch firmware binaries, kernel drivers, or `/system/av-cam.bin`.

### The 4-Byte Palette Record

The camera's UI engine loads `/usr/share/app/color_cmn.uxc` (312 bytes) at startup. Palette records have an 8-byte stride: `u16 id` (0x4000..0x4022), `u16 attr` (0x3a09), and 4 bytes `RGBA`. Record `0x400c` (offset `0xbc`) governs the live-view framing lines:

| Mode | Entry `0x400c` (Hex) | RGBA Colour | File MD5 | On-Screen Appearance |
|---|---|---|---|---|
| **Stock** | `0c 40 09 3a 33 33 33 80` | `#333333` @ 50% | `f468bd3e72ca4e5b948a1c9f1f35c0a1` | Factory subtle grey grid lines |
| **Magenta** | `0c 40 09 3a ff 00 ff ff` | `#FF00FF` @ 100% | `c169428ea6ef0e924235164a0b33e528` | **Vibrant magenta framing lines** |
| **Blue (Alt)** | `0c 40 09 3a 00 00 dd 80` | `#0000DD` @ 50% | `9474c2846a1a952179a2408018ff0295` | Translucent blue grid lines |

### Quick Start: Apply or Revert on Hardware

**Option 1: Single-shot Python script**
```powershell
# Deploy magenta framing lines (writes /usr/share/app/color_cmn.uxc and reboots):
python batch_patch_magenta.py

# Revert to factory stock anytime:
python batch_patch_magenta.py --revert
```

**Option 2: Direct service shell commands**
```sh
# 1. Remount /usr writable
mount -o remount,rw /usr

# 2. Patch 4 bytes at offset 0xbc (Entry 0x400c -> ff 00 ff ff)
printf '\xff\x00\xff\xff' | dd of=/usr/share/app/color_cmn.uxc bs=1 seek=188 count=4 conv=notrunc

# 3. Verify MD5 matches c169428ea6ef0e924235164a0b33e528
/bin/busybox md5sum /usr/share/app/color_cmn.uxc

# 4. Remount read-only and reboot to observe
mount -o remount,ro /usr
sync
/bin/busybox reboot -f
```
