"""Collect repeatable original-firmware disassembly and call candidates, offline."""
from pathlib import Path
import json,hashlib
from elftools.elf.elffile import ELFFile
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
from elf_calls import plt_names,symbols,disassemble
from thumb_xrefs import direct_calls
ROOT=Path('D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr/lib')
OUT=Path('.local/outputs/yc-subsystem-offline-20261029');OUT.mkdir(parents=True,exist_ok=True)
for needle in ['ImageOutTimInfo','DataflowInfraPin','DataflowInfraReceiver']:
 (OUT/(needle+'-original.txt')).write_text(disassemble(ROOT/'dataflowInfraFramework.so',needle))
with (ROOT/'libObj.so').open('rb') as f:
 e=ELFFile(f);t=e.get_section_by_name('.text');b=t.data();base=t['sh_addr'];names=symbols(e);names.update(plt_names(e))
 regions={
 'native-receive-dispatch':[(0x7006e0,0x700940)],
 'native-type1-handler':[(0x6f71e8,0x6f72f4)],
 'native-type1-endpoints':[(0x6f6eec,0x6f71e8)],
 'native-pin-receiver-regions':[(0x700940,0x700b2c),(0x6f5a38,0x6f5aa8),(0x6f5bbc,0x6f5c80),(0x6f5fa0,0x6f60b0)]}
 for label,ranges in regions.items():
  out=[]
  for start,end in ranges:
   out.append('\nRANGE '+hex(start))
   for i in Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(b[start-base:end-base],start):
    target=int(i.op_str[1:],16) if i.mnemonic in ['bl','blx','b.w'] and i.op_str.startswith('#0x') else None
    out.append(f'{i.address:08x}: {i.mnemonic:9} {i.op_str} '+names.get(target,''))
  (OUT/(label+'.txt')).write_text('\n'.join(out)+'\n')
 targets={a:n for a,n in names.items() if 'DataflowInfraReceiver' in n or 'DataflowInfraPin' in n}
 targets.update({0x6f5958:'YC1Pin constructor',0x6f5994:'YC1Pin allocate',0x6f5a38:'YC1Pin outgoing Send'})
 out=[f'{a:08x}: {targets[target]} ({target:08x})' for a,target in direct_calls(b,base) if target in targets]
 (OUT/'libObj-pin-receiver-call-candidates.txt').write_text('\n'.join(out)+'\n')
inputs=[]
for name in ['dataflowInfraFramework.so','libObj.so']:
 data=(ROOT/name).read_bytes();inputs.append(dict(name=name,bytes=len(data),md5=hashlib.md5(data).hexdigest(),sha256=hashlib.sha256(data).hexdigest()))
(OUT/'firmware-input-hashes.json').write_text(json.dumps(dict(camera_access=False,inputs=inputs,notes=['Addresses are original library-relative virtual addresses with Thumb bit cleared in text.','Call scan emits candidates, not a complete reachable call graph.','Linear disassembly may decode literal pools as instructions; branch targets and execution fixtures establish the claims.']),indent=2)+'\n')
print('Saved original-library evidence and verified input hashes.')
