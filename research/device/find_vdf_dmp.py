from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

path = 'F:/D/lib/libObj.so'
with open(path, 'rb') as f:
    elf = ELFFile(f)
    text = elf.get_section_by_name('.text')
    text_base = text['sh_addr']
    text_data = text.data()

md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

start_addr = 0x00684086
offset = start_addr - text_base
chunk = text_data[offset:offset + 250]

print('=== Disassembly of GRM_gpermRectblit at 0x00684086 ===')
for insn in md.disasm(chunk, start_addr):
    print('0x%08x: %-10s %s' % (insn.address, insn.mnemonic, insn.op_str))
