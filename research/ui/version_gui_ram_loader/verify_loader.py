"""Original GUI instructions plus modeled Linux EABI syscalls; real ARM payload execution."""
import struct
from unicorn import UC_HOOK_INTR, UC_HOOK_CODE, UC_PROT_READ, UC_PROT_WRITE, UC_PROT_EXEC
from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,
    UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R7)
from verify import Fixture,OBJECT,WIDGET,STATE


class LoaderFixture(Fixture):
    def __init__(self,image,base,blob=None,fail=None):
        self.ram_maps={};self.blob=blob;self.fail=fail;self.fd_open=False;self.position=0
        self.syscalls=[];self.execution_count=0;self.next_map=0x9000000
        self.last_map=None;self.interrupt_reads=0;self.chunks=7
        super().__init__(image,base,432)
        self.cpu.hook_add(UC_HOOK_INTR,self.interrupt)
        self.cpu.hook_add(UC_HOOK_CODE,self.execution)

    def write_guard(self,cpu,access,address,size,value,_):
        for start,prot in self.ram_maps.items():
            if start<=address and address+size<=start+4096:
                assert prot==3,"Write to executable payload mapping"
                return
        super().write_guard(cpu,access,address,size,value,_)

    def execution(self,cpu,address,size,_):
        if any(start<=address<start+4096 for start in self.ram_maps):
            assert self.ram_maps[self.last_map]==5
            if address==self.last_map+32:self.execution_count+=1

    def interrupt(self,cpu,number,_):
        registers=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5]
        args=[cpu.reg_read(r) for r in registers];n=cpu.reg_read(UC_ARM_REG_R7)
        self.syscalls.append({"number":n,"args":args[:]})
        result=0
        if n==5:
            assert self.string(args[0])=="/log/zve10-ram-loader/payload.bin" and args[1:3]==[0,0]
            if self.blob is None:result=-2
            else:self.fd_open=True;self.position=0;result=55
        elif n==6:
            assert self.fd_open and args[0]==55;self.fd_open=False
        elif n==192:
            assert args==[0,4096,3,0x22,0xffffffff,0]
            if self.fail=="mmap":result=-12
            else:
                address=self.next_map;self.next_map+=0x2000
                self.cpu.mem_map(address,4096,UC_PROT_READ|UC_PROT_WRITE)
                self.ram_maps[address]=3;self.last_map=address;result=address
        elif n==3:
            assert self.fd_open and args[0]==55
            if self.fail=="read":result=-5
            elif self.interrupt_reads:
                self.interrupt_reads-=1;result=-4
            else:
                count=min(args[2],self.chunks,len(self.blob)-self.position)
                if count:cpu.mem_write(args[1],self.blob[self.position:self.position+count])
                self.position+=count;result=count
        elif n==125:
            assert args[:3]==[self.last_map,4096,5]
            if self.fail=="protect":result=-13
            else:self.ram_maps[self.last_map]=5;self.cpu.mem_protect(self.last_map,4096,UC_PROT_READ|UC_PROT_EXEC)
        elif n==0xf0002:
            assert self.last_map+32==args[0] and args[1]==self.last_map+len(self.blob) and args[2]==0
            if self.fail=="cache":result=-22
        elif n==91:
            assert args[:2]==[self.last_map,4096]
            if self.fail=="unmap":result=-16
            else:self.cpu.mem_unmap(self.last_map,4096);del self.ram_maps[self.last_map]
        else:raise AssertionError("Unexpected syscall: "+hex(n))
        cpu.reg_write(UC_ARM_REG_R0,result&0xffffffff)


def setup(image,base,symbols,blob=None,fail=None):
    f=LoaderFixture(image,base,blob,fail)
    f.put(base+0x8c7c4,WIDGET+0x2021)
    f.call(symbols["ctor_hook"],r1=0);f.model()
    return f


def activate(f,symbols):
    for key in (5,6,8,7):
        assert f.call(symbols["trigger_hook"],r0=0x15010000|(key<<4)|2)==0
        f.call(symbols["trigger_hook"],r0=0x15010000|(key<<4)|1)
    assert f.get(f.base+STATE+12)==4 and not f.syscalls
    f.seen["assigned"].clear()
    f.call(symbols["trigger_hook"],r0=0x15010052)


def verify_loader(image,symbols,first,second,pack):
    results=[]
    for base in (0x1000000,0x2200000):
        f=setup(image,base,symbols,first);f.interrupt_reads=2
        activate(f,symbols)
        assert f.get(base+STATE+12)==6 and "HELLO   " in f.seen["assigned"]
        assert f.execution_count==1 and not f.ram_maps and not f.fd_open
        calls=len(f.syscalls)
        f.call(symbols["trigger_hook"],r0=0x15010052) # Duplicate confirmation is inert.
        assert len(f.syscalls)==calls
        f.call(symbols["trigger_hook"],r0=0x15010051)
        f.blob=second;f.seen["assigned"].clear();f.syscalls.clear()
        activate(f,symbols)
        assert f.get(base+STATE+12)==6 and "RAM V2  " in f.seen["assigned"]
        assert f.execution_count==2 and not f.ram_maps and not f.fd_open
        assert f.get(OBJECT+0x154)==f.get(OBJECT+0x158)==0x20003
        results.append({"load_bias":hex(base),"two_payloads_without_gui_reload":True,
                        "real_ram_payload_entries":f.execution_count,"rw_to_rx_then_unmapped":True})
    bad_crc=bytearray(first);bad_crc[-1]^=1
    bad_entry=bytearray(first);struct.pack_into('<I',bad_entry,20,0xffffffff)
    bad_api=bytearray(first);struct.pack_into('<I',bad_api,28,2)
    bad_header=bytearray(first);bad_header[0]=0
    # Valid returning code with the wrong return value is rejected after execution.
    wrong_return=pack(bytes.fromhex('00207047'))
    cases=[('missing',None,None,1),('map',first,'mmap',2),('read',first,'read',3),
           ('header',bytes(bad_header),None,4),('short',first[:20],None,4),
           ('length',first+b'x',None,5),('entry',bytes(bad_entry),None,5),
           ('ABI',bytes(bad_api),None,4),('CRC',bytes(bad_crc),None,6),
           ('protect',first,'protect',7),('cache',first,'cache',8),
           ('return',wrong_return,None,9),('unmap',first,'unmap',10)]
    for name,blob,failure,expected in cases:
        f=setup(image,0x1000000,symbols,blob,failure);activate(f,symbols)
        assert f.get(f.base+STATE+12)==5,(name,f.seen)
        assert f.get(f.base+STATE+24)==expected,(name,f.get(f.base+STATE+24))
        assert not f.fd_open
        if failure!='unmap':assert not f.ram_maps
        if expected<9:assert f.execution_count==0
        assert 'ERR:%04X'%expected in f.seen['assigned'],(name,f.seen)
    return {"success":results,"failure_cases":len(cases),
            "short_reads_and_EINTR":True,"confirmation_required":True,
            "no_writable_executable_mapping":True,
            "limits":["Linux syscalls are mocked; no real kernel policy checked",
                      "Payloads execute real instructions in Unicorn with RX page permissions",
                      "A failed munmap is reported and may leave a mapping",
                      "Arbitrary valid-checksum code is not sandboxed or authenticated"]}
