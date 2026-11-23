"""Compile a returning kernel entry probe against prepared Sony GPL headers, read-only."""
import argparse,hashlib,json,struct,subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kernel',type=Path,required=True)
    p.add_argument('--reference-module',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();kernel=args.kernel.resolve();args.out.mkdir(parents=True,exist_ok=True)
    gcc='C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe'
    inc=subprocess.check_output([gcc,'-print-file-name=include'],text=True).strip()
    flags=['-nostdinc','-isystem',inc,'-I'+str(kernel/'arch/arm/include'),
       '-I'+str(kernel/'arch/arm/include/generated'),'-I'+str(kernel/'include'),
       '-I'+str(kernel/'arch/arm/mach-cxd900x0/include'),
       '-include',str(kernel/'include/generated/autoconf.h'),
       '-include',str(kernel/'include/linux/kconfig.h'),'-D__KERNEL__','-DMODULE',
       '-D__LINUX_ARM_ARCH__=7','-DKBUILD_MODNAME="zve10_boot_bridge"',
       '-DKBUILD_BASENAME="zve10_boot_bridge"','-std=gnu89','-O1','-fno-strict-overflow',
       '-fno-strict-aliasing','-fno-common','-fno-delete-null-pointer-checks',
       '-fno-omit-frame-pointer','-fno-optimize-sibling-calls','-marm','-mlittle-endian',
       '-mapcs','-mno-sched-prolog','-mabi=aapcs-linux','-mno-thumb-interwork',
       '-march=armv7-a','-msoft-float','-Uarm','-fno-unwind-tables','-fno-asynchronous-unwind-tables']
    objects=[]
    for name in ['bridge','module_info']:
        output=args.out/(name+'.o')
        subprocess.run([gcc,*flags,'-c',str(ROOT/(name+'.c')),'-o',str(output)],check=True)
        objects.append(output)
    ko=args.out/'zve10_boot_bridge.ko'
    subprocess.run(['C:/msys64/ucrt64/bin/arm-none-eabi-ld.exe','-EL','-r',
                    *[str(x) for x in objects],'-o',str(ko)],check=True)
    with args.reference_module.open('rb') as f:
        ref=ELFFile(f);expected_size=ref.get_section_by_name('.gnu.linkonce.this_module')['sh_size']
        ref_magic=next(x for x in ref.get_section_by_name('.modinfo').data().split(b'\0') if x.startswith(b'vermagic='))
    with ko.open('rb') as f:
        elf=ELFFile(f);sym=elf.get_section_by_name('.symtab')
        layout=struct.unpack('<4I',elf.get_section_by_name('.zve10_abi').data())
        assert layout==(316,12,188,308),layout
        assert layout[0]==expected_size
        magic=next(x for x in elf.get_section_by_name('.modinfo').data().split(b'\0') if x.startswith(b'vermagic='))
        assert magic==ref_magic,(magic,ref_magic)
        undefined=sorted({s.name for s in sym.iter_symbols() if s['st_shndx']=='SHN_UNDEF' and s.name})
        assert undefined==['printk'],undefined
        section_index=next(i for i,s in enumerate(elf.iter_sections()) if s.name=='.gnu.linkonce.this_module')
        reloc={}
        for s in elf.iter_sections():
            if s['sh_type']=='SHT_REL' and s['sh_info']==section_index:
                for r in s.iter_relocations():reloc[r['r_offset']]=sym.get_symbol(r['r_info_sym']).name
        assert reloc=={188:'init_module',308:'cleanup_module'},reloc
    report={'status':'built-ABI-guarded-not-hardware-tested','hardware_tested':False,
      'sha256':hashlib.sha256(ko.read_bytes()).hexdigest(),'bytes':ko.stat().st_size,
      'vermagic':magic.decode(),'module_layout':list(layout),'undefined_symbols':undefined,
      'privileged_operations':['read CPSR','read SCTLR','read MPIDR','print result and return'],
      'takeover_implemented':False,'reference_sha256':hashlib.sha256(args.reference_module.read_bytes()).hexdigest(),
      'source_sha256_lf':{p.name:hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in ROOT.glob('*.c')}}
    (args.out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
