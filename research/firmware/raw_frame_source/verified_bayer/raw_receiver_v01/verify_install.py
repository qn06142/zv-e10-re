from pathlib import Path
import sys,json
from elftools.elf.elffile import ELFFile
from unicorn import *
from unicorn.arm_const import *
sys.path.insert(0,str(Path('.local/work/hd-v42/recipe').resolve()));import verify_support as m
MOD=Path('.local/outputs/raw-v01/raw_capture_v01.so');NATIVE=Path('D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr/lib/CameraOnDemandSaver.so');B=0x20000000;N=0x30000000
with MOD.open('rb') as f:e=ELFFile(f);defined={s.name:B+s['st_value'] for s in e.get_section_by_name('.dynsym').iter_symbols() if s['st_value']}
rows=[]
for case in ['resolved','lazy','bad_guard','bad_slot','wrong_symbol','pin_fail','protect_fail']:
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);handlers={};calls=[]
 def imp(name):
  if name in defined:return defined[name]
  a=0x10000000+len(handlers)*4;handlers[a]=name;return a
 u.mem_map(0x10000000,0x10000);s=m.load(u,MOD,B,imp);m.load(u,NATIVE,N)
 for a,n in [(m.STOP,4096),(m.STACK-0x10000,0x20000)]:u.mem_map(a,n)
 slot=N+0xa18c;old=N+(0x1108 if case=='lazy' else 0x1af5);m.put(u,slot,old)
 if case=='bad_slot':m.put(u,slot,0xdeadbeef);old=0xdeadbeef
 if case=='bad_guard':u.mem_write(N+0x1af4,b'\x00')
 def hook(u,pc,size,_):
  if pc not in handlers:return
  name=handlers[pc];a=[u.reg_read(r) for r in m.R];calls.append(name)
  if name=='memcmp':v=int(bytes(u.mem_read(a[0],a[2]))!=bytes(u.mem_read(a[1],a[2])))
  elif name=='dlopen':
   path=m.cstr(u,a[0]);v=0 if case=='pin_fail' and path.endswith('/raw_capture_v01.so') else 1
  elif name=='dlsym':v=N+0x1af5+(2 if case=='wrong_symbol' else 0)
  elif name=='getpagesize':v=4096
  elif name=='mprotect':assert a==[slot&~4095,4096,3,a[3]];v=-1 if case=='protect_fail' else 0
  else:raise AssertionError(name)
  u.reg_write(UC_ARM_REG_R0,v&0xffffffff);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 u.hook_add(UC_HOOK_CODE,hook);u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,m.STACK);u.reg_write(UC_ARM_REG_LR,m.STOP);u.reg_write(UC_ARM_REG_R0,N);u.emu_start(s['raw_v01_install'],m.STOP,count=30000)
 rc=u.reg_read(UC_ARM_REG_R0);good=case in ['resolved','lazy'];assert (rc==0)==good
 assert m.word(u,slot)==(s['raw_v01_dispatch'] if good else old)
 rows.append(dict(case=case,returncode=hex(rc),slot_changed=good,calls=calls))
Path('.local/outputs/raw-v01/install-tests.json').write_text(json.dumps(dict(compiled_ARM_executed=True,camera_access=False,cases=rows,limitations='dlopen/dlsym/mprotect/libc mocked; live module unloading, concurrency and native RAW activation not tested.'),indent=2));print('Passed seven actual ARM installer cases')
