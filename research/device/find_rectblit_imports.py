import glob, os
from elftools.elf.elffile import ELFFile

grm_callers = {}
for p in glob.glob('F:/D/lib/*.so'):
    try:
        with open(p, 'rb') as f:
            elf = ELFFile(f)
            dynsym = elf.get_section_by_name('.dynsym')
            if not dynsym: continue
            for s in dynsym.iter_symbols():
                if s.name.startswith('GRM_') and s['st_shndx'] == 'SHN_UNDEF':
                    fn = os.path.basename(p)
                    grm_callers.setdefault(fn, []).append(s.name)
    except Exception as e:
        pass

print(f'Libraries importing GRM_* symbols: {len(grm_callers)}')
for lib, syms in grm_callers.items():
    print(f'{lib}: {syms}')
