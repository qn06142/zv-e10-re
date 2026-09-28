# Property semantics: the first property named from code, and a located rect

Date: 2026-09-28. Engine: `viewUnified2.so` (.text 7,647,084 B).
Scripts: `trace_bool2.py`, `find_setter_callers.py`, `arity_verify.py`, `find_rect_key.py`.

## 1. `c34c39a70111` is the caution flag

The first property whose meaning has been established from the code rather than
from its value distribution.

The chain, each step read directly:

```
0x002334f8  push {r4, r5, r7, lr}
0x002334fe  movs r0, #0x10
0x00233500  blx  0x18e5f8
0x00233504  bl   0x231054        ; property lookup
0x00233508  cbz  r0, ->false     ; absent -> return 0
0x0023350a  ldrb r1, [r0, #0x11] ; the payload byte
0x0023350c  cmp  r1, #1
0x0023350e  bne  ->false         ; != 1 -> return 0
0x00233516  b.w  0x23342a        ; tail call on true
```

A strict `== 1` test with a false path returning zero: a boolean, confirmed from
code. The predicate sits inside the exported symbol **`ViewCautionToInstance`**
(0x00231a12 .. 0x00236b0a). The setter at 0x0023342a is the same function's
local: it branches on the argument, passes 1 or 0 to 0x190a50, and writes the
value to a 2-byte slot at `[r4, #0x31]` mirrored to a byte at `[r4, #0x16c]`.

So the property is the **caution** flag: whether a caution overlay is shown.
This lands on a third option that the value distribution never offered — the
188 classes with the byte uniformly 1, the 18 uniformly 0 and the 32 mixed are
all consistent with a flag that most caution widgets set and a few do not.

## 2. The four "deserialisers" are constructors

This corrects an earlier note. 0x640850, 0x640878, 0x6408a0 and 0x648150 were
recorded as deserialisers. Read in full they are one identical function:

```
blx  0x1872c8          ; base-class constructor
ldr  r3, [r4, r3]      ; the class vtable
adds r3, #8
str  r3, [r5]          ; install vtable+8
movs r3, #0
str  r3, [r5, #0x14]   ; zero the payload
```

**Not one instruction reads the input stream.** They build, install a vtable and
zero. The consequence is the useful part: **the number of payload fields a
constructor zeroes is the property's arity**, and arity can be counted instead of
guessed at from a byte pattern.

`0x6408a0` is excluded and is not a property constructor at all. Its `r4`/`r5` are
reused for a PC-relative base, so its stores land in `.rodata`:

```
add  r5, pc            ; r5 is a rodata address, no longer 'this'
mov  r4, r5
str  r3, [r4], #0x14   ; patching a global table
```

## 3. Arity census, with the detector calibrated first

`arity_census.py` reported "exactly one arity-4 class" while its own
calibration was failing. That number was a property of the filter, not of the
binary, and was discarded. `arity_verify.py` replaces the displacement-reading
with a small abstract interpreter (r0 seeded as `this`; post-increment forms
tracked) and refuses to print a census unless it reproduces ground truth.

Calibration, and it passes:

| address | key | expected | got |
|---|---|---|---|
| 0x640850 | `ed188f1a018d` | 1 word @ 0x14 | 1 word @ 0x14 |
| 0x640878 | `c34c39a70111` | 1 byte @ 0x11 | 1 byte @ 0x11 |
| 0x648150 | `1f0280550208` | 2 words @ 0x14,0x18 | 2 words @ 0x14,0x18 |

Census of the 0x1872c8 family:

| arity | classes | distinct keys |
|---:|---:|---:|
| 1 | 84 | 112 |
| 2 | 7 | 51 |
| **4** | **1** | **1** |

**The arity-4 class: constructor 0x677010, fields 0x14/0x18/0x1c/0x20, and
exactly one key — `38f85c32..` (engine constant 0x325cf838).** Four consecutive
word fields. A rect.

Scope, stated rather than glossed: the census only sees classes calling the
shared base constructor 0x1872c8, so every count is a **lower bound**. The
result is "one found", not "one exists".

## 4. The key is in the view files, but the payload is constant

Across 299 view files (79,656,916 B):

| key | 4-byte prefix hits | full 6-byte hits |
|---|---:|---:|
| `c34c39a70111` | 8,311 | 8,304 |
| `1f0280550208` | 11,531 | 11,530 |
| `ed188f1a018d` | 2,283 | 2,283 |
| `1b572204010e` | 13,035 | 13,035 |
| **`38f85c32..`** | **37** | (bytes 5-6 unknown) |

The engine carries only the **first four** key bytes as a constant — verified on
all three known keys (`c3 4c 39 a7 | 01 11` → `0xa7394cc3`). So the target had to
be searched as a 4-byte prefix; searching all six would have returned nothing
and looked like a refutation.

37 hits against an expected 0.0185 random, in 4 files (`master_camera`,
`viewBeautyEffect`, `viewIroiroCon`, and one more). **But 35 of the 37 have a
byte-identical 20-byte tail.** That is a constant, not a payload. A constant
means the occurrence is a *declaration*, not an instance — the same trap as the
23 constant payload bytes found earlier.

**So the file-side read is still open.** The values for this key are not
adjacent to it, and locating them needs the index mechanism, not a scan.

## 5. Two claims withdrawn

Recorded because both were nearly mistaken for confirmations.

- **"92 property classes matches the 92 view signatures."** No. The census
  returned 92 and the file format has 92 signatures, but the coincidence came
  from one lossy filter being lossy in the same way twice. The two numbers come
  from unrelated data, which makes a coincidence *more* likely to look
  meaningful, not less. The engine certainly has far more than 92 property
  classes — 12,008 distinct keys were seen in one pass.
- **Vtable slot offsets as type tags.** A census found 133 offsets and
  `0x19c`/`0x44`/`0x1b0` do behave as type tags in composite readers. But the
  calibration required the four known classes to show one virtual read each and
  they showed **zero**: the scalar properties are constructors, not readers, so
  the census was measuring a different layer. Void.

## 6. Instrument bugs found and fixed, kept for the record

- **Capstone desynchronised** when decoding all of `.text` with `skipdata=True`,
  reinterpreting literal pools as opcodes (`ldrtmi`, `ldrvs`, `ldrdeq` — not ARM
  mnemonics). Symptom: a search returned 0 hits for the field offset *and* for
  both controls. Fixed by decoding only inside recovered function bodies:
  impossible `ldr<cond>` fell from tens of thousands to 0.11%.
- **Hand-rolled Thumb `bl` decoding** was wrong twice (J1/J2 are in the second
  halfword; the mask is `0xC000`, not `0xD000`). Caught by a self-test against a
  known call. Its output, "0 call sites for the setter", was fiction. Replaced
  with capstone's branch rendering.
- **The abstract interpreter** initially resolved `mov r5, r0` to nothing because
  `r0` was not seeded as `this`, so all four ground-truth classes came back
  empty. The calibration caught it.
- **A regex** expected `movs r3, #0x0` where capstone prints `movs r3, #0`,
  which made a detector match nothing while passing silently.

Each was found by a control returning a value it should not have. None would
have been caught by inspection.

## 7. State of the machine

- Camera is still patched to **magenta** guides (`0x400c` → `ff00ff`@80α).
  Restore file: `color_cmn.restore.uxc`, md5 `f468bd3e72ca4e5b948a1c9f1f35c0a1`.
- `/usr` is still mounted **rw**.
- The vtable-census and key-walk tables (`prop_table.tsv`) are **not** used; the
  key walk failed its own consistency invariant at 18.6%.

## 8. Next step

Find where the values for key `38f85c32..` live. The key's 37 occurrences are
declarations, so the values are reached by index — the same shape as the
container index rule already solved (`index_count = control & 0xff`, control at
0x0c) and the view object table (`offset[0] == 1 + 2N`). The rect class at
0x677010 gives the expected shape to look for: four words, in order, at the
slot the index points to.
