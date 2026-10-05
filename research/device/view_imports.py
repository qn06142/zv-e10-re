from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM

path = 'F:/D/lib/libBizFw.so'
with open(path, 'rb') as f:
    elf = ELFFile(f)
    plt = elf.get_section_by_name('.plt')
    base = plt['sh_addr']
    data = plt.data()
    relplt = elf.get_section_by_name('.rel.plt')
    dynsym = elf.get_section_by_name('.dynsym')
    sym_names = [s.name for s in dynsym.iter_symbols()]
    got_map = {rel['r_offset']: sym_names[rel['r_info_sym']] for rel in relplt.iter_relocations()}

    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    for addr in [0x2bd30, 0x2c280, 0x2c464, 0x2acd0]:
        off = addr - base
        insns = list(md.disasm(data[off:off+12], addr))
        # Compute target GOT address
        # insn 0: add ip, pc, #...
        # insn 1: add ip, ip, #...
        # insn 2: ldr pc, [ip, #...]
        print(f'\n0x{addr:x}:')
        for ins in insns:
            print(f'  {ins.mnemonic} {ins.op_str}')
