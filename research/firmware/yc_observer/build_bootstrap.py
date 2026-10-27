"""Generate session-specific RAM loader bytes; never access the camera."""
from pathlib import Path
import argparse,json
from keystone import Ks,KS_ARCH_ARM,KS_MODE_THUMB
p=argparse.ArgumentParser();p.add_argument('--base',type=lambda s:int(s,0),required=True)
p.add_argument('--dl-base',type=lambda s:int(s,0),required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();sb=a.base;dl=a.dl_base
asm=f'''
push.w {{r0,r1,r2,r3,r4,r5,r6,r7,r12,lr}}
adr r0,module_path
movw r1,#0x102
ldr r3,dlopen_ptr
blx r3
cbz r0,resume
adr r1,activation_name
ldr r3,dlsym_ptr
blx r3
cbz r0,resume
blx r0
resume:
pop.w {{r0,r1,r2,r3,r4,r5,r6,r7,r12,lr}}
movw r12,#{(sb+0x90c1)&65535}
movt r12,#{(sb+0x90c1)>>16}
bx r12
.align 2
dlopen_ptr: .word {dl+0xbb1}
dlsym_ptr: .word {dl+0xc49}
module_path: .asciz "/log/yc_observer/yc_observer_v2.so"
activation_name: .asciz "yc_observer_activate"
'''
k=Ks(KS_ARCH_ARM,KS_MODE_THUMB);code=bytes(k.asm(asm,addr=sb+0x9630)[0]);assert len(code)<=204
code+=b'\0'*(204-len(code))
branch=bytes(k.asm(f'b.w {sb+0x9630}',addr=sb+0x8d00)[0])+b'\x00\xbf'*4
a.output.mkdir(exist_ok=True,parents=True)
(a.output/'bootstrap-v2-after.bin').write_bytes(code);(a.output/'prepare-v2-after.bin').write_bytes(branch)
(a.output/'bootstrap-v2-context.json').write_text(json.dumps({'stream_base':sb,'dl_base':dl},indent=2)+'\n')
print('Generated RAM bootstrap for',hex(sb))
