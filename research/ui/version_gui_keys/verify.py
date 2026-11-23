"""Execute original Version constructor, transform and layout with controlled GUI APIs."""
import io
import struct
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
    UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
    UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
    UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC)

OBJECT, STACK, WIDGET, STOP = 0x4000000, 0x5000000, 0x6000000, 0x7000000
STATE = 0x97b30


class Fixture:
    def __init__(self, image, base, state_bytes=16):
        self.state_bytes=state_bytes
        self.base = base
        self.cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        self.cpu.mem_map(base, 0x100000)
        elf = ELFFile(io.BytesIO(image))
        self.segments = list(elf.iter_segments())
        for s in self.segments:
            if s["p_type"] == "PT_LOAD": self.cpu.mem_write(base + s["p_vaddr"], s.data())
        for r in elf.get_section_by_name(".rel.dyn").iter_relocations():
            if r["r_info_type"] == 23:
                a = base + r["r_offset"]
                self.put(a, self.get(a) + base)
        for a in (OBJECT, STACK, WIDGET, STOP): self.cpu.mem_map(a, 0x10000)
        self.put(WIDGET, WIDGET + 0x1000)
        self.put(WIDGET + 0x11b4, WIDGET + 0x2001)
        self.put(WIDGET + 0x11cc, WIDGET + 0x2011)
        self.seen = {"assigned": [], "formatted": [], "widget_ids": []}
        self.pending = None
        self.external_returns = {}
        self.cpu.hook_add(UC_HOOK_CODE, self.hook)
        self.cpu.hook_add(UC_HOOK_MEM_WRITE, self.write_guard)

    def get(self, a): return struct.unpack("<I", self.cpu.mem_read(a, 4))[0]
    def put(self, a, n): self.cpu.mem_write(a, struct.pack("<I", n & 0xffffffff))
    def string(self, a): return bytes(self.cpu.mem_read(a, 128)).split(b"\0", 1)[0].decode()
    def ret(self, value=0):
        self.cpu.reg_write(UC_ARM_REG_R0, value)
        self.cpu.reg_write(UC_ARM_REG_PC, self.cpu.reg_read(UC_ARM_REG_LR))

    def write_guard(self, cpu, access, address, size, value, _):
        allowed = [(OBJECT, OBJECT + 0x10000), (STACK, STACK + 0x10000),
                   (self.base + STATE, self.base + STATE + self.state_bytes)]
        assert any(lo <= address and address + size <= hi for lo, hi in allowed), hex(address)

    def hook(self, cpu, a, size, _):
        if a == STOP: cpu.emu_stop(); return
        if a == WIDGET + 0x2000: self.ret(); return
        if a == WIDGET + 0x2010:
            self.seen["assigned"].append(self.pending); self.ret(); return
        if a == self.base + 0x221b8: self.ret(cpu.reg_read(UC_ARM_REG_R0)); return
        if not self.base + 0x16cd0 <= a < self.base + 0x17b70: return
        relative = a - self.base
        r0,r1,r2,r3 = [cpu.reg_read(r) for r in
                       (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        if relative in self.external_returns: self.ret(self.external_returns[relative])
        elif relative == 0x176fc: self.ret(r0)  # base constructor
        elif relative == 0x175f0: self.ret()  # constructor addItem
        elif relative == 0x17934: self.ret(r0)  # unknown event fallback: identity
        elif relative == 0x17054:
            cpu.mem_write(r0, bytes([r1 & 255]) * r2); self.ret(r0)
        elif relative == 0x17960:
            self.seen["widget_ids"].append(r1); self.ret(WIDGET)
        elif relative == 0x17620: self.ret(r0)
        elif relative == 0x17a0c:
            fmt = self.string(r2)
            minor = self.get(cpu.reg_read(UC_ARM_REG_SP))
            text = fmt % ((r3,minor) if fmt.count("%") == 2 else r3)
            cpu.mem_write(r0,text.encode()[:r1-1] + b"\0")
            self.seen["formatted"].append(text); self.ret(len(text))
        elif relative == 0x1799c:
            self.pending = self.string(r2); self.ret()
        elif relative in (0x175fc,0x17078,0x17088): self.ret()
        else: raise AssertionError("Unexpected external call " + hex(relative))

    def call(self, entry, r0=OBJECT, r1=3, r2=0, r3=0):
        registers = (UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
                     UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
        expected = [0x11110000 + n for n in range(len(registers))]
        for r,v in zip(registers,expected): self.cpu.reg_write(r,v)
        for r,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),(r0,r1,r2,r3)):
            self.cpu.reg_write(r,v)
        self.cpu.reg_write(UC_ARM_REG_SP,STACK + 0xf000)
        self.cpu.reg_write(UC_ARM_REG_LR,STOP | 1)
        self.cpu.emu_start(self.base + entry, STOP, count=getattr(self,"instruction_limit",20000))
        assert self.cpu.reg_read(UC_ARM_REG_PC) == STOP, "Callback did not return"
        assert self.cpu.reg_read(UC_ARM_REG_SP) == STACK + 0xf000
        assert [self.cpu.reg_read(r) for r in registers] == expected
        return self.cpu.reg_read(UC_ARM_REG_R0)

    def model(self, state=1, boot=1):
        self.put(OBJECT+4,state); self.put(OBJECT+0x174,boot)
        self.put(OBJECT+0x154,0x20003); self.put(OBJECT+0x158,0x20003)
        self.cpu.mem_write(OBJECT+0x160,b"ZV-E10\0")


def verify(original, candidate, symbols):
    evidence = []
    for base in (0x1000000,0x2200000):
        old = Fixture(original,base); new = Fixture(candidate,base)
        assert new.call(symbols["ctor_hook"],r1=0) == OBJECT
        assert new.get(base+STATE) == OBJECT and new.get(base+STATE+4) == 0
        old.model(); new.model()
        new.call(0x41a0d)
        assert "GUI KEYS" in new.seen["assigned"]
        for event in (0x15010002,0x15010012,0x15010022,0x15010032,
                      0x15010042,0x15010052,0x15010062,0x15010072,
                      0x15010082,0x15020042,0x15020052,0x150a0371,0x2108001):
            before = old.call(0x3f421,r0=event)
            count = new.get(base+STATE+8)
            new.seen["assigned"].clear()
            after = new.call(symbols["trigger_hook"],r0=event)
            assert before == after, (hex(event),hex(before),hex(after))
            if event >> 16 in (0x1501,0x1502):
                marker = "E:%06X" % (event & 0xffffff)
                assert marker in new.seen["assigned"],new.seen
                assert new.get(base+STATE+8) == count+1
            else:
                assert not new.seen["assigned"]
                assert new.get(base+STATE+8) == count
            assert new.get(OBJECT+0x154) == 0x20003
            assert new.get(OBJECT+0x158) == 0x20003
            evidence.append({"load_bias":hex(base),"event":hex(event),"original_result":hex(before),
                             "hook_result":hex(after),"assigned":new.seen["assigned"][:]})
        for state,boot in ((0,1),(2,1),(1,2)):
            new.model(state,boot); count = new.get(base+STATE+8)
            new.seen["assigned"].clear()
            new.call(symbols["trigger_hook"],r0=0x15010042)
            assert new.get(base+STATE+8) == count and not new.seen["assigned"]
        new.call(symbols["ctor_hook"],r1=0)
        assert new.get(base+STATE+4) == new.get(base+STATE+8) == 0
        # Input callback resolves through the original dynamic relocation slot.
        assert new.get(base+0x8c7a0) == base+symbols["trigger_hook"]
    return {"event_cases":evidence,"scope_controls":6,"constructor_resets":2,
            "callee_saved_and_stack_checked":True,"writes_limited_to_private_state_object_and_stack":True}
