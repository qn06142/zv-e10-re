"""Build the experimental Sony SDF VGA module and PIC streaming gate offline."""
from pathlib import Path
import hashlib,json,re,struct,subprocess
from keystone import Ks,KS_ARCH_ARM,KS_MODE_THUMB
from elftools.elf.elffile import ELFFile
import argparse
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--repo',type=Path,required=True)
ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--streaming-image',type=Path,required=True)
ap.add_argument('--cc',type=Path,default=Path(r'C:\msys64\ucrt64\bin\arm-none-eabi-gcc.exe'))
args=ap.parse_args()
ROOT=args.repo.resolve()
WORK=Path(__file__).resolve().parent;OUT=args.output.resolve();OUT.mkdir(parents=True,exist_ok=True)
CC=args.cc
from generate_guards import build as generate_guards
generate_guards(ROOT,WORK/"vga_guards.h")
cmn=(ROOT/'dumps/camera_2025/usr/usr/lib/libInfraUsbCmn.so').read_bytes()
stream=args.streaming_image.read_bytes()
assert hashlib.md5(cmn).hexdigest()=='31308976206a837f6f5c571992d2b499'
assert hashlib.md5(stream).hexdigest()=='19461091c07aa6900829defb0060fcd6'
source=(WORK/'yuy2_640_v30vga.c').read_text()
for name,data in [('path_guard',stream[0x8e14:0x8e1e]),('data_guard',stream[0x9618:0x9622]),('ctrl_guard',cmn[0x12064:0x1206e])]:
 source=re.sub(r'(static const u8 '+name+r'\[10\]=)\{[^}]+\}',lambda m:m[1]+'{'+','.join(hex(b) for b in data)+'}',source)
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
guards=[]
for off in [0x7aa8,0x903e,0x8f9c,0x8dbe,0x894c,0x83c8]:
 data=stream[off:off+10];instructions=list(Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(data,off))
 assert sum(i.size for i in instructions)==10
 assert not any('pc' in i.op_str or i.mnemonic.startswith(('b','cb','it')) for i in instructions)
 guards.append('{'+','.join(hex(x) for x in data)+'}')
source=source.replace('EXTRA_GUARDS',','.join(guards))
cfg=(ROOT/'dumps/camera_2025/usr/setting/DmmConfig.bin').read_bytes()
assert struct.unpack_from('<4I',cfg,0x11c24)==(0x276,0,0x333,0xffffffff)
assert struct.unpack_from('<5I',cfg,0x2e20)==(0x333,0x320000,0x10f,0,7)
assert struct.unpack_from('<5I',cfg,0x2e34)==(0x333,0x320000,0x10f,0,4)
(OUT/'yuy2_640.c').write_text(source)
common=['-mcpu=cortex-a5','-marm','-mfpu=vfpv4-d16','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mfloat-abi=soft','-O2','-fno-builtin','-fno-stack-protector','-fstack-usage','-nostdlib',f'-L{ROOT}/build_sysroot/lib',f'-Wl,-rpath-link,{ROOT}/build_sysroot/lib']
cmd=[str(CC),*common,'-fPIC','-fvisibility=hidden','-shared','-Wl,--hash-style=sysv,-soname,yuy2_640_v30vga.so,--no-undefined','-o',str(OUT/'yuy2_640_v30vga.so'),str(OUT/'yuy2_640.c'),'-DRAW_FRAME_CONVERSION_ONLY','-DRAW_LIVE_TARGET_ARM',f'-I{WORK}',str(WORK/'vga_resize.c'),str(WORK/'vga_contract.c'),str(WORK/'sony_yc_sds.c'),str(WORK/'sony_yc_metadata.c'),'-l:libc.so.6','-l:libdl.so.2','-l:libpthread-2.11.2.so','-lgcc']
subprocess.run(cmd,check=True)

from persistent_stream import build as build_stream
patched,report=build_stream(stream)
(OUT/'libInfraStreamingUsb.so').write_bytes(patched)
(OUT/'libInfraStreamingUsb.persistent.json').write_text(json.dumps(report,indent=2)+'\n')
manifest=dict(status='BUILT_NOT_HARDWARE_VERIFIED',deployment='NOT_INSTALLED',revision='3.0-experimental-native-vga',
 position_independent=True,width=640,height=480,advertised_fps=10,observed_fps=None,
 pixel_format='YUY2 advertised / native uncompressed VGA bytes; packing UNVERIFIED',
 source_backend='SONY_SDF_PRIVATE_WORKER_OWNED_SSYC_VEF295_TO_OWNED_VGA220',
 synthetic_fallback=False,frame_bytes=614400,packet_header_bytes=0,
 cold_boot_required=True,stream_sessions_per_boot=1,files={})
for name in ['yuy2_640_v30vga.so','libInfraStreamingUsb.so']:
 data=(OUT/name).read_bytes();manifest['files'][name]=dict(bytes=len(data),md5=hashlib.md5(data).hexdigest(),sha256=hashlib.sha256(data).hexdigest())
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
