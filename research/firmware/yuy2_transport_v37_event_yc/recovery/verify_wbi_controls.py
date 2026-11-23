"""Execute this ZV-E10 kernel's sysfs WBI handlers with a mocked storage backend."""
from pathlib import Path
import hashlib,struct,json
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
p=Path('D:/02_Development_And_Projects/pmca-re/.local/dumps/firmware/vmlinux.bin');b=p.read_bytes()
assert hashlib.md5(b).hexdigest()=='f5b6bc225e2e5158fecabead4108e9ab'
BASE=0x60108000;GLOBAL=0x604ff780;DEV=0x61000000;BUF=0x61001000;INPUT=0x61002000;STOP=0x63000000
cases=[]
def execute(name,entry,value,count=1,fail=None):
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(BASE,0x700000);u.mem_write(BASE,b);u.mem_map(DEV,0x30000);u.mem_map(0x62000000,0x10000);u.mem_map(STOP,4096)
 put=lambda at,n:u.mem_write(at,struct.pack('<I',n&0xffffffff))
 word=lambda at:struct.unpack('<I',bytes(u.mem_read(at,4)))[0]
 put(GLOBAL,2);put(GLOBAL+4,DEV);put(GLOBAL+12,BUF);put(DEV+0x20,DEV+0x20000);put(DEV+0x24,DEV+0x20004);put(DEV+0x2c,DEV+0x20008)
 u.mem_write(BUF,b'WBI1'+b'X'*508);u.mem_write(INPUT,value)
 calls=[]
 def hook(u,a,n,data):
  r=[u.reg_read(v) for v in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]]
  if a in [0x60154704,0x601545c0,0x603cd494]:result=0
  elif a==0x6025d420:
   assert r[:2]==[BUF,512];u.mem_write(BUF,bytes(512));calls.append('zero_512_byte_header');result=0
  elif a==DEV+0x20000:
   assert r[0]==DEV;calls.append('backend_open');result=-5 if fail=='open' else 0
  elif a==DEV+0x20004:
   assert r==[DEV,BUF,0,1] and bytes(u.mem_read(BUF,512))==bytes(512);calls.append('backend_write_sector_0_count_1');result=-5 if fail=='write' else 0
  elif a==DEV+0x20008:assert r[0]==DEV;calls.append('backend_close');result=0
  else:return
  u.reg_write(UC_ARM_REG_R0,result&0xffffffff);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 u.hook_add(UC_HOOK_CODE,hook);u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,0x62008000);u.reg_write(UC_ARM_REG_LR,STOP)
 u.reg_write(UC_ARM_REG_R2,INPUT);u.reg_write(UC_ARM_REG_R3,count);u.emu_start(entry,STOP,count=2000)
 assert u.reg_read(UC_ARM_REG_PC)==STOP and u.reg_read(UC_ARM_REG_SP)==0x62008000
 rc=u.reg_read(UC_ARM_REG_R0);rc=rc if rc<0x80000000 else rc-0x100000000
 cases.append(dict(case=name,return_value=rc,image_mode=word(GLOBAL),backend_calls=calls))
 return rc,word(GLOBAL),calls
rc,mode,c=execute('drop_one_byte_1',0x6011c248,b'1');assert rc==1 and mode==2 and c==['backend_open','zero_512_byte_header','backend_write_sector_0_count_1','backend_close']
for name,value,count in [('invalid_byte',b'0',1),('empty_write',b'1',0)]:
 rc,mode,c=execute(name,0x6011c248,value,count);assert rc==-22 and not c
rc,mode,c=execute('backend_open_error',0x6011c248,b'1',fail='open');assert rc==-5 and c==['backend_open']
rc,mode,c=execute('backend_write_error',0x6011c248,b'1',fail='write');assert rc==-5 and c[-1]=='backend_close'
rc,mode,c=execute('mode_zero_one_byte',0x6011b4bc,b'0');assert rc==1 and mode==0 and not c
rc,mode,c=execute('mode_invalid_four',0x6011b4bc,b'4');assert rc==-22 and mode==2 and not c
out=dict(original_kernel_md5=hashlib.md5(b).hexdigest(),original_ARM_handlers_executed=True,cases=cases,
 limitations=['Storage backend, mutex and memory-zero helpers mocked.','Live selected backend remains wbi4; no manual physical-sector write follows from this test.'])
Path('.local/outputs/vga-v37/deployment/wbi-control-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
