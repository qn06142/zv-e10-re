"""Execute original Sony category2 getters and native pin construction offline."""
from pathlib import Path
import sys,struct,json,hashlib
from elftools.elf.elffile import ELFFile
from unicorn import *
from unicorn.arm_const import *
sys.path.insert(0,str(Path(__file__).parent));from elf_calls import plt_names
ROOT=Path(r'D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr/lib')
OUT=Path('.local/outputs/yc-subsystem-offline-20261029');BASES={'dataflowInfraFramework.so':0x10000000,'libObj.so':0x18000000};MEM=0x40000000;STOP=0x50000000;STACK=0x60010000
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);handlers={};names={};libraries={}
for p,n in [(MEM,0x10000),(STOP,4096),(STACK-0x10000,0x20000),(0x70000000,0x10000)]:u.mem_map(p,n)
def word(p):return struct.unpack('<I',u.mem_read(p,4))[0]
def put(p,v):u.mem_write(p,struct.pack('<I',v&0xffffffff))
def cstr(p):
 b=bytearray()
 while len(b)<4096:
  x=bytes(u.mem_read(p,1))[0];p+=1
  if not x:return b.decode('ascii','replace')
  b.append(x)
 raise AssertionError('unterminated')
# Map both ELFs, then resolve own/cross-library symbols and dynamic relocations.
for filename,base in BASES.items():
 f=(ROOT/filename).open('rb');e=ELFFile(f);libraries[filename]=(f,e)
 segs=[p for p in e.iter_segments() if p['p_type']=='PT_LOAD'];end=max(p['p_vaddr']+p['p_memsz'] for p in segs);u.mem_map(base,(end+4095)&~4095)
 for p in segs:u.mem_write(base+p['p_vaddr'],p.data())
 for s in e.get_section_by_name('.dynsym').iter_symbols():
  if s['st_shndx']!='SHN_UNDEF':names[s.name]=base+s['st_value']
def external(n):
 if n in names:return names[n]
 for p,name in handlers.items():
  if name==n:return p
 p=0x70000000+len(handlers)*4;handlers[p]=n;return p
for filename,base in BASES.items():
 e=libraries[filename][1]
 for sn in ['.rel.dyn','.rel.plt']:
  sec=e.get_section_by_name(sn)
  if not sec:continue
  sy=e.get_section(sec['sh_link'])
  for r in sec.iter_relocations():
   at=base+r['r_offset'];kind=r['r_info_type']
   if kind==23:put(at,word(at)+base)
   elif kind in [2,21,22]:
    s=sy.get_symbol(r['r_info_sym']);value=base+s['st_value'] if s['st_shndx']!='SHN_UNDEF' else external(s.name)
    put(at,value+word(at) if kind==2 else value)
   elif kind!=0:raise AssertionError(('relocation',kind))
def hook(u,pc,size,data):
 if pc not in handlers:return
 n=handlers[pc];a=[u.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]]
 if n=='memset':u.mem_write(a[0],bytes([a[1]&255])*a[2]);v=a[0]
 elif n=='memcpy':u.mem_write(a[0],bytes(u.mem_read(a[1],a[2])));v=a[0]
 else:raise AssertionError(('unexpected external',n,a))
 u.reg_write(UC_ARM_REG_R0,v);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
u.hook_add(UC_HOOK_CODE,hook)
def run(address,*args):
 u.reg_write(UC_ARM_REG_CPSR,0x10);u.reg_write(UC_ARM_REG_SP,STACK);u.reg_write(UC_ARM_REG_LR,STOP)
 for r,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):u.reg_write(r,v)
 u.emu_start(address,STOP,count=100000);assert u.reg_read(UC_ARM_REG_PC)==STOP;assert u.reg_read(UC_ARM_REG_SP)==STACK
 return u.reg_read(UC_ARM_REG_R0)
raw=Path('.local/outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin').read_bytes();assert hashlib.sha256(raw).hexdigest()=='9c60c7088da03631af4cd06fbd8f9d444d084e9104ead87cb0147ef76ac45f9c'
off=struct.unpack_from('<I',raw,16)[0];payload=None
for _ in range(struct.unpack_from('<I',raw,12)[0]):
 cat,start,size,nxt=struct.unpack_from('<I4xIII',raw,off+4)
 if cat==2:payload=raw[start:start+size];break
 off=nxt
assert payload is not None
# The real constructor/getters place28payload bytes at object+0x14.
u.mem_write(MEM+0x14,payload[:28]);getters={}
for fragment,n in [('GetData_CreateStartTiming',8),('GetData_DataTransTiming',12),('GetData_Id',4),('GetData_RecordingState',1),('GetData_MainStreamStartTrigger',1),('GetData_MainStreamStopTrigger',1),('GetData_All',28)]:
 symbol=next(nm for nm in names if 'Entry_ImageOutTimInfo' in nm and fragment in nm)
 run(names[symbol],MEM,MEM+0x100);b=bytes(u.mem_read(MEM+0x100,n));getters[fragment]=dict(symbol=symbol,bytes=n,hex=b.hex(),words=list(struct.unpack('<'+str(n//4)+'I',b)) if n%4==0 else list(b))
assert getters['GetData_Id']['words']==[0x7600]
assert getters['GetData_CreateStartTiming']['words']==[0x1979,0]
assert getters['GetData_DataTransTiming']['words']==[0x197c,1,0]
# Execute the claimed native YC1Pin constructor and inspect its real object.
run(BASES['libObj.so']+0x6f5959,MEM+0x1000)
vtable=word(MEM+0x1000);rtti=word(vtable-4);type_name=cstr(word(rtti+4));pin_words=[word(MEM+0x1000+x) for x in [8,12,16,20]]
result=dict(camera_access=False,original_Sony_instructions_executed=True,category2_wire_bytes=len(payload),category2_logical_payload_bytes=28,getters=getters,native_pin=dict(constructor='libObj.so+0x6f5958 Thumb',rtti_name=type_name,property_words=pin_words,send_method='libObj.so+0x6f5a38 calls DataflowInfraPin::Send',conclusion='This object exposes an outgoing Send path; constructor alone does not establish a frame-receive subscription.'),limitations=['Getter names/layout do not prove VSYNC completion, monotonicity or a pixel lifetime lease.','Timing units and semantics of the three transfer words remain unresolved.'])
(OUT/'category2-and-pin-original-execution.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
