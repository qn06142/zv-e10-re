"""Build a volatile 640x480/10fps YUY2 synthetic producer; no USB operations."""
from pathlib import Path
import hashlib,json,re,struct,subprocess
from keystone import Ks,KS_ARCH_ARM,KS_MODE_THUMB
from elftools.elf.elffile import ELFFile
import argparse
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--repo',type=Path,required=True)
ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--streaming-image',type=Path,required=True)
ap.add_argument('--stream-base',type=lambda v:int(v,0),default=0x0a73d000)
ap.add_argument('--cc',type=Path,default=Path(r'C:\msys64\ucrt64\bin\arm-none-eabi-gcc.exe'))
args=ap.parse_args()
ROOT=args.repo.resolve()
WORK=Path(__file__).resolve().parent;OUT=args.output.resolve();OUT.mkdir(parents=True,exist_ok=True)
CC=args.cc
cmn=(ROOT/'dumps/camera_2025/usr/usr/lib/libInfraUsbCmn.so').read_bytes()
stream=args.streaming_image.read_bytes()
assert hashlib.md5(cmn).hexdigest()=='31308976206a837f6f5c571992d2b499'
assert hashlib.md5(stream).hexdigest()=='19461091c07aa6900829defb0060fcd6'
source=(WORK/'yuy2_640_v23.c').read_text()
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
common=['-mcpu=cortex-a9','-marm','-mfloat-abi=soft','-O2','-fno-builtin','-fno-stack-protector','-fstack-usage','-nostdlib',f'-L{ROOT}/build_sysroot/lib',f'-Wl,-rpath-link,{ROOT}/build_sysroot/lib']
cmd=[str(CC),*common,'-fPIC','-fvisibility=hidden','-shared','-Wl,--hash-style=sysv,-soname,yuy2_640_v23.so,--no-undefined','-o',str(OUT/'yuy2_640_v23.so'),str(OUT/'yuy2_640.c'),'-l:libc.so.6','-l:libdl.so.2','-lgcc']
subprocess.run(cmd,check=True)
subprocess.run([str(CC),*common,'-Wl,--dynamic-linker=/lib/ld-linux.so.3,-e,_start,--hash-style=sysv','-o',str(OUT/'checked_mempatch.elf'),str(WORK/'checked_mempatch.c'),str(WORK/'arm_linux_start.S'),'-l:libc.so.6','-lgcc'],check=True)

# Bases are the read-only preflight result, checked again at deployment time.
sb=args.stream_base;cb=0x04834000;dl=0x040ba000
assert sb>=0x10000 and sb%4096==0
path=b'/log/yuy2_640_v23/yuy2_640_v23.so\0'
label=b'yuy2_status\0'
asm=f'''
 push {{r0,r1,r2,r3,r4,r5,r6,lr}}
 adr r0,module_path
 movw r1,#0x102
 ldr r3,dlopen_pointer
 blx r3
 cbz r0,failed
 adr r1,status_name
 ldr r3,dlsym_pointer
 blx r3
 cbz r0,failed
 blx r0
 cmp r0,#1
 bne failed
 pop.w {{r0,r1,r2,r3,r4,r5,r6,lr}}
 push {{r3,r4,r5,r6,r7,lr}}
 movs r1,#0
 mov r4,r0
 add r7,sp,#0
 movs r0,#4
 mov r2,r1
 movw r12,#{((sb+0x8d0c)|1)&65535}
 movt r12,#{(sb+0x8d0c)>>16}
 bx r12
failed:
 pop.w {{r0,r1,r2,r3,r4,r5,r6,lr}}
 movs r0,#4
 bx lr
 .align 2
dlopen_pointer: .word {dl+0xbb1:#x}
dlsym_pointer: .word {dl+0xc49:#x}
module_path: .byte {','.join(str(x) for x in path)}
status_name: .byte {','.join(str(x) for x in label)}
'''
code=bytes(Ks(KS_ARCH_ARM,KS_MODE_THUMB).asm(asm,addr=sb+0x90c0)[0])
assert len(code)<=380
code+=b'\x00\xbf'*((380-len(code))//2)
assert len(code)==380
branch=bytes(Ks(KS_ARCH_ARM,KS_MODE_THUMB).asm(f'b.w {sb+0x90c0:#x}',addr=sb+0x8d00)[0])
hook=branch+b'\x00\xbf'*4
assert len(hook)==12
for name,b in [('bootstrap-before.bin',stream[0x90c0:0x923c]),('bootstrap-after.bin',code),('prepare-before.bin',stream[0x8d00:0x8d0c]),('prepare-after.bin',hook)]:
 (OUT/name).write_bytes(b)
blobs=[]
for old in [cmn[0x12537:0x12574],cmn[0x12625:0x12662]]:
 header=bytearray(old[:14]);struct.pack_into('<H',header,4,77)
 fmt=bytes([27,0x24,4,1,1])+bytes.fromhex('5955593200001000800000aa00389b71')+bytes([16,1,0,0,0,0])
 frame=struct.pack('<BBBBBHHIIIIBI',30,0x24,5,1,0,640,480,49152000,49152000,614400,1000000,1,1000000)
 blob=bytes(header)+fmt+frame+bytes([6,0x24,13,4,1,4]);assert len(blob)==77;blobs.append(blob)
(OUT/'descriptors.bin').write_bytes(b''.join(blobs))
bars=[(235,128,128),(210,16,146),(170,166,16),(145,54,34),(106,202,222),(81,90,240),(41,240,110),(16,128,128)]
row=b''.join(bytes([y,u,y,v])*40 for y,u,v in bars)
frame=row*472+bytes([16,128,16,128])*(640*8//2)
assert len(frame)==614400
(OUT/'expected-frame-00000.yuy2').write_bytes(frame)
manifest=dict(status='BUILT_NOT_HARDWARE_VERIFIED',revision='2.3',source_unit='0x276',source_extent='0x333',configured_source_bytes=0x320000,width=640,height=480,fps=10,pixel_format='YUY2',frame_bytes=614400,stream_base=hex(sb),common_base=hex(cb),libdl_base=hex(dl),files={})
for p in OUT.iterdir():
 if p.suffix in ['.so','.elf','.bin','.yuy2']:
  a=p.read_bytes();manifest['files'][p.name]=dict(bytes=len(a),md5=hashlib.md5(a).hexdigest(),sha256=hashlib.sha256(a).hexdigest())
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
