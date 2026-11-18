from pathlib import Path
import subprocess,json,hashlib
from elftools.elf.elffile import ELFFile
r=Path('D:/02_Development_And_Projects/pmca-re');o=Path('.local/outputs/raw-v01');cc='C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe'
cmd=[cc,'-std=c11','-mcpu=cortex-a5','-marm','-mfloat-abi=soft','-O2','-fPIC','-fvisibility=hidden','-fno-builtin','-fno-stack-protector','-nostdlib','-shared','-Wl,--hash-style=sysv,-soname,raw_capture_v01.so,--no-undefined','-L'+str(r/'.local/build_sysroot/lib'),'-Wl,-rpath-link,'+str(r/'.local/build_sysroot/lib'),'-o',str(o/'raw_capture_v01.so'),'.local/work/raw-v01/capture.c','.local/work/raw-v01/runtime.c','.local/work/raw-v01/install.c','-l:libc.so.6','-l:libdl.so.2','-lgcc']
subprocess.run(cmd,check=True)
p=o/'raw_capture_v01.so'
with p.open('rb') as f:
 e=ELFFile(f);exports=[s.name for s in e.get_section_by_name('.dynsym').iter_symbols() if s['st_value'] and s['st_info']['bind']=='STB_GLOBAL'];assert all(e.get_section_by_name(n) is None or not e.get_section_by_name(n)['sh_size'] for n in ['.init_array','.ctors'])
 original=r/'.local/dumps/camera_2025/usr/usr/lib/CameraOnDemandSaver.so'
 with original.open('rb') as ff:
  ne=ELFFile(ff);rels=[]
  for s in ne.iter_sections():
   if s['sh_type']!='SHT_REL':continue
   sy=ne.get_section(s['sh_link'])
   for rr in s.iter_relocations():
    n=sy.get_symbol(rr['r_info_sym']).name
    if '10fsys_writeE' in n:rels.append(dict(symbol=n,offset=hex(rr['r_offset']),type=rr['r_info_type']))
 report=dict(status='OFFLINE_RECEIVER_COMPONENT_NOT_INSTALLED',source_library_md5=hashlib.md5(original.read_bytes()).hexdigest(),component_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size,exports=exports,hook_relocation_candidates=rels,camera_access=False,sensor_activation_implemented=False,guarded_installer_implemented=True,usb_spool_implemented=False)
(o/'build.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

