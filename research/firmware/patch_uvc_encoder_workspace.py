"""Build a matched UVC pair with checked encoder startup; never accesses USB.

Includes the RTOS resize-workspace correction inferred from the captured
SDF_ERR_PARAM / buffer-capacity failures. Hardware validation remains pending.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB

_HERE=Path(__file__).resolve()
REPO = _HERE.parents[2] if (_HERE.parents[2]/'dumps').is_dir() else Path(r'D:\02_Development_And_Projects\pmca-re')
DEFAULT_OUTPUT=(_HERE.parent if _HERE.parent.name!='firmware' else REPO/'dumps/staged/uvc/encoder-workspace-fix')/'candidate-1080p'
STOCK = {
    'libInfraStreamingUsb.so': 'cde7a1b42c919706aa5f61aba5fc0d75',
    'libInfraUsbCmn.so': '31308976206a837f6f5c571992d2b499',
}

def assemble(source, address, size):
    code = bytes(Ks(KS_ARCH_ARM, KS_MODE_THUMB).asm(source, addr=address)[0])
    assert len(code) <= size and (size-len(code)) % 2 == 0
    return code + bytes.fromhex('00bf') * ((size-len(code))//2)

def build(source, width):
    blobs = {name: (source/name).read_bytes() for name in STOCK}
    for name, data in blobs.items():
        if hashlib.md5(data).hexdigest() != STOCK[name]:
            raise ValueError('Unexpected source hash: '+name)
    stream = bytearray(blobs['libInfraStreamingUsb.so'])
    # Same stack frame and callee-saved registers as the original, keeping its
    # ARM unwind descriptor valid. Failure returns keep state=1 and do not wake
    # the worker. Existing set_path_sync diagnostics retain the failing stage.
    stream[0x903e:0x90c0] = assemble(f'''
        push {{r4,r5,r6,r7,lr}}
        mov r4,r0
        sub sp,#12
        add r7,sp,#8
        movs r0,#4
        movs r1,#2
        movs r2,#0
        bl 0x8a64
        ldr r0,[r4,#16]
        blx 0x6328
        ldrb r6,[r4]
        cmp r6,#1
        beq valid
        ldr r0,[r4,#16]
        blx 0x60dc
        movs r0,#2
        b done
    valid:
        movs r5,#0
        ldr r0,[r4,#16]
        blx 0x60dc
        mov r1,r6
        mov r2,r5
        mov r3,r5
        mov r0,r4
        str r5,[sp]
        str r5,[sp,#4]
        blx 0x60c4
        cbnz r0,done
        movs r1,#32
        mov.w r2,#{width}
        mov.w r3,#300
        mov r0,r4
        stmia.w sp,{{r2,r3}}
        movs r2,#30
        movs r3,#5
        blx 0x60c4
        cbnz r0,done
        ldr r0,[r4,#16]
        blx 0x6328
        movs r3,#2
        strb r3,[r4]
        ldr r0,[r4,#16]
        blx 0x60dc
        ldr r0,[r4,#20]
        blx 0x60dc
        mov r0,r5
    done:
        add.w r7,r7,#4
        mov sp,r7
        pop {{r4,r5,r6,r7,pc}}
    ''',0x903e,130)
    # The immediate caller also ignored the result and latched its started flag.
    # Remove only its entry trace to make room for the return check in-place.
    stream[0x8422:0x8450] = assemble('''
        push {r3,r4,r7,lr}
        add r7,sp,#0
        blx 0x62d4
        ldrb.w r3,[r0,#62]
        mov r4,r0
        cbnz r3,already
        ldr r0,[r0,#52]
        blx 0x5c70
        cbnz r0,done
        movs r3,#1
        strb.w r3,[r4,#62]
    already:
        movs r0,#0
    done:
        pop {r3,r4,r7,pc}
    ''',0x8422,46)
    common = bytearray(blobs['libInfraUsbCmn.so'])
    # Preserve original bandwidth, interval, buffer-size and relocation fields.
    # A larger advertised bandwidth is not evidence of larger encoder buffers.
    if width == 1920:
        for off in (0x12550,0x1263e):
            assert struct.unpack_from('<HH',common,off+5)==(1280,720)
            struct.pack_into('<HH',common,off+5,1920,1080)
    return {'libInfraStreamingUsb.so':bytes(stream),'libInfraUsbCmn.so':bytes(common)},blobs

def build_rtos(repo, automatic_workspace):
    raw=(repo/'dumps/av-cam.bin').read_bytes()
    assert hashlib.md5(raw).hexdigest()=='cdcae9d4fdbf66a33704a4c7564e346d'
    patched=bytearray(raw)
    if automatic_workspace:
        assert raw[0x81097c:0x810984]==bytes.fromhex('bdf81850bdf81c40')
        # Preserve packet fields and buffer limits. Select automatic workspace
        # only for width 1920. Other widths retain the original supplied handle.
        # Stack arguments occupy 32-bit AAPCS slots. Compact loads/stores make
        # room for the conditional without changing this function's extent.
        patched[0x810978:0x8109be]=assemble('''
            push {r4,r5,r6,r7,lr}
            ldr r6,[sp,#20]
            ldr r5,[sp,#24]
            ldr r4,[sp,#28]
            uxth r5,r5
            cmp.w r6,#0x3f000
            it hs
            movhs.w r6,#0x3f000
            strh r3,[r0,#40]
            add.w r3,r6,#0x1000
            str r3,[r0,#52]
            str r6,[r0,#60]
            strh r2,[r0,#28]
            cmp.w r5,#1920
            it eq
            movweq r1,#65535
            strh.w r1,[r0,#80]
            add.w r7,r0,#64
            strh r5,[r7]
            strh r4,[r7,#2]
            strh r5,[r7,#4]
            strh r4,[r7,#6]
            ldr r5,[sp,#32]
            strb r5,[r7,#14]
            ldr r7,[sp,#36]
            strh r7,[r0,#10]
            pop {r4,r5,r6,r7,pc}
        ''',0x810978,70)
    return bytes(patched),raw

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=REPO)
    parser.add_argument('--width',type=int,choices=(1280,1920),default=1920)
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    args=parser.parse_args()
    built,stock=build(args.repo/'dumps/camera_2025/usr/usr/lib',args.width)
    built['av-cam.bin'],stock['av-cam.bin']=build_rtos(args.repo,args.width==1920)
    args.output.mkdir(parents=True,exist_ok=True)
    report={'status':'BUILT_HARDWARE_UNTESTED','width':args.width,
        'automatic_rtos_resize_workspace':args.width==1920,'files':{}}
    for name,data in built.items():
        (args.output/name).write_bytes(data)
        report['files'][name]={'md5':hashlib.md5(data).hexdigest(),
            'sha256':hashlib.sha256(data).hexdigest(),'size':len(data),
            'changed_byte_offsets':[hex(i) for i,(a,b) in enumerate(zip(stock[name],data)) if a!=b]}
    (args.output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    cs=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
    lines=[]
    for start,end in ((0x8422,0x8450),(0x903e,0x90c0)):
        for i in cs.disasm(built['libInfraStreamingUsb.so'][start:end],start):
            lines.append(f'{i.address:08x}: {i.bytes.hex():10} {i.mnemonic:9} {i.op_str}')
    (args.output/'startup.disasm.txt').write_text('\n'.join(lines)+'\n')
    (args.output/'rtos-workspace.disasm.txt').write_text('\n'.join(
        f'{i.address:08x}: {i.bytes.hex():10} {i.mnemonic:9} {i.op_str}' for i in
        cs.disasm(built['av-cam.bin'][0x810978:0x8109be],0x810978))+'\n')
    print(args.output)

if __name__=='__main__':main()
