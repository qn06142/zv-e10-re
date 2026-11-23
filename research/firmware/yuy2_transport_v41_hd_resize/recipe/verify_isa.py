"""Check executable ARM function bodies for Advanced SIMD instructions."""
from pathlib import Path
import argparse, json
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
from capstone.arm import ARM_GRP_NEON

ap = argparse.ArgumentParser()
ap.add_argument('--module', type=Path, required=True)
a = ap.parse_args()
count = instructions = 0
with a.module.open('rb') as f:
    e = ELFFile(f)
    section = e.get_section_by_name('.text')
    symbols = list(e.get_section_by_name('.symtab').iter_symbols())
    mappings = sorted({(s['st_value'], s.name[1]) for s in symbols
        if s.name.startswith(('$a', '$t', '$d')) and isinstance(s['st_shndx'], int)
        and e.get_section(s['st_shndx']).name == '.text'})
    assert mappings and mappings[0][0] == section['sh_addr']
    for index, (va, mode) in enumerate(mappings):
        end = mappings[index+1][0] if index+1 < len(mappings) else section['sh_addr']+section['sh_size']
        if mode == 'd':
            continue # compiler-marked literal pool, not instructions
        lo = va-section['sh_addr']; data = section.data()[lo:lo+end-va]
        md = Cs(CS_ARCH_ARM, CS_MODE_THUMB if mode == 't' else CS_MODE_ARM)
        md.detail = True
        decoded = list(md.disasm(data, va))
        assert sum(i.size for i in decoded) == len(data), hex(va)
        for i in decoded:
            assert ARM_GRP_NEON not in i.groups, (hex(i.address), i.mnemonic, i.op_str)
        count += 1; instructions += len(decoded)
result = {'code_regions': count, 'instructions': instructions, 'neon_instructions': 0,
          'scope': '.text code regions identified by ARM mapping symbols; external libc excluded'}
a.module.with_name('isa-verification.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
