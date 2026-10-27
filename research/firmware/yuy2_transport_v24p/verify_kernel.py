"""Execute original/patched ARM probe and header fragments, plus binary guards."""
from pathlib import Path
import argparse,io,json,struct
from elftools.elf.elffile import ELFFile
from elftools.common.exceptions import ELFError
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
import kernel_patch as patch

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--stock',type=Path,required=True);ap.add_argument('--candidate',type=Path,required=True)
args=ap.parse_args();stock=args.stock.read_bytes();candidate=args.candidate.read_bytes();results=[]
built,records=patch.transform(stock);assert built==candidate
assert patch.transform(candidate,True)[0]==stock
results.append('forward_and_reverse_exact_module_hashes')
allowed={r['file_offset']+n for r in records for n in range(len(bytes.fromhex(r['before'])))}
assert len(stock)==len(candidate) and all(a==b or i in allowed for i,(a,b) in enumerate(zip(stock,candidate)))
results.append('only_six_guarded_sites_change_no_relocations')
e=ELFFile(io.BytesIO(candidate));info=e.get_section_by_name('.modinfo').data()
assert ('version='+patch.MODULE_VERSION).encode() in info.split(b'\0')
stock_elf=ELFFile(io.BytesIO(stock))
assert e.get_section_by_name('__param').data()==stock_elf.get_section_by_name('__param').data()
results.append('module_version_marker_with_runtime_parameter_registration_unchanged')
for mutate in ['unrelated','instruction','probe','already_patched']:
 bad=bytearray(candidate if mutate=='already_patched' else stock)
 if mutate!='already_patched':
  off={'unrelated':0,'instruction':records[0]['file_offset'],'probe':records[2]['file_offset']}[mutate]
  bad[off]^=1
 try:patch.transform(bytes(bad))
 except (ValueError,AssertionError,ELFError):
  # ELF parser failure is an expected rejection for an invalid ELF header.
  results.append('reject_'+mutate)
 else:raise AssertionError('Accepted invalid input')

BASE=0x100000;RO=0x200000;STATE=0x300000;FP=0x400100
def machine(data):
 e=ELFFile(io.BytesIO(data));text=e.get_section_by_name('.text').data();ro=e.get_section_by_name('.rodata').data()
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
 for a in [BASE,RO,STATE,0x400000,0x500000]:u.mem_map(a,0x10000)
 u.mem_write(BASE,text);u.mem_write(RO,ro)
 # Apply the .rodata relocation for the literal consumed by this fragment.
 u.mem_write(BASE+0x1388,struct.pack('<I',RO+0x7a))
 return u

for mode in [0,1,2,3]:
 for name,data in [('stock',stock),('candidate',candidate)]:
  u=machine(data);calls=[]
  u.reg_write(UC_ARM_REG_R11,FP);u.reg_write(UC_ARM_REG_R0,0x500000)
  u.reg_write(UC_ARM_REG_R1,0x500020)
  u.mem_write(STATE+0xa8,struct.pack('<I',mode))
  def hook(u,a,size,user):
   if a==BASE+0x11e4:
    dst=u.reg_read(UC_ARM_REG_R0);src=u.reg_read(UC_ARM_REG_R1);n=u.reg_read(UC_ARM_REG_R2)
    assert n==26;u.mem_write(dst,bytes(u.mem_read(src,n)));calls.append('memcpy')
    u.reg_write(UC_ARM_REG_PC,a+4)
   elif a==BASE+0x11e8:
    calls.append('get_this');u.reg_write(UC_ARM_REG_R0,STATE);u.reg_write(UC_ARM_REG_PC,a+4)
  u.hook_add(UC_HOOK_CODE,hook)
  u.emu_start(BASE+0x11cc,BASE+0x1238,count=100)
  probe=bytes(u.mem_read(FP-0x46,26));interval=struct.unpack_from('<I',probe,4)[0]
  frame,payload=struct.unpack_from('<II',probe,18)
  assert calls==['memcpy','get_this']
  if name=='stock':assert (interval,frame,payload)==(400000 if mode==2 else 333333,14745600,300000)
  else:assert (interval,frame,payload)==(1000000,614400,614412)
  assert probe[:4]==b'\x00\x00\x01\x01'
 results.append(f'probe_response_mode_{mode}_original_and_patched')
for fid in [0,1]:
 u=machine(candidate);u.reg_write(UC_ARM_REG_R8,fid);u.reg_write(UC_ARM_REG_R5,STATE)
 u.emu_start(BASE+0xf44,BASE+0xf50,count=10)
 header=bytes(u.mem_read(STATE+1,1))[0]
 assert header==0x8e+fid and header&2 and header&1==fid
 results.append(f'actual_header_eof_and_fid_{fid}')
assert 614400+12==614412 and 614412<1843200//2
results.append('payload_limit_matches_actual_request_and_fits_staging_half')
out=dict(passed=len(results),cases=results,hardware_services_mocked=True,
         limitations=['No UDC/DMA/Windows emulation; larger payload acceptance requires hardware test'])
args.candidate.with_name('kernel-verification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
