"""Execute observer ARM code against real Sony ELF relocation tables, offline."""
from pathlib import Path
import importlib.util, json, struct
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
from elftools.elf.elffile import ELFFile
REPO=Path('D:/02_Development_And_Projects/pmca-re')
OUT=Path('outputs/sony-backend-recovery/candidate')
spec=importlib.util.spec_from_file_location('support',REPO/'research/firmware/yuy2_transport_v25/verify_support.py')
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
U=Uc(UC_ARCH_ARM,UC_MODE_ARM)
for a,n in [(0x10000000,0x10000),(0x40000000,0x40000),(0x50000000,4096),(0x60000000,0x20000)]:U.mem_map(a,n)
handlers={};opened=[];original_args=[]
def imported(name):
    regs=[U.reg_read(r) for r in support.R]
    if name=='strcmp':return (support.cstr(U,regs[0])>support.cstr(U,regs[1]))-(support.cstr(U,regs[0])<support.cstr(U,regs[1]))
    if name=='snprintf':return 0 # logging body exercised separately; no format emulation
    if name=='syscall':return 123
    if name=='open':opened.append(support.cstr(U,regs[0]));return -1
    if name=='dlopen':return 1
    if name=='dlsym':return framework+0x246d7 if 'GetData_All' in support.cstr(U,regs[1]) else CTOR
    if name=='dl_iterate_phdr':return 0
    raise AssertionError(name)
def imp(name):
    address=0x10000000+len(handlers)*4
    handlers[address]=lambda:imported(name)
    return address
syms=support.load(U,OUT/'yc_observer.so',0x20000000,imp)
framework=0x08fa2000
support.load(U,REPO/'dumps/camera_2025/usr/usr/lib/dataflowInfraFramework.so',framework)
CTOR=0x1000f000
def ctor():
    original_args.append([U.reg_read(r) for r in support.R]);return U.reg_read(UC_ARM_REG_R0)
handlers[CTOR]=ctor
def hook(u,address,size,user):
    if address in handlers:
        result=handlers[address]();u.reg_write(UC_ARM_REG_R0,result&0xffffffff)
        u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
U.hook_add(UC_HOOK_CODE,hook)
def run(name,*args):
    U.reg_write(UC_ARM_REG_CPSR,0x10);U.reg_write(UC_ARM_REG_SP,support.STACK);U.reg_write(UC_ARM_REG_LR,support.STOP)
    for r,v in zip(support.R,args):U.reg_write(r,v)
    U.emu_start(syms[name],support.STOP,count=500000)
    assert U.reg_read(UC_ARM_REG_PC)==support.STOP,name
    assert U.reg_read(UC_ARM_REG_SP)==support.STACK,name
    return U.reg_read(UC_ARM_REG_R0)
results=[]
assert run('yc_observer_activate')==0 # no fake callback modules supplied yet
results.append('activation_resolves_originals_without_hooks_or_camera_calls')
lib=REPO/'dumps/camera_2025/usr/usr/lib/libBizFw.so';base=0x05792000
support.load(U,lib,base)
with lib.open('rb') as f:
    e=ELFFile(f);phoff=e['e_phoff'];phnum=e['e_phnum']
INFO=0x40000000;NAME=INFO+0x100;U.mem_write(NAME,b'/usr/lib/libBizFw.so\0')
U.mem_write(INFO,struct.pack('<IIIH',base,NAME,base+phoff,phnum))
slots=[base+0x544e8,base+0x5513c]
before=[support.word(U,p) for p in slots]
assert run('visit',INFO,16,0)==0
assert support.word(U,slots[0])==syms['getall_hook'] and support.word(U,slots[1])==syms['ctor_hook']
assert support.word(U,syms['hooks'])==2
results.append('real_libBizFw_relocations_identify_and_patch_only_two_matching_GOT_slots')
run('visit',INFO,16,0);assert support.word(U,syms['hooks'])==2
results.append('repeated_scan_is_idempotent')
ENTRY=0x40001000;DEST=0x40002000
metadata=bytes((i*17+3)&255 for i in range(60));U.mem_write(ENTRY+20,metadata)
U.mem_write(DEST,b'\xee'*64);run('getall_hook',ENTRY,DEST)
assert bytes(U.mem_read(DEST,64))==metadata+b'\xee'*4
results.append('real_framework_thumb_GetData_All_copies_exact_60_bytes_and_preserves_canary')
assert run('ctor_hook',ENTRY,0x12345678,0x11223344,7)==ENTRY
assert original_args==[[ENTRY,0x12345678,0x11223344,7]]
results.append('constructor_wrapper_preserves_all_four_arguments_and_result')
opened_before=len(opened)
for _ in range(34):run('getall_hook',ENTRY,DEST)
assert support.word(U,syms['meta_count'])==35
assert len(opened)-opened_before==31 # only metadata events 2..32 log
results.append('metadata_hook_remains_safe_after_capture_limit')
# Restore fixtures, then remove write permission in the real PT_LOAD headers.
for address,value in zip(slots,before):support.put(U,address,value)
for i in range(phnum):
    at=base+phoff+i*32
    if support.word(U,at)==1:support.put(U,at+24,support.word(U,at+24)&~2)
run('visit',INFO,16,0)
assert [support.word(U,p) for p in slots]==before
results.append('read_only_LOAD_GOT_is_not_patched')
# Replay the camera's actual relocated dynamic table, not just on-disk pointers.
with lib.open('rb') as f:
    e=ELFFile(f);dynamic_address=base+e.get_section_by_name('.dynamic')['sh_addr']
    f.seek(phoff);headers=f.read(phnum*32)
U.mem_write(base+phoff,headers)
live=Path('outputs/sony-backend-recovery/deployment/libBizFw.so.dynamic-live.bin').read_bytes()
U.mem_write(dynamic_address,live)
run('visit',INFO,16,0)
assert support.word(U,slots[0])==syms['getall_hook'] and support.word(U,slots[1])==syms['ctor_hook']
results.append('camera_runtime_absolute_dynamic_pointers_resolve_same_two_GOT_slots')
result={'passed':len(results),'cases':results,'uses_real_Sony_ELF_tables_and_GetData_All':True,'camera_access':False}
(OUT/'observer-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
