"""Recover the test-message grammar from libtestcmd.so's code.

The strings give the response formats:
    "%c:0x%x"     a tag byte then a value in hex
    "%s:%s"       name:value
    "0x%02x "     byte dump

and the front-ends take --ifile / --ibfile / --size / --id, so the message is
described by (size, id) plus a payload.  cmdline_get_size (0x1CB1, 232 bytes)
is almost certainly what turns the parsed fields into the message length, and
the read_* functions turn a file into those fields.

Disassemble the PLT and the text to see the call order, then read the format
strings the parser compares against.  .rodata is only 0x81 bytes, so every
format string in the library is in that block -- if the grammar is
string-driven, it is all visible there.
"""
import re
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

SO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\libtestcmd.so')
img = SO.read_bytes()
md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
md.detail = False

TEXT_OFF, TEXT_ADDR, TEXT_SIZE = 0x000F2C, 0x00000F2C, 0x00EF8
RO_OFF, RO_ADDR, RO_SIZE = 0x001E2A, 0x00001E2A, 0x00081

print('=== .rodata in full (the grammar lives here if it is string-driven) ===')
rb = img[RO_OFF:RO_OFF + RO_SIZE]
off = 0
while off < len(rb):
    end = rb.find(b'\x00', off)
    if end < 0:
        end = len(rb)
    if end > off:
        s = rb[off:end]
        print('  ro+0x%04x (va 0x%08X)  %-40r  %s'
              % (off, RO_ADDR + off, s, s.decode('latin1')))
    off = end + 1
print()

# PLT: map each stub to its GOT slot so calls can be named
print('=== .plt stubs (0x0D7C, 0x1B0 bytes = 44 entries) ===')
plt = []
for i in range(0x00D7C, 0x00D7C + 0x01B0, 12):
    w = struct.unpack_from('<3I', img, i)
    plt.append((0x00000D7C + (i - 0x00D7C), w))
# resolve GOT names from .rel.plt / .dynsym
relplt = None
(e_shoff,) = struct.unpack_from('<I', img, 0x20)
e_shentsize, e_shnum, e_shstrndx = struct.unpack_from('<HHH', img, 0x2E)
secs = []
for i in range(e_shnum):
    off = e_shoff + i * e_shentsize
    v = struct.unpack_from('<10I', img, off)
    secs.append(dict(name=v[0], type=v[1], flags=v[2], addr=v[3], offset=v[4],
                     size=v[5], link=v[6], entsize=v[9]))
shstr = secs[e_shstrndx]
for s in secs:
    b = shstr['offset'] + s['name']
    s['sname'] = img[b:img.find(b'\x00', b)].decode('latin1')
dynsym = next(s for s in secs if s['sname'] == '.dynsym')
dynstr = next(s for s in secs if s['sname'] == '.dynstr')

gotname = {}
relplt = next((s for s in secs if s['sname'] == '.rel.plt'), None)
if relplt:
    for i in range(relplt['size'] // 8):
        r_off, r_info = struct.unpack_from('<II', img, relplt['offset'] + i * 8)
        symidx = r_info >> 8
        so = dynsym['offset'] + symidx * 24
        st_name = struct.unpack_from('<I', img, so)[0]
        b = dynstr['offset'] + st_name
        gotname[r_off] = img[b:img.find(b'\x00', b)].decode('latin1')

for idx, (addr, w) in enumerate(plt):
    # ARM PLT: add ip, pc, #.. ; add ip, ip, #.. ; ldr pc, [ip, #..]!
    got = w[2] & 0xFFF
    nm = gotname.get(w[1], '')
    print('  plt[%2d] 0x%08X  %s' % (idx, addr, nm))


def show(label, va, n=60):
    off = TEXT_OFF + (va - TEXT_ADDR)
    print('--- %s  (va 0x%08X) ---' % (label, va))
    a = off
    cnt = 0
    while cnt < n and a + 4 <= TEXT_OFF + TEXT_SIZE:
        i = next(md.disasm(img[a:a + 4], TEXT_ADDR + (a - TEXT_OFF)), None)
        if i is None:
            a += 2
            continue
        note = ''
        if i.mnemonic in ('bl', 'blx'):
            m = re.search(r'#?(0x[0-9a-fA-F]+)', i.op_str)
            if m:
                t = int(m.group(1), 16)
                for idx, (pa, w) in enumerate(plt):
                    if pa == t:
                        note = '   ; %s' % gotname.get(w[1], 'plt%d' % idx)
        print('  0x%08x  %-12s %-9s %-24s%s'
              % (i.address, i.bytes.hex(' '), i.mnemonic, i.op_str[:24], note))
        a += i.size
        cnt += 1
    print()


print('=== cmdline_get_size (0x1CB1) -- builds the message length ===')
show('cmdline_get_size', 0x1CB1, 70)
