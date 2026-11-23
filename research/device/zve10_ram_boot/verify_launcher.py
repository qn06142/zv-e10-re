"""Run the real GUI/user payload path with a modeled kernel module control endpoint."""
import sys,struct,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT.parents[1]/'ui/version_gui_ram_loader'),str(ROOT.parents[1]/'ui/version_gui_keys')]
from verify_loader import LoaderFixture,activate
from verify import OBJECT,WIDGET,STATE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R7


class LaunchFixture(LoaderFixture):
    def __init__(self,image,base,blob,module,failure=None):
        self.files={};self.maps={};self.kernel_loaded=False;self.kernel_state=b'READY\n'
        self.module=module;self.failure=failure;self.actions=[];self.launch_entries=0
        self.instruction_limit=250000
        super().__init__(image,base,blob)
        self.chunks=256

    def write_guard(self,cpu,access,address,size,value,_):
        for start,(length,prot,tag) in self.maps.items():
            if start<=address and address+size<=start+length:
                assert prot==3
                return
        # These writes are to modeled original GUI object/stack/private state only.
        from verify import Fixture
        Fixture.write_guard(self,cpu,access,address,size,value,_)

    def execution(self,cpu,address,size,_):
        for start,(length,prot,tag) in self.maps.items():
            if start<=address<start+length:
                assert tag=='payload' and prot==5
                entry=struct.unpack_from('<I',self.blob,20)[0]
                if address==start+32+entry:self.launch_entries+=1

    def interrupt(self,cpu,number,_):
        a=[cpu.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5)]
        n=cpu.reg_read(UC_ARM_REG_R7);self.syscalls.append({'number':n,'args':a[:]});value=0
        if n==5:
            path=self.string(a[0])
            if path=='/log/zve10-ram-loader/payload.bin':fd,data,kind=55,self.blob,'payload'
            elif path=='/log/zve10-ram-boot/boot.ko':
                fd,data,kind=57,self.module,'module'
                if self.failure=='missing_module':value=-2;fd=None
            elif path=='/sys/module/zve10_ram_boot/parameters/state':
                fd,data,kind=56,self.kernel_state,'state'
                if not self.kernel_loaded:value=-2;fd=None
            elif path=='/sys/module/zve10_ram_boot/parameters/command':
                assert self.kernel_loaded and a[1]==1
                fd,data,kind=58,b'','command'
            else:raise AssertionError(path)
            if fd is not None:self.files[fd]=[data,0,kind];value=fd
        elif n==3:
            data,pos,kind=self.files[a[0]];count=min(a[2],self.chunks,len(data)-pos)
            if count:cpu.mem_write(a[1],data[pos:pos+count])
            self.files[a[0]][1]+=count;value=count
        elif n==6:del self.files[a[0]]
        elif n==192:
            assert a[0]==0 and a[1] in (4096,16384) and a[2:]==[3,0x22,0xffffffff,0]
            address=self.next_map;self.next_map+=0x10000
            self.cpu.mem_map(address,a[1],3)
            self.maps[address]=(a[1],3,'payload' if a[1]==4096 else 'module');value=address
        elif n==125:
            length,_,tag=self.maps[a[0]];assert length==4096 and a[1:3]==[4096,5] and tag=='payload'
            self.cpu.mem_protect(a[0],length,5);self.maps[a[0]]=(length,5,tag)
        elif n==0xf0002:
            assert a[2]==0
        elif n==91:
            length,_,_=self.maps[a[0]];assert a[1]==length
            self.cpu.mem_unmap(a[0],length);del self.maps[a[0]]
        elif n==128:
            assert bytes(cpu.mem_read(a[0],a[1]))==self.module
            assert self.string(a[2])=='' and not self.kernel_loaded
            self.actions.append('INIT_MODULE')
            if self.failure=='init':value=-22
            else:self.kernel_loaded=True
        elif n==36:self.actions.append('SYNC')
        elif n==4:
            assert self.files[a[0]][2]=='command'
            assert bytes(cpu.mem_read(a[1],a[2]))==b'GO' and self.kernel_state==b'READY\n'
            self.actions.append('GO_QUEUED');self.kernel_state=b'QUEUED\n';value=2
        else:raise AssertionError('Unexpected syscall '+str(n))
        cpu.reg_write(UC_ARM_REG_R0,value&0xffffffff)


def verify(image,symbols,blob,module):
    reports=[]
    for base in (0x1000000,0x2200000):
        f=LaunchFixture(image,base,blob,module)
        f.put(base+0x8c7c4,WIDGET+0x2021)
        f.call(symbols['ctor_hook'],r1=0);f.model()
        activate(f,symbols)
        assert 'BOOT RDY' in f.seen['assigned'] and f.actions==['INIT_MODULE']
        assert f.launch_entries==1 and not f.maps and not f.files
        f.call(symbols['trigger_hook'],r0=0x15010051)
        f.syscalls.clear();activate(f,symbols)
        assert 'BOOTING ' in f.seen['assigned'],f.seen
        assert f.actions==['INIT_MODULE','SYNC','GO_QUEUED']
        assert f.launch_entries==2 and not f.maps and not f.files
        assert f.get(OBJECT+0x154)==f.get(OBJECT+0x158)==0x20003
        reports.append({'load_bias':hex(base),'first_invocation':'BOOT RDY; init only',
                        'second_invocation':'BOOTING; GO queued','actual_user_payload_entries':2})
    for failure,text in [('missing_module','NO MOD  '),('init','MOD ERR ')]:
        f=LaunchFixture(image,0x1000000,blob,module,failure)
        f.put(f.base+0x8c7c4,WIDGET+0x2021);f.call(symbols['ctor_hook'],r1=0);f.model();activate(f,symbols)
        assert text in f.seen['assigned'],(failure,f.seen)
        assert 'GO_QUEUED' not in f.actions and not f.maps and not f.files
    return {'status':'original-GUI-and-user-launcher-verified','success':reports,
            'negative_cases':2,'limits':'init_module and sysfs GO scheduling are modeled; no Linux shutdown is emulated'}


if __name__=='__main__':
    from elftools.elf.elffile import ELFFile
    image=Path(sys.argv[1]).read_bytes()
    with Path(sys.argv[2]).open('rb') as f:
        e=ELFFile(f);symbols={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols()}
    r=verify(image,symbols,Path(sys.argv[3]).read_bytes(),Path(sys.argv[4]).read_bytes())
    print(json.dumps(r))
