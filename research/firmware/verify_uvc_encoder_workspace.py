"""Execute replacement startup and unmodified RTOS dimension/buffer functions.

Hardware, OSAL and DMM services are stubbed. These tests validate control flow
and arithmetic, and cannot validate the hardware JPEG engine or USB delivery.
"""
import hashlib
import json
from pathlib import Path
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import *
from patch_uvc_encoder_workspace import build, build_rtos, REPO

OUT=REPO/'dumps/staged/uvc/encoder-workspace-fix'
REGS=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
      UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]

def startup(data,state,results,caller=False,flag=0):
    cpu=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
    for addr,size in ((0,0x20000),(0x100000,0x10000),(0x200000,0x1000),(0x300000,0x1000)):
        cpu.mem_map(addr,size)
    cpu.mem_write(0,data)
    cpu.mem_write(0x200000,bytes([state]))
    cpu.mem_write(0x200010,struct.pack('<II',0x200100,0x200200))
    cpu.mem_write(0x200834,struct.pack('<I',0x200000))
    cpu.mem_write(0x20083e,bytes([flag]))
    for i,r in enumerate(REGS):cpu.reg_write(r,0xabc000+i)
    sp=0x10fff0
    for r,v in ((UC_ARM_REG_SP,sp),(UC_ARM_REG_LR,0x300001),
                (UC_ARM_REG_R0,0x200900 if caller else 0x200000)):
        cpu.reg_write(r,v)
    calls=[];sem=[];done=[]
    def hook(uc,a,s,_):
        if a==0x300000:done.append(1);uc.emu_stop();return
        if a==0x5c70:
            uc.reg_write(UC_ARM_REG_PC,0x903f);return
        if a not in (0x8a64,0x6328,0x60dc,0x60c4,0x62d4):return
        ret=0
        if a==0x62d4:ret=0x200800
        if a in (0x6328,0x60dc):sem.append([hex(a),hex(uc.reg_read(UC_ARM_REG_R0))])
        if a==0x60c4:
            ret=results[len(calls)]
            calls.append([uc.reg_read(r) for r in (UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]+
                         list(struct.unpack('<II',bytes(uc.mem_read(uc.reg_read(UC_ARM_REG_SP),8)))))
        # AAPCS permits every external call to overwrite these registers.
        for i,r in enumerate((UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R12)):
            uc.reg_write(r,0xfeed0000+i)
        uc.reg_write(UC_ARM_REG_R0,ret&0xffffffff)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    cpu.hook_add(UC_HOOK_CODE,hook)
    cpu.emu_start(0x8423 if caller else 0x903f,0x300010,count=500)
    assert done and cpu.reg_read(UC_ARM_REG_SP)==sp
    assert all(cpu.reg_read(r)==0xabc000+i for i,r in enumerate(REGS))
    valid=state==1 and not (caller and flag)
    success=valid and results[:2]==[0,0]
    expected=0 if caller and flag else (2 if state!=1 else next((x for x in results if x),0))
    assert cpu.reg_read(UC_ARM_REG_R0)==expected&0xffffffff
    assert bytes(cpu.mem_read(0x200000,1))[0]==(2 if success else state)
    assert bytes(cpu.mem_read(0x20083e,1))[0]==(1 if caller and success else flag)
    count=0 if not valid else (1 if results[0] else 2)
    assert len(calls)==count
    if count:
        assert calls[0]==[1,0,0,0,0]
    if count==2:
        assert calls[1] in ([32,30,5,1280,300],[32,30,5,1920,300])
    assert sum(p=='0x200200' for _,p in sem)==int(success)
    # Control semaphore must always be balanced, including every failure path.
    control=[a for a,p in sem if p=='0x200100']
    assert control.count('0x6328')==control.count('0x60dc')
    return {'caller':caller,'initial_state':state,'initial_started_flag':flag,
        'injected_results':results,'configuration_calls':calls,
        'return':cpu.reg_read(UC_ARM_REG_R0),'worker_wakeups':int(success),
        'stack_and_callee_saved_registers_preserved':True}

def raw_cpu(raw, extra=None):
    c=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
    c.mem_map(0,(len(raw)+4095)&~4095);c.mem_write(0,raw)
    for addr,size in ((0x2000000,0x10000),(0x3000000,0x1000),(0x4000000,0x1000)):
        c.mem_map(addr,size)
    c.reg_write(UC_ARM_REG_SP,0x200ff00)
    c.reg_write(UC_ARM_REG_R0,0x3000000)
    c.reg_write(UC_ARM_REG_LR,0x4000001)
    def hook(uc,a,s,_):
        if extra is not None and extra(uc,a):return
        if a==0x4000000:uc.emu_stop();return
        if a in (0x4f6c90,0x817784):
            uc.reg_write(UC_ARM_REG_R0,0)
            uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
        elif a==0x15d58:
            uc.reg_write(UC_ARM_REG_R0,uc.reg_read(UC_ARM_REG_R0)//uc.reg_read(UC_ARM_REG_R1))
            uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    c.hook_add(UC_HOOK_CODE,hook)
    return c

def rtos(raw):
    report=[]
    for width in (1280,1920):
        for aspect in range(5):
            c=raw_cpu(raw)
            c.mem_write(0x3000030,struct.pack('<HH',width,0))
            c.mem_write(0x300005c,bytes([aspect]))
            c.emu_start(0x4efa41,0x4000010,count=500)
            h=c.reg_read(UC_ARM_REG_R0)
            if aspect==2:assert h==(720 if width==1280 else 1080)
            report.append({'width':width,'explicit_height':0,'aspect_enum':aspect,'derived_height':h})
        c=raw_cpu(raw);c.mem_write(0x3000030,struct.pack('<HH',width,712))
        c.emu_start(0x4efa41,0x4000010,count=500)
        assert c.reg_read(UC_ARM_REG_R0)==712
        report.append({'width':width,'explicit_height':712,'derived_height':712})
    for limit in (0x10000,0x3f000,0x50000):
        c=raw_cpu(raw)
        sp=c.reg_read(UC_ARM_REG_SP)
        c.mem_write(sp,struct.pack('<IIIII',limit,1920,1080,255,1))
        for r,v in ((UC_ARM_REG_R1,0x111),(UC_ARM_REG_R2,0x222),(UC_ARM_REG_R3,0x333)):
            c.reg_write(r,v)
        c.emu_start(0x810979,0x4000010,count=500)
        p=bytes(c.mem_read(0x3000000,0x54))
        allocated,output=struct.unpack_from('<I',p,0x34)[0],struct.unpack_from('<I',p,0x3c)[0]
        assert allocated==min(limit,0x3f000)+4096
        assert output==min(limit,0x3f000)
        assert struct.unpack_from('<HHHH',p,0x40)==(1920,1080,1920,1080)
        report.append({'requested_output_limit':limit,'jpeg_buffer_bytes':allocated,'jpeg_output_limit':output})
    return report

def workspace_check(raw,width,height,handle,capacity):
    """Execute ApiEncodeJpegWithWork's check plus its real capacity validator.

    Base input/output stream validation is an explicit successful stub. Only
    the resize-workspace validation and its public error conversion run here.
    """
    requested=[];diagnostics=[]
    def hook(c,a):
        if a==0x6de6ea:requested.append(c.reg_read(UC_ARM_REG_R2));return False
        ret=0
        if a==0x6dd240:ret=capacity
        elif a==0x6de594:ret=3
        elif a==0x5223ec:
            p=c.reg_read(UC_ARM_REG_R0);n=c.reg_read(UC_ARM_REG_R2)
            c.mem_write(p,bytes(c.mem_read(c.reg_read(UC_ARM_REG_R1),n)));ret=p
        elif a==0x6e4da0:
            p=c.reg_read(UC_ARM_REG_R0);q=c.reg_read(UC_ARM_REG_R1)
            c.mem_write(p+0xd8,bytes(c.mem_read(q+0x5c,4)))
        elif a==0xf4d44:
            diagnostics.append([c.reg_read(UC_ARM_REG_R3),
                struct.unpack('<I',bytes(c.mem_read(c.reg_read(UC_ARM_REG_SP)+12,4)))[0]])
        elif a not in (0x6dd706,0xf4e70,0xf4e58,0x6dc6d8,0x699e48,0xf4db8):return False
        c.reg_write(UC_ARM_REG_R0,ret)
        c.reg_write(UC_ARM_REG_PC,c.reg_read(UC_ARM_REG_LR));return True
    c=raw_cpu(raw,hook)
    c.reg_write(UC_ARM_REG_R1,0x3000400)
    c.mem_write(0x300045c,struct.pack('<HH',width,height))
    c.mem_write(0x300046c,struct.pack('<H',handle))
    c.emu_start(0xfab8d,0x4000010,count=2000)
    status=c.reg_read(UC_ARM_REG_R0)
    expected=0 if handle==0xffff or capacity>=width*height*2 else 16
    assert status==expected
    assert requested==([] if handle==0xffff else [width*height*2])
    if status:assert [0x4df,0x541] in diagnostics
    c.reg_write(UC_ARM_REG_R1,status);c.reg_write(UC_ARM_REG_LR,0x4000001)
    c.emu_start(0x6de493,0x4000010,count=200)
    public=c.reg_read(UC_ARM_REG_R0)
    assert public==(5 if status else 0)
    return {'width':width,'height':height,'supplied_handle':hex(handle),
        'injected_workspace_capacity':capacity,'checked_required_bytes':requested,
        'intra_status':status,'public_status':public,'diagnostics':diagnostics,
        'base_stream_validation_stubbed_success':True}

def allocation_route(raw):
    routes=[]
    def hook(c,a):
        if a==0x6edc28:
            routes.append(c.reg_read(UC_ARM_REG_R1))
        elif a not in (0xf4e70,0xf4e58):return False
        c.reg_write(UC_ARM_REG_R0,0)
        c.reg_write(UC_ARM_REG_PC,c.reg_read(UC_ARM_REG_LR));return True
    c=raw_cpu(raw,hook)
    c.mem_write(0x30000c8,struct.pack('<HH',1920,1080))
    c.emu_start(0x6efd97,0x4000010,count=500)
    assert routes==[15] and c.reg_read(UC_ARM_REG_R0)==0
    return {'size_computed_by_real_code':1920*1080*2,'selected_pool':15,
        'branch_upper_size':0x400000,'allocator_return_stubbed_success':True}

def allocation_lifetime(raw,handle):
    calls=[]
    def hook(c,a):
        if a==0x6f00e6:ret=1
        elif a in (0x10b454,0x6dd1fe,0x6edcba):calls.append(hex(a));ret=0
        elif a in (0xf4e70,0xf4e58,0x699e48):ret=0
        else:return False
        c.reg_write(UC_ARM_REG_R0,ret)
        c.reg_write(UC_ARM_REG_PC,c.reg_read(UC_ARM_REG_LR));return True
    c=raw_cpu(raw,hook);c.mem_write(0x3000228,struct.pack('<I',handle))
    c.emu_start(0x10b981,0x4000010,count=500)
    assert calls==([hex(0x10b454)] if handle==0xffff else [hex(0x6dd1fe)])
    c.reg_write(UC_ARM_REG_R0,0x3000000);c.reg_write(UC_ARM_REG_R1,0x3000400)
    c.reg_write(UC_ARM_REG_LR,0x4000001)
    c.mem_write(0x30004fe,struct.pack('<H',handle))
    c.emu_start(0x6f051d,0x4000010,count=500)
    assert (hex(0x6edcba) in calls)==(handle==0xffff)
    return {'work_handle':hex(handle),'calls':calls,'auto_workspace_released':handle==0xffff}

def compare_packet_builders(stock,patched):
    report=[]
    for width,height in ((1280,720),(1920,1080),(1920,712)):
        packets=[]
        for raw in (stock,patched):
            c=raw_cpu(raw);sp=c.reg_read(UC_ARM_REG_SP)
            c.mem_write(sp,struct.pack('<IIIII',0x3f000,width,height,255,1))
            for r,v in ((UC_ARM_REG_R1,0x123),(UC_ARM_REG_R2,0x456),(UC_ARM_REG_R3,0x789)):
                c.reg_write(r,v)
            c.emu_start(0x810979,0x4000010,count=500)
            packets.append(bytes(c.mem_read(0x3000000,0x54)))
        a,b=packets
        assert a[:0x50]==b[:0x50] and a[0x52:]==b[0x52:]
        assert struct.unpack_from('<H',a,0x50)[0]==0x123
        expected=0xffff if width==1920 else 0x123
        assert struct.unpack_from('<H',b,0x50)[0]==expected
        report.append({'width':width,'height':height,'only_changed_packet_field':'resize_work_handle',
            'old_handle':0x123,'new_handle':expected})
    return report

def main():
    source=REPO/'dumps/camera_2025/usr/usr/lib'
    report={'startup':[],'hardware_tested':False}
    for width in (1280,1920):
        pair,stock=build(source,width)
        for caller in (False,True):
            for state,results,flag in ((0,[],0),(2,[],0),(1,[0,0],0),
                (1,[4],0),(1,[-1024],0),(1,[0,4],0),(1,[0,-1024],0)):
                case=startup(pair['libInfraStreamingUsb.so'],state,results,caller,flag)
                case['width']=width;report['startup'].append(case)
            if caller:report['startup'].append(startup(pair['libInfraStreamingUsb.so'],2,[],True,1))
        # Structural invariants: no ELF metadata/relocation changes or arbitrary caves.
        ranges=((0x8422,0x8450),(0x903e,0x90c0))
        for i,(a,b) in enumerate(zip(stock['libInfraStreamingUsb.so'],pair['libInfraStreamingUsb.so'])):
            assert a==b or any(lo<=i<hi for lo,hi in ranges)
        for off in (0x12550,0x1263e):
            w,h=struct.unpack_from('<HH',pair['libInfraUsbCmn.so'],off+5)
            assert (w,h)==(width,width*9//16)
        diff={i for i,(a,b) in enumerate(zip(stock['libInfraUsbCmn.so'],pair['libInfraUsbCmn.so'])) if a!=b}
        assert diff<=set(range(0x12555,0x12559))|set(range(0x12643,0x12647))
    raw=(REPO/'dumps/av-cam.bin').read_bytes()
    assert hashlib.md5(raw).hexdigest()=='cdcae9d4fdbf66a33704a4c7564e346d'
    report['rtos']=rtos(raw)
    patched,original=build_rtos(REPO,True)
    assert original==raw
    assert {i for i,(a,b) in enumerate(zip(raw,patched)) if a!=b}<=set(range(0x810978,0x8109be))
    report['workspace_packet_comparison']=compare_packet_builders(raw,patched)
    report['workspace_validation']=[workspace_check(raw,w,h,handle,cap)
        for w,h in ((1280,720),(1920,1080)) for handle in (0x123,0xffff)
        for cap in (0x200000,0x800000)]
    report['automatic_allocation']=allocation_route(raw)
    report['allocation_lifetime']=[allocation_lifetime(raw,h) for h in (0x123,0xffff)]
    report['rtos_md5']=hashlib.md5(raw).hexdigest()
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f"Passed {len(report['startup'])} startup, {len(report['rtos'])} dimension/buffer, "
          f"{len(report['workspace_packet_comparison'])} packet, {len(report['workspace_validation'])} "
          'workspace, 1 allocation-route and 2 lifetime execution cases; hardware untested')

if __name__=='__main__':main()
