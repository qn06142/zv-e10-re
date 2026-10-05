from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

path = 'F:/D/lib/libObj.so'
with open(path, 'rb') as f:
    elf = ELFFile(f)
    text = elf.get_section_by_name('.text')
    text_base = text['sh_addr']
    text_data = text.data()

md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

syms = [
    ('GRM_screenGetOnBitmap', 0x00685a21, 16),
    ('GRM_bitmapGetPhysicalAddress', 0x00684e6d, 24),
    ('GRM_bitmapWriteLockBits', 0x00684ead, 24),
    ('GRM_bitmapWriteUnlockBits', 0x00684ebd, 24),
    ('GRM_bitmapGetRowPixelCount', 0x00684fd7, 24),
    ('GRM_bitmapCreate', 0x00684c19, 120),
]

for name, addr, sz in syms:
    print(f'\n=== {name} (0x{addr:08x}) ===')
    off = (addr & ~1) - text_base
    chunk = text_data[off:off+sz]
    for insn in md.disasm(chunk, addr & ~1):
        print('  0x%08x: %-10s %s' % (insn.address, insn.mnemonic, insn.op_str))
