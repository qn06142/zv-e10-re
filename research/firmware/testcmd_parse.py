"""Recover the message grammar from libtestcmd.so's parser.

Elf parsing is now correct (research/firmware/testcmd_elf.py), so the function
addresses are trustworthy:

    0x1909  cmdline_read_data_from_file     the text-file parser
    0x1671  cmdline_read_data_from_ibfile   the binary parser
    0x1CB1  cmdline_get_size                size computation
    0x1C1D  cmdline_get_id
    0x1AC7  cmdline_get_sid
    0x116D  testcmd_sndmsg                  the uipc send
    0x1255  testcmd_rcvmsg

.rodata is tiny (0x81 bytes) and contains only:
    'rcv msg from 0x%x size %d @ %p'   '%c:0x%x'   '%s:%s'
    'r'  'wb'  'rb'  'Usage: %s %s'  'options'  '0x%02x '

There is no field-name grammar in .rodata, which means the text format is not
keyword-driven: the parser is positional, and the field layout lives in the
code.  So disassemble cmdline_read_data_from_file and read the strtoul/strtoull
call sequence -- the ORDER of the conversions is the field order, and the
fgets delimiter shows the record separator.

.strtoul and .strtoull both appear in the import list, which is consistent
with a multi-field hex record.
"""
import re
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

sys_path = None
SO = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera\libtestcmd.so')
img = SO.read_bytes()
md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
md.detail = False

# section table (verified by testcmd_elf.py)
TEXT_OFF, TEXT_ADDR, TEXT_SIZE = 0x000F2C, 0x00000F2C, 0x00EF8
RO_OFF, RO_ADDR, RO_SIZE = 0x001E2A, 0x00001E2A, 0x00081
PLT_OFF, PLT_ADDR, PLT_SIZE = 0x000D7C, 0x00000D7C, 0x001B0
RELPLT_OFF, RELPLT_SIZE = 0x00000C68, 0x00108
DYNSYM_OFF, DYNSYM_SIZE = 0x000001D0, 0x004C0
DYNSTR_OFF = 0x000690

# build GOT-slot -> name from .rel.plt
got = {}
for i in range(RELPLT_SIZE // 8):
    r_off, r_info = struct.unpack_from('<II', img, RELPLT_OFF + i * 8)
    symidx = r_info >> 8
    so = DYNSYM_OFF + symidx * 24
    st_name = struct.unpack_from('<I', img, so)[0]
    b = DYNSTR_OFF + st_name
    got[r_off] = img[b:img.find(b'\x00', b)].decode('latin1')

plt = []
for i in range(0, PLT_SIZE, 12):
    w = struct.unpack_from('<3I', img, PLT_OFF + i)
    plt.append((PLT_ADDR + i, w[0], w[1], got.get(w[1], '')))


def name_plt(target):
    for addr, _, _, nm in plt:
        if addr == target:
            return nm or 'plt@0x%X' % addr
    return None


def disasm(va, nbytes=200, label=''):
    off = TEXT_OFF + (va - TEXT_ADDR)
    print('--- %s  va 0x%08X ---' % (label, va))
    a = off
    end = off + nbytes
    cnt = 0
    while a < end and cnt < 200:
        i = next(md.disasm(img[a:a + 4], TEXT_ADDR + (a - TEXT_OFF)), None)
        if i is None:
            a += 2
            continue
        note = ''
        if i.mnemonic in ('bl', 'blx'):
            m = re.search(r'#(0x[0-9a-fA-F]+|\d+)', i.op_str)
            if m:
                nm = name_plt(int(m.group(1), 0))
                if nm:
                    note = '   ; %s' % nm
        if i.mnemonic in ('ldr',) and '[pc' in i.op_str:
            m = re.search(r'#(0x[0-9a-fA-F]+|\d+)', i.op_str)
            if m:
                tgt = ((i.address + 4) & ~3) + int(m.group(1), 0)
                if RO_ADDR <= tgt < RO_ADDR + RO_SIZE:
                    so = RO_OFF + (tgt - RO_ADDR)
                    s = img[so:img.find(b'\x00', so)].decode('latin1')
                    note = '   ; "%s"' % s
        print('  0x%08X  %-10s %-9s %-26s%s'
              % (i.address, i.bytes.hex(' '), i.mnemonic, i.op_str[:26], note))
        a += i.size
        cnt += 1
    print()


disasm(0x1909, 120, 'cmdline_read_data_from_file')
disasm(0x1CB1, 230, 'cmdline_get_size')
disasm(0x1671, 110, 'cmdline_read_data_from_ibfile')
