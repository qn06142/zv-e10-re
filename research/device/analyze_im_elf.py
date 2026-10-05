import tarfile, io
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

with tarfile.open('F:/RE_DUMP/TREES/usr_bin.tgz') as t:
    elf_data = t.extractfile('bin/im.elf').read()

elf = ELFFile(io.BytesIO(elf_data))
text = elf.get_section_by_name('.text')
text_addr = text['sh_addr']
text_data = text.data()

md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

def disasm_block(start, length):
    offset = start - text_addr
    chunk = text_data[offset:offset+length]
    for insn in md.disasm(chunk, start):
        print('0x%08x: %-10s %s' % (insn.address, insn.mnemonic, insn.op_str))

print('=== 0x97e0..0x9860: IMDB_find_target_bit caller ===')
disasm_block(0x97e0, 100)

print('\n=== 0xb400..0xb560: Dynamic library runner ===')
disasm_block(0xb400, 200)
