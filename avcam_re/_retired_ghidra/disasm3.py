#!/usr/bin/env python3
"""Recursive-descent disassembler for ZV-E10 av-cam.bin (Thumb, base 0x635c6000).

CLEAN worklist descent:
  seed = vector table (@12, real ARM absolute ptrs) + reset stub ONLY.
  follow bl/blx/branch targets (true recursive descent -> reachable firmware).
  pointer tables are DISCOVERED (entries landing in code_va), not seeded.
  record LDR-PC/ADR data xrefs + call edges. Bounded by caps.
"""
import struct, math, re, os, sys
import capstone
from capstone import CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB, CS_OP_MEM, CS_OP_IMM
from capstone.arm import ARM_REG_PC, ARM_REG_LR, ARM_REG_SP

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]

BASE = 0x635c6000
SRC  = (ROOT_REPO / 'dumps/av-cam.bin').as_posix()
OUT  = (ROOT_REPO / 'avcam_re/out').as_posix()
os.makedirs(OUT, exist_ok=True)
d = open(SRC,"rb").read(); N=len(d)
def off2va(o): return BASE+o
def va2off(v): return v-BASE
def valid(v): o=v-BASE; return 0<=o<N
def rd32(o): return struct.unpack_from("<I",d,o)[0] if 0<=o<=N-4 else None

def isf32(x): return math.isfinite(x) and abs(x)<1e6 and abs(x)>=1e-12
FLOAT={}; i=0
while i+4<=N:
    c=0;s=i
    while i+4<=N:
        x=struct.unpack_from("<f",d,i)[0]
        if isf32(x): c+=1;i+=4
        else: break
    if c>=16: FLOAT[s]=c
    else: i+=4
STR={}
for m in re.finditer(rb'[ -~]{5,}', d): STR[m.start()]=m.group().decode('latin1','replace')

md_arm=capstone.Cs(CS_ARCH_ARM,CS_MODE_ARM); md_arm.detail=True
md_thb=capstone.Cs(CS_ARCH_ARM,CS_MODE_THUMB); md_thb.detail=True

visited=set(); code_va=set(); funcs=[]; xrefs=[]; calls=[]
MAXFN=40000; TOTALFUNC=200000; TOTALCAP=4_000_000

def thumb_pcrel(ins):
    pc=(ins.address&~3)+4
    for op in ins.operands:
        if op.type==CS_OP_MEM and op.mem.base==ARM_REG_PC: return pc+op.mem.disp
    return None
def arm_pcrel(ins):
    pc=(ins.address+8)&~3
    for op in ins.operands:
        if op.type==CS_OP_MEM and op.mem.base==ARM_REG_PC: return pc+op.mem.disp
    return None

def disasm_one(va, mode):
    md = md_thb if mode==CS_MODE_THUMB else md_arm
    cur=va; count=0
    while True:
        if cur in code_va: break
        o=va2off(cur)
        if not (0<=o<=N-2): break
        res=list(md.disasm(d[o:o+4],cur,count=1)) or list(md.disasm(d[o:o+2],cur,count=1))
        if not res: break
        ins=res[0]
        if (ins.address,mode) in visited: break
        visited.add((ins.address,mode)); code_va.add(ins.address)
        mnem=ins.mnemonic
        tgt=thumb_pcrel(ins) if mode==CS_MODE_THUMB else arm_pcrel(ins)
        if tgt is not None and valid(tgt):
            to=va2off(tgt)
            kind="ldr" if mnem.startswith("ldr") or mnem.startswith("adr") else "mem"
            xrefs.append((ins.address,kind,tgt,to))
        is_call=mnem.startswith("bl")
        is_branch=mnem.startswith("b") or mnem in ("bx","blx","bxj")
        term=False
        if mnem in ("bx","bxj","blx"):
            for op in ins.operands:
                if op.type==CS_OP_IMM: calls.append((ins.address,op.imm)); term=True
                elif op.type==capstone.CS_OP_REG: term=True
        elif is_call:
            for op in ins.operands:
                if op.type==CS_OP_IMM:
                    calls.append((ins.address,op.imm))
                    xrefs.append((ins.address,"call",op.imm,va2off(op.imm) if valid(op.imm) else -1))
        if mnem=="pop":
            for op in ins.operands:
                if op.type==capstone.CS_OP_REG and op.reg==ARM_REG_PC: term=True
        if is_branch and not is_call:
            for op in ins.operands:
                if op.type==CS_OP_IMM:
                    xrefs.append((ins.address,"branch",op.imm,va2off(op.imm) if valid(op.imm) else -1))
                    if op.imm>cur: term=True
        cur=ins.address+ins.size
        count+=1
        if count>MAXFN or len(code_va)>TOTALCAP: break
    return cur, cur-va

def main():
    seeds=[]
    for o in range(12,0x400,4):
        v=rd32(o)
        if v is None: break
        if BASE<=v<BASE+N:
            mode=CS_MODE_THUMB if (v&1) else CS_MODE_ARM
            seeds.append((v&~1,mode))
    seeds.append((BASE+0x28,CS_MODE_ARM))
    seen=set(); work=[]
    for s in seeds:
        if s not in seen: seen.add(s); work.append(s)
    sys.stderr.write("initial seeds=%d\n"%len(work))

    while work:
        va,mode=work.pop()
        if (va,mode) in visited or not valid(va): continue
        end,sz=disasm_one(va,mode)
        funcs.append((va,va2off(va),"T" if mode==CS_MODE_THUMB else "A",sz))
        for s,tgt in calls:
            if valid(tgt):
                m=CS_MODE_THUMB if (tgt&1) else CS_MODE_ARM
                if (tgt&~1,m) not in seen:
                    seen.add((tgt&~1,m)); work.append((tgt&~1,m))
        if len(funcs)>TOTALFUNC: break

    # discover pointer tables: runs of consecutive in-range ptrs where >=60% point to code_va
    code_set=code_va
    ptr_tables=[]
    run=[]
    for o in range(0,N-3,4):
        v=rd32(o)
        if v is not None and BASE<=v<BASE+N and (v&~1) in code_set: run.append(o)
        else:
            if len(run)>=4:
                ok=sum(1 for ro in run if (rd32(ro)&~1) in code_set)
                if ok>=0.6*len(run): ptr_tables.append((run[0],len(run)))
            run=[]
    if len(run)>=4:
        ok=sum(1 for ro in run if (rd32(ro)&~1) in code_set)
        if ok>=0.6*len(run): ptr_tables.append((run[0],len(run)))

    with open(os.path.join(OUT,"code_va.txt"),"w") as f:
        for v in sorted(code_va): f.write("%08x\n"%v)
    with open(os.path.join(OUT,"funcs.csv"),"w") as f:
        f.write("va,off,mode,size\n")
        for va,o,m,sz in sorted(funcs): f.write("%08x,%d,%s,%d\n"%(va,o,m,sz))
    with open(os.path.join(OUT,"xrefs.csv"),"w") as f:
        f.write("src_va,kind,target_va,target_off\n")
        for s,k,t,to in xrefs: f.write("%08x,%s,%08x,%d\n"%(s,k,t,to))
    with open(os.path.join(OUT,"calls.csv"),"w") as f:
        f.write("src_va,target_va\n")
        for s,t in calls: f.write("%08x,%08x\n"%(s,t))
    with open(os.path.join(OUT,"ptr_tables.txt"),"w") as f:
        for so,cnt in ptr_tables: f.write("0x%06x %d\n"%(so,cnt))
    cb=len(code_va)*2
    sys.stderr.write("funcs=%d code_va=%d coverage=%.1f%% xrefs=%d calls=%d floatrefs=%d strrefs=%d ptr_tables=%d\n"%(
        len(funcs),len(code_va),100*cb/N,len(xrefs),len(calls),
        sum(1 for _,k,_,to in xrefs if to in FLOAT),
        sum(1 for _,k,_,to in xrefs if to in STR),
        len(ptr_tables)))
    print("OK")

if __name__=="__main__":
    main()
