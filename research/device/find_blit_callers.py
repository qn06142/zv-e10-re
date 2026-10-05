import struct
from elftools.elf.elffile import ELFFile

path = 'F:/D/lib/libObj.so'
with open(path, 'rb') as f:
    elf = ELFFile(f)
    text = elf.get_section_by_name('.text')
    text_base = text['sh_addr']
    text_data = text.data()

targets = {
    0x00684087 & ~1: 'GRM_gpermRectblit',
    0x00683f4d & ~1: 'GRM_gpermFillrect',
}

print('Fast scanning 16MB .text for bl/blx calls...')
hits = []
for i in range(0, len(text_data) - 4, 2):
    hw1, hw2 = struct.unpack('<HH', text_data[i:i+4])
    # Thumb BL / BLX
    if (hw1 & 0xf800) == 0xf000 and (hw2 & 0xd000) == 0xd000:
        S = (hw1 >> 10) & 1
        imm10 = hw1 & 0x3ff
        J1 = (hw2 >> 13) & 1
        J2 = (hw2 >> 11) & 1
        is_blx = not ((hw2 >> 12) & 1)
        imm11 = hw2 & 0x7ff
        I1 = 1 if (J1 == S) else 0
        I2 = 1 if (J2 == S) else 0
        imm25 = (S << 24) | (I1 << 23) | (I2 << 22) | (imm10 << 12) | (imm11 << 1)
        if is_blx:
            imm25 &= ~3
        # sign extend from 25 bits
        if imm25 & 0x1000000:
            imm25 -= 0x2000000
        pc = text_base + i + 4
        tgt = pc + imm25
        if is_blx:
            tgt &= ~3
        else:
            tgt &= ~1
        if tgt in targets:
            hits.append((text_base + i, targets[tgt]))
            print('0x%08x: bl%s -> %s' % (text_base + i, 'x' if is_blx else '', targets[tgt]))

print('Total calls found:', len(hits))
