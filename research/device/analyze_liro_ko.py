from elftools.elf.elffile import ELFFile

with open('dumps/staged/audit/liro.ko', 'rb') as f:
    elf = ELFFile(f)
    print('liro.ko ELF type:', elf['e_type'])
    print('Sections:')
    for sec in elf.iter_sections():
        print('  %-20s size: 0x%x' % (sec.name, sec['sh_size']))
    
    symtab = elf.get_section_by_name('.symtab')
    if symtab:
        print('Exported/Defined symbols in liro.ko:')
        for sym in symtab.iter_symbols():
            if sym['st_info']['type'] == 'STT_FUNC' and sym['st_shndx'] != 'SHN_UNDEF':
                print('  func: %s (0x%x)' % (sym.name, sym['st_value']))
