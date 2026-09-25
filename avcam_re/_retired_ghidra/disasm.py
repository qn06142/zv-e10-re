#!/usr/bin/env python3
"""Recursive-descent disassembler for ZV-E10 av-cam.bin (plaintext ARM/Thumb, base 0x635c6000).
Seeds from vector table (@12) + pointer tables (consecutive in-range ptrs).
Emits code coverage, xrefs (LDR/ADR/bx/bl targets), and a function map.
"""
import struct, math, re, os, sys
import capstone
from capstone import CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB, CS_OP_MEM, CS_OP_IMM
from capstone.arm import ARM_REG_PC, ARM_REG_LR

BASE = 0x635c6000
SRC  = r"C:\Users\Minhsnguhoa\pmca-re\dumps\av-cam.bin"
OUT  = r"C:\Users\Minhsnguhoa\pmca-re\avcam_re\out"
os.makedirs(OUT, exist_ok=True)

d = open(SRC,"rb").read()
N = len(d)
def off2va(o): return BASE + o
def va2off(v): return v - BASE
def valid_va(v): o=v-BASE; return 0 <= o < N
def rd32(o): return struct.unpack_from("<I", d, o)[0] if 0 <= o <= N-4 else None
def rd16(o): return struct.unpack_from("<H", d, o)[0] if 0 <= o <= N-2 else None

# ---- float-run map ----
def isf32(x): return math.isfinite(x) and abs(x)<1e6 and abs(x)>=1e-12
FLOAT={}
i=0
while i+4<=N:
    c=0;s=i
    while i+4<=N:
        x=struct.unpack_from("<f",d,i)[0]
        if isf32(x): c+=1;i+=4
        else: break
    if c>=16: FLOAT[s]=c
    else: i+=4

# ---- string map ----
STR={}
for m in re.finditer(rb'[ -~]{5,}', d):
    STR[m.start()] = m.group().decode('latin1','replace')

md_arm = capstone.Cs(CS_ARCH_ARM, CS_MODE_ARM); md_arm.detail=True
md_thb = capstone.Cs(CS_ARCH_ARM, CS_MODE_THUMB); md_thb.detail=True

visited=set()        # (va, mode)
code_va=set()        # disassembled VAs
funcs=[]             # (va, off, mode, size)
xrefs=[]             # (src, kind, tgt_va, tgt_off)
MAXFN=30000
TOTALCAP=6_000_000

def thumb_pcrel(ins):
    pc = (ins.address & ~3) + 4
    for op in ins.operands:
        if op.type==CS_OP_MEM and op.mem.base==ARM_REG_PC:
            return pc + op.mem.disp
    return None
def arm_pcrel(ins):
    pc = (ins.address + 8) & ~3
    for op in ins.operands:
        if op.type==CS_OP_MEM and op.mem.base==ARM_REG_PC:
            return pc + op.mem.disp
    return None

def disasm_func(va, mode):
    if (va,mode) in visited: return None
    md = md_thb if mode==CS_MODE_THUMB else md_arm
    start=va; count=0; cur=va
    while True:
        if cur in code_va: break
        o=va2off(cur)
        if not (0 <= o <= N-2): break
        res=list(md.disasm(d[o:o+4], cur, count=1))
        if not res:
            res=list(md.disasm(d[o:o+2], cur, count=1))
            if not res: break
        ins=res[0]
        if (ins.address,mode) in visited: break
        visited.add((ins.address,mode)); code_va.add(ins.address)
        mnem=ins.mnemonic
        # data xref (PC-relative)
        tgt = thumb_pcrel(ins) if mode==CS_MODE_THUMB else arm_pcrel(ins)
        if tgt is not None and valid_va(tgt):
            to=va2off(tgt)
            kind="ldr" if mnem.startswith("ldr") or mnem.startswith("adr") else "mem"
            xrefs.append((ins.address, kind, tgt, to))
        # control flow
        is_call = mnem.startswith("bl")
        is_branch = mnem.startswith("b") or mnem in ("bx","blx","bxj")
        if is_call or mnem in ("bx","blx"):
            for op in ins.operands:
                if op.type==CS_OP_IMM:
                    xrefs.append((ins.address,"call",op.imm, va2off(op.imm) if valid_va(op.imm) else -1))
        if mnem in ("bx","bxj"): break
        if mnem=="pop":
            # pop {..,pc} ends function
            for op in ins.operands:
                if op.type==capstone.CS_OP_REG and op.reg==ARM_REG_PC:
                    pass
            # conservatively: treat pop as possible end
        if is_branch and not is_call:
            for op in ins.operands:
                if op.type==CS_OP_IMM:
                    xrefs.append((ins.address,"branch",op.imm, va2off(op.imm) if valid_va(op.imm) else -1))
                    if op.imm > cur: break  # forward -> likely func tail
        cur = ins.address + ins.size
        count+=1
        if count>MAXFN or len(code_va)>TOTALCAP: break
    sz=cur-start
    return (cur, mode, sz)

def seed_entries():
    seeds=[]
    # vector table @12 (ARM): 4-byte absolute pointers
    for o in range(12, 0x400, 4):
        v=rd32(o)
        if v is None: break
        if BASE <= v < BASE+N:
            mode = CS_MODE_THUMB if (v&1) else CS_MODE_ARM
            seeds.append((v & ~1, mode))
    # reset stub: b #0x28 at off0 -> ARM entry
    seeds.append((BASE+0x28, CS_MODE_ARM))
    # pointer tables: arrays of consecutive in-range ptrs
    run=[]
    for o in range(0, N-3, 4):
        v=rd32(o)
        if v is not None and BASE <= v < BASE+N:
            run.append(o)
        else:
            if len(run)>=4:
                for ro in run:
                    v=rd32(ro)
                    mode=CS_MODE_THUMB if (v&1) else CS_MODE_ARM
                    seeds.append((v&~1, mode))
            run=[]
    if len(run)>=4:
        for ro in run:
            v=rd32(ro); mode=CS_MODE_THUMB if (v&1) else CS_MODE_ARM
            seeds.append((v&~1, mode))
    # dedupe
    seen=set(); uniq=[]
    for s in seeds:
        if s not in seen: seen.add(s); uniq.append(s)
    return uniq

seeds=seed_entries()
sys.stderr.write("seeds=%d\n"%len(seeds))
done=0
for va,mode in seeds:
    if not valid_va(va): continue
    r=disasm_func(va,mode)
    if r:
        end,m,sz=r
        funcs.append((va, va2off(va), "T" if m==CS_MODE_THUMB else "A", sz)); done+=1
sys.stderr.write("funcs=%d code_va=%d\n"%(done, len(code_va)))

with open(os.path.join(OUT,"code_va.txt"),"w") as f:
    for v in sorted(code_va): f.write("%08x\n"%v)
with open(os.path.join(OUT,"funcs.csv"),"w") as f:
    f.write("va,off,mode,size\n")
    for va,o,m,sz in sorted(funcs):
        f.write("%08x,%d,%s,%d\n"%(va,o,m,sz))
with open(os.path.join(OUT,"xrefs.csv"),"w") as f:
    f.write("src_va,kind,target_va,target_off\n")
    for s,k,t,to in xrefs:
        f.write("%08x,%s,%08x,%d\n"%(s,k,t,to))
cb=len(code_va)*2
sys.stderr.write("coverage~%.1f%% xrefs=%d floatrefs=%d strrefs=%d\n"%(
    100*cb/N, len(xrefs),
    sum(1 for _,k,_,to in xrefs if to in FLOAT),
    sum(1 for _,k,_,to in xrefs if to in STR)))
print("OK")
