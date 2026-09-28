"""Disassemble libtestcmd.so's parsers as THUMB.

Correct ISA: the .dynsym addresses carry the Thumb bit (0x1909 -> 0x1908), and
decoding in ARM mode produced plausible-looking nonsense.  With CS_MODE_THUMB
the very first function decodes as a textbook prologue:

    0x1CB0  push.w {r4,r5,r6,r7,r8,sb,lr}
    0x1CB4  sub   sp, #0x5c

and cmdline_get_size immediately shows the message layout:

    ldrb r2, [r4, #1] / ldrb r3, [r4]
    orr  r3, r3, r2, lsl #8
    ldrb r2, [r4, #2] / orr r3, r3, r2, lsl #16
    ldrb r2, [r4, #3] / orr r3, r3, r2, lsl #24
    ldr  r2, [r7, #0x2c]
    adds r3, r3, r2

i.e. a 32-bit little-endian header at the front of the structure, plus a length
field at offset 0x2c.  So the message is {u32 header, payload}, and the text
file parser builds that header from what we write in the file.

Goal: the exact text grammar, so a message file can be authored.  Read
cmdline_read_data_from_file (0x1908) and follow its strtoul/fgets calls, plus
cmdline_read_data_from_ibfile (0x1670) for the binary path.
"""
import re
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

SO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\libtestcmd.so')
img = SO.read_bytes()
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
md.detail = False

TEXT_OFF, TEXT_ADDR, TEXT_SIZE = 0x000F2C, 0x00000F2C, 0x00EF8
RO_OFF, RO_ADDR, RO_SIZE = 0x001E2A, 0x00001E2A, 0x00081
PLT_OFF, PLT_ADDR, PLT_SIZE = 0x000D7C, 0x00000D7C, 0x001B0
RELPLT_OFF, RELPLT_SIZE = 0x00000C68, 0x00108
DYNSYM_OFF, DYNSTR_OFF = 0x000001D0, 0x000690

got = {}
for i in range(RELPLT_SIZE // 8):
    r_off, r_info = struct.unpack_from('<II', img, RELPLT_OFF + i * 8)
    so = DYNSYM_OFF + (r_info >> 8) * 24
    st_name = struct.unpack_from('<I', img, so)[0]
    b = DYNSTR_OFF + st_name
    got[r_off] = img[b:img.find(b'\x00', b)].decode('latin1')

# Thumb BL targets are word-aligned; the PLT entries are ARM though, so build a
# name table for the PLT addresses and match on the raw immediate.
plt = []
for i in range(0, PLT_SIZE, 12):
    w = struct.unpack_from('<3I', img, PLT_OFF + i)
    plt.append((PLT_ADDR + i, got.get(w[1], ''), w[2]))


def bl_target(ins_bytes, addr):
    """Decode a Thumb BL/BLX immediate and return the absolute target."""
    hw1, hw2 = struct.unpack_from('<HH', ins_bytes)
    if (hw1 & 0xF800) in (0xF000, 0xE000):
        s = (hw1 >> 10) & 1
        imm10 = hw1 & 0x3FF
        j1, j2 = (hw2 >> 13) & 1, (hw2 >> 11) & 1
        imm11 = hw2 & 0x7FF
        i1, i2 = (~(j1 ^ s)) & 1, (~(j2 ^ s)) & 1
        v = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
        if v & 0x1000000:
            v -= 0x2000000
        return addr + 4 + v
    return None


def disasm(va, nbytes, label=''):
    va &= ~1
    off = TEXT_OFF + (va - TEXT_ADDR)
    print('--- %s   va 0x%08X ---' % (label, va))
    a = off
    end = off + nbytes
    while a < end:
        i = next(md.disasm(img[a:a + 4], TEXT_ADDR + (a - TEXT_OFF)), None)
        if i is None:
            a += 2
            continue
        note = ''
        if i.mnemonic in ('bl', 'blx') and i.size == 4:
            t = bl_target(img[a:a + 4], i.address)
            if t is not None:
                for pa, nm, _ in plt:
                    if pa == t:
                        note = '   ; %s' % (nm or 'plt@0x%X' % pa)
                        break
                else:
                    note = '   ; -> 0x%08X' % t
        if i.mnemonic == 'bl' and i.size == 2:
            m = re.search(r'#(0x[0-9a-fA-F]+|\d+)', i.op_str)
            if m:
                note = '   ; -> 0x%X' % int(m.group(1), 0)
        if i.mnemonic.startswith('ldr') and '[pc' in i.op_str:
            m = re.search(r'#(0x[0-9a-fA-F]+|\d+)', i.op_str)
            if m:
                tgt = ((i.address + 4) & ~3) + int(m.group(1), 0)
                if RO_ADDR <= tgt < RO_ADDR + RO_SIZE:
                    so = RO_OFF + (tgt - RO_ADDR)
                    note = '   ; "%s"' % img[so:img.find(b'\x00', so)].decode('latin1')
        print('  0x%08X  %-10s %-9s %-24s%s'
              % (i.address, i.bytes.hex(' '), i.mnemonic, i.op_str[:24], note))
        a += i.size
    print()


disasm(0x1908, 120, 'cmdline_read_data_from_file')
disasm(0x1670, 110, 'cmdline_read_data_from_ibfile')
