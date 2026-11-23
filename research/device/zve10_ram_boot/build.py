"""Compile the explicit-GO-only non-returning RAM handoff module against prepared Sony GPL headers, read-only."""
import argparse,hashlib,json,struct,subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile',choices=['reset','runtime','display','osd-compare','osd-full','osd-fire','rtos-loader','rtos-display'],default='reset')
    p.add_argument('--kernel',type=Path,required=True)
    p.add_argument('--reference-module',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();kernel=args.kernel.resolve();args.out.mkdir(parents=True,exist_ok=True)
    gcc='C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe'
    inc=subprocess.check_output([gcc,'-print-file-name=include'],text=True).strip()
    flags=['-nostdinc','-Wno-attributes','-Wno-address-of-packed-member','-isystem',inc,'-I'+str(kernel/'arch/arm/include'),
       '-I'+str(kernel/'arch/arm/include/generated'),'-I'+str(kernel/'include'),
       '-I'+str(kernel/'arch/arm/mach-cxd900x0/include'),
       '-include',str(kernel/'include/generated/autoconf.h'),
       '-include',str(kernel/'include/linux/kconfig.h'),'-D__KERNEL__','-DMODULE',
       '-D__LINUX_ARM_ARCH__=7','-DKBUILD_MODNAME="zve10_ram_boot"',
       '-DKBUILD_BASENAME="zve10_ram_boot"','-std=gnu89','-O1','-fno-strict-overflow',
       '-fno-strict-aliasing','-fno-common','-fno-delete-null-pointer-checks',
       '-fno-omit-frame-pointer','-fno-optimize-sibling-calls','-marm','-mlittle-endian',
       '-mapcs','-mno-sched-prolog','-mabi=aapcs-linux','-mno-thumb-interwork',
       '-march=armv7-a','-msoft-float','-Uarm','-fno-unwind-tables','-fno-asynchronous-unwind-tables']
    os_source=ROOT/({'reset':'os.S','runtime':'os_runtime.S','display':'os_display.S','osd-compare':'os_compare.S','osd-full':'os_compare.S','osd-fire':'os_fire.S','rtos-loader':'os_rtos_loader.S','rtos-display':'os_rtos_loader.S'}[args.profile])
    if args.profile!='reset':flags.append('-DZVE10_RESIDENT_RUNTIME=1')
    if args.profile=='display':flags.append('-DZVE10_DISPLAY_TEST=1')
    if args.profile in ('osd-compare','osd-full','osd-fire'):flags.append('-DZVE10_OSD_COMPARE=1')
    if args.profile in ('osd-full','osd-fire'):flags.append('-DZVE10_OSD_FULL=1')
    if args.profile=='osd-fire':flags.extend(['-DZVE10_OSD_FIRE=1','-ffixed-r10'])
    if args.profile in ('rtos-loader','rtos-display'):flags.append('-DZVE10_RTOS_LOADER=1')
    if args.profile=='rtos-display':flags.append('-DZVE10_RTOS_DISPLAY=1')
    os_elf=args.out/'os.elf';os_bin=args.out/'os.bin'
    subprocess.run([gcc,'-mcpu=cortex-a5','-marm','-nostdlib','-Wl,--build-id=none',
                    '-T',str(ROOT/'os.ld'),str(os_source),'-o',str(os_elf)],check=True)
    subprocess.run(['C:/msys64/ucrt64/bin/arm-none-eabi-objcopy.exe','-O','binary','-j','.text',
                    str(os_elf),str(os_bin)],check=True)
    with os_elf.open('rb') as f:
        e=ELFFile(f)
        assert not any(x['sh_type'] in ('SHT_REL','SHT_RELA') for x in e.iter_sections())
    embed=args.out/'embed.S'
    embed.write_text('.section .rodata.osimage,\"a\",%progbits\n.balign 4\n.global zve10_os_start,zve10_os_end\nzve10_os_start:\n.incbin \"'+str(os_bin.resolve()).replace('\\','/')+'\"\nzve10_os_end:\n')
    embedded=args.out/'embed.o'
    subprocess.run([gcc,'-mcpu=cortex-a5','-marm','-c',str(embed),'-o',str(embedded)],check=True)
    objects=[embedded]
    for name in ['boot','module_info']:
        output=args.out/(name+'.o')
        subprocess.run([gcc,*flags,'-c',str(ROOT/(name+'.c')),'-o',str(output)],check=True)
        objects.append(output)
    ko=args.out/'zve10_ram_boot.ko'
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
        exports={row.split()[1] for row in (kernel/'Module.symvers').read_text().splitlines() if len(row.split())>=2}
        assert set(undefined)<=exports, sorted(set(undefined)-exports)
        assert elf.get_section_by_name('__param')['sh_size']==32
        assert '__versions' not in [x.name for x in elf.iter_sections()]
        section_index=next(i for i,s in enumerate(elf.iter_sections()) if s.name=='.gnu.linkonce.this_module')
        reloc={}
        for s in elf.iter_sections():
            if s['sh_type']=='SHT_REL' and s['sh_info']==section_index:
                for r in s.iter_relocations():reloc[r['r_offset']]=sym.get_symbol(r['r_info_sym']).name
        assert reloc=={188:'init_module',308:'cleanup_module'},reloc
    report={'status':'built-ABI-guarded-not-hardware-tested','hardware_tested':False,
      'sha256':hashlib.sha256(ko.read_bytes()).hexdigest(),'bytes':ko.stat().st_size,
      'vermagic':magic.decode(),'module_layout':list(layout),'undefined_symbols':undefined,
      'privileged_operations':['prepare owned RAM code/stack and GPIO mappings','explicit GO schedules CPU0 takeover','stock device shutdown and SMP stop','inherited-MMU private-stack ARM image',('resident loop with private vectors and watchdog reset disabled' if args.profile!='reset' else 'LED pulses then force reset request')],
      'profile':args.profile,'automatic_reset':args.profile=='reset',
      'assembly_sha256':hashlib.sha256(os_source.read_bytes()).hexdigest(),
      'assembly_sources_sha256_lf':{p.name:hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in ROOT.glob('*.S')},
      'display_register_writes':(['0xf3445108 Y/Cb/Cr and native mute-control bits only'] if args.profile=='display' else ['OSD0 AIF stop, owned DDR0 source and restart'] if args.profile in ('osd-compare','osd-full','osd-fire') else []),
      'takeover_implemented':True,'takeover_executed':False,'os_bytes':os_bin.stat().st_size,'reference_sha256':hashlib.sha256(args.reference_module.read_bytes()).hexdigest(),
      'source_sha256_lf':{p.name:hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in ROOT.glob('*.c')}}
    (args.out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
