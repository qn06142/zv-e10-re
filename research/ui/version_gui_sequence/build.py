"""Build and verify a GUI-only sequence/confirmation; never contacts the camera."""
import sys
import json
import struct
import hashlib
import subprocess
import argparse
from pathlib import Path
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent / "version_gui_keys"))
from build import make_image,normalize
from verify import Fixture,OBJECT,WIDGET,STATE,STOP
STATE_BYTES=432


def verify_sequence(original,image,symbols):
    events=[]
    for base in (0x1000000,0x2200000):
        f=Fixture(image,base,STATE_BYTES)
        old=Fixture(original,base)
        # Imported ViewBase::Exit is controlled; the hook must call this exact pointer.
        exit_stub=WIDGET+0x2021
        f.put(base+0x8c7c4,exit_stub)
        calls=[]
        def exit_hook(cpu,address,size,_):
            if address==exit_stub-1:
                calls.append(True);f.ret()
        from unicorn import UC_HOOK_CODE
        f.cpu.hook_add(UC_HOOK_CODE,exit_hook)
        f.call(symbols["ctor_hook"],r1=0); f.model(); old.model()
        clone=f.get(OBJECT)
        assert clone==base+STATE+40
        assert f.get(clone+4)==base+symbols["exit_hook"]
        assert f.get(clone-4)==f.get(base+0x8c7bc)  # Preserve RTTI metadata.
        f.call(0x41a0d)
        assert "GUI IDLE" in f.seen["assigned"]
        def raw(event):
            f.seen["assigned"].clear()
            result=f.call(symbols["trigger_hook"],r0=event)
            row={"base":hex(base),"event":hex(event),"result":hex(result),
                 "phase":f.get(base+STATE+12),"text":f.seen["assigned"][:]}
            events.append(row)
            return result
        def press(key):return raw(0x15010000 | key<<4 | 2)
        def release(key):return raw(0x15010000 | key<<4 | 1)
        def phase(n):assert f.get(base+STATE+12)==n
        # Wrong initial key preserves Sony's result and cannot arm.
        assert press(6)==old.call(0x3f421,r0=0x15010062);phase(0);release(6)
        for number,key in enumerate((5,6,5,6,4),1):
            assert press(key)==0; phase(number)
            # Duplicate down and hold must not advance or confirm.
            press(key);phase(number)
            raw(0x15010000|key<<4|4);phase(number)
            release(key);phase(number)
        assert "CONFIRM?" in f.seen["assigned"]
        assert press(4)==0;phase(6)
        assert "ARMED OK" in f.seen["assigned"]
        press(4);phase(6)  # Same down event cannot toggle the state.
        release(4)
        assert press(8)==0;phase(0)  # A fresh non-confirm key clears the demo.
        release(8)
        # Explicit cancellation at the prompt.
        for key in (5,6,5,6,4):press(key);release(key)
        press(7);phase(0);release(7)
        # Remote family and unknown local keys cannot continue a partial sequence.
        press(5);release(5);raw(0x15020062);phase(0)
        press(5);release(5);raw(0x15010022);phase(0)
        # Consumed result 0 leaves original Version main's transition outputs alone.
        f.external_returns[0x16f90]=0
        f.put(OBJECT+0x1200,0x12345678);f.put(OBJECT+0x1204,0x87654321)
        f.call(0x41281,r1=OBJECT+0x1200,r2=OBJECT+0x1204)
        assert f.get(OBJECT+0x1200)==0x12345678 and f.get(OBJECT+0x1204)==0x87654321
        # Leaving the screen clears progress through the original imported Exit.
        press(5);release(5);phase(1)
        f.call(symbols["exit_hook"]);phase(0)
        assert len(calls)==1 and f.get(base+STATE+20)==0
        # Scope controls do not mutate progress.
        for state,boot in ((0,1),(2,1),(1,2)):
            f.model(state,boot);raw(0x15010052);phase(0)
        f.model()
        # Formatter honors every capacity, including zero, with adjacent canaries.
        for capacity in (0,1,2,8,9,16):
            buf=OBJECT+0x1000
            f.cpu.mem_write(buf,b"Z"*32)
            f.call(symbols["format_hook"],r0=buf,r1=capacity)
            data=bytes(f.cpu.mem_read(buf,32))
            used=0 if capacity==0 else min(8,capacity-1)+1
            assert data[used:]==b"Z"*(32-used)
            if capacity:assert data[used-1]==0
        assert f.get(OBJECT+0x154)==f.get(OBJECT+0x158)==0x20003
    return {"events":events,"two_load_biases":True,"exit_reset":True,
            "duplicate_and_hold_rejected":True,"separate_fresh_confirmation":True,
            "scope_controls":6,"buffer_capacity_controls":12,"neutral_event_transition_controls":2,
            "callee_saved_and_stack_checked":True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    original=normalize(args.input.read_bytes())
    args.out.mkdir(parents=True,exist_ok=True)
    manifest=args.out/"verification.json"
    if manifest.exists():manifest.unlink()
    payload_elf=args.out/"sequence.elf"
    subprocess.run(["C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe","-mcpu=cortex-a5",
        "-mthumb","-Os","-fPIE","-ffreestanding","-fno-builtin","-fno-stack-protector",
        "-fno-unwind-tables","-fno-asynchronous-unwind-tables","-nostdlib",
        "-Wl,--build-id=none","-T",str(ROOT/"sequence.ld"),str(ROOT/"hooks.S"),
        str(ROOT/"sequence.c"),"-o",str(payload_elf)],check=True)
    payload_bin=args.out/"sequence.bin"
    subprocess.run(["C:/msys64/ucrt64/bin/arm-none-eabi-objcopy.exe","-O","binary",
                    "-j",".text",str(payload_elf),str(payload_bin)],check=True)
    with payload_elf.open("rb") as f:
        elf=ELFFile(f)
        symbols={s.name:s["st_value"] for s in elf.get_section_by_name(".symtab").iter_symbols()}
        assert not any(s["sh_type"] in ("SHT_REL","SHT_RELA") for s in elf.iter_sections())
    image=make_image(original,payload_bin.read_bytes(),symbols,STATE_BYTES)
    tests=verify_sequence(original,image,symbols)
    (args.out/"viewUnified6.gui-sequence.so").write_bytes(image)
    report={"status":"offline-original-instruction-verified","hardware_tested":False,
      "input_sha256":hashlib.sha256(original).hexdigest(),"output_sha256":hashlib.sha256(image).hexdigest(),
      "output_md5":hashlib.md5(image).hexdigest(),"bytes":len(image),
      "sequence":["Up","Down","Up","Down","Center"],"confirm":"separate fresh Center press",
      "markers":["GUI IDLE","SEQ 1/5 ","CONFIRM?","ARMED OK"],
      "symbols":{k:hex(symbols[k]) for k in ["ctor_hook","trigger_hook","format_hook","exit_hook"]},
      "tests":tests,"os_handoff_implemented":False,
      "source_sha256_lf":{str(p.relative_to(ROOT.parent)):hashlib.sha256(p.read_bytes().replace(b"\r\n",b"\n")).hexdigest()
                          for p in [ROOT/"hooks.S",ROOT/"sequence.c",ROOT/"sequence.ld",Path(__file__),
                                    ROOT.parent/"version_gui_keys"/"build.py",
                                    ROOT.parent/"version_gui_keys"/"verify.py"]}}
    manifest.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:report[k] for k in ["status","output_sha256","output_md5","bytes"]}))


if __name__=="__main__":main()
