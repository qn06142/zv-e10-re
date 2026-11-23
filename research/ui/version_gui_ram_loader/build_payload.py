"""Build one returning payload without rebuilding the installed GUI loader."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile
from payload_format import pack
ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=ROOT/'payload.c')
    p.add_argument('--message',default='HELLO')
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if not 1<=len(args.message)<=8 or any(ord(c)<32 or ord(c)>126 for c in args.message):
        raise ValueError('Message must be 1..8 printable ASCII characters')
    if any(c in args.message for c in ('"','\\')):
        raise ValueError('Quote/backslash messages are not supported by this build option')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    elf_path=args.out.with_suffix('.elf');body_path=args.out.with_suffix('.body')
    subprocess.run(['C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe',
        '-mcpu=cortex-a5','-mthumb','-Os','-fPIE','-ffreestanding','-fno-builtin',
        '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
        '-nostdlib','-Wl,--build-id=none','-I',str(ROOT),
        '-DPAYLOAD_TEXT="'+args.message+'"','-T',str(ROOT/'payload.ld'),
        str(args.source),'-o',str(elf_path)],check=True)
    with elf_path.open('rb') as f:
        elf=ELFFile(f)
        for section in elf.iter_sections():
            if section.name in ('.bss','.data') and section['sh_size']:
                raise ValueError('This text/rodata ABI does not support mutable global sections')
            if section['sh_type'] in ('SHT_REL','SHT_RELA'):raise ValueError('Unresolved relocation')
        symbol=next(s for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name=='payload_entry')
        if not symbol['st_value']&1:raise ValueError('Entry must be Thumb')
        entry=symbol['st_value']&~1
    subprocess.run(['C:/msys64/ucrt64/bin/arm-none-eabi-objcopy.exe','-O','binary','-j','.text',
                    str(elf_path),str(body_path)],check=True)
    blob=pack(body_path.read_bytes(),entry)
    args.out.write_bytes(blob)
    report={'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest(),
            'entry_offset':entry,'message':args.message,'abi':1,
            'loader_rebuild_required':False,'hardware_tested':False}
    args.out.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
