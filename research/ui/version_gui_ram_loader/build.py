"""Build the GUI RAM-loader stage and two independently replaceable test payloads."""
import argparse,hashlib,json,struct,subprocess,sys,zlib
from pathlib import Path
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'version_gui_keys'))
from build import normalize,make_image
GCC='C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe'
OBJCOPY='C:/msys64/ucrt64/bin/arm-none-eabi-objcopy.exe'
FLAGS=['-mcpu=cortex-a5','-mthumb','-Os','-fPIE','-ffreestanding','-fno-builtin',
       '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
       '-nostdlib','-Wl,--build-id=none']


from payload_format import pack


def compile_binary(output,script,sources,extra=()):
    elf_path=output.with_suffix('.elf')
    subprocess.run([GCC,*FLAGS,*extra,'-T',str(ROOT/script),
                    *[str(ROOT/s) for s in sources],'-o',str(elf_path)],check=True)
    subprocess.run([OBJCOPY,'-O','binary','-j','.text',str(elf_path),str(output)],check=True)
    with elf_path.open('rb') as f:
        elf=ELFFile(f)
        assert not any(s['sh_type'] in ('SHT_REL','SHT_RELA') for s in elf.iter_sections())
        return {s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();original=normalize(args.input.read_bytes());args.out.mkdir(parents=True,exist_ok=True)
    manifest=args.out/'verification.json'
    if manifest.exists():manifest.unlink()
    payloads={}
    for name,text in [('hello','HELLO'),('second','RAM V2')]:
        body=args.out/(name+'.body')
        symbols=compile_binary(body,'payload.ld',['payload.c'],['-DPAYLOAD_TEXT="'+text+'"'])
        assert symbols['payload_entry']==1
        payloads[name]=pack(body.read_bytes())
    injected=args.out/'loader.body'
    symbols=compile_binary(injected,'sequence.ld',['hooks.S','syscalls.S','sequence.c','loader.c'])
    image=make_image(original,injected.read_bytes(),symbols,432)
    from verify_loader import verify_loader
    tests=verify_loader(image,symbols,payloads['hello'],payloads['second'],pack)
    target=args.out/'viewUnified6.gui-ram-loader.so';target.write_bytes(image)
    for name,data in payloads.items():(args.out/(name+'.payload.bin')).write_bytes(data)
    report={'status':'offline-original-instruction-and-RAM-payload-verified','hardware_tested':False,
       'input_sha256':hashlib.sha256(original).hexdigest(),'output_sha256':hashlib.sha256(image).hexdigest(),
       'output_md5':hashlib.md5(image).hexdigest(),'bytes':len(image),'tests':tests,
       'payloads':{n:{'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'crc32_body':hex(zlib.crc32(b[32:]))} for n,b in payloads.items()},
       'payload_path':'/log/zve10-ram-loader/payload.bin',
       'ram_contract':'anonymous RW mapping, validated file, RX protection, instruction-cache flush, returning Thumb ABI, unmap',
       'os_handoff_implemented':False,
       'source_sha256_lf':{str(p.relative_to(ROOT.parent)):hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
         for p in sorted(ROOT.glob('*')) if p.suffix in ('.py','.c','.h','.S','.ld')}}
    manifest.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['status','output_sha256','output_md5','bytes']}))


if __name__=='__main__':main()
