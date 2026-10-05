import sys
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE / "research" / "firmware"))
from thumb import mkdis, pcrel_strrefs, walk, calls_of, is_prologue, strref_at

avcam_path = HERE / "dumps" / "av-cam.bin"
av = avcam_path.read_bytes()
md = mkdis()

print("Building PC-relative string reference map for av-cam.bin...")
refs = pcrel_strrefs(md, av, 0x1000, len(av))
print(f"Mapped {len(refs)} reference targets.")

targets = [
    ("ModuleCalcAspectImageArea", 0x0097afec),
    ("[SDF] aspect", 0x00975133),
    ("[SDF] outputImageAspect", 0x00976303),
    ("Capture Crop Type", 0x009b56ff),
    ("FULL_CROP", 0x009a6112),
    ("scanMode", 0x0094ef1a),
    ("esPictureAspect", 0x0094efb3),
]

for name, target_off in targets:
    print(f"\n=== Searching references to '{name}' (target off 0x{target_off:08x}) ===")
    site = strref_at(av, refs, target_off)
    if site is None:
        # Check range +- 16 bytes
        found = []
        for delta in range(-16, 17):
            cand = target_off + delta
            if cand in refs:
                found.extend(refs[cand])
        if found:
            print(f"  Found near references at {', '.join(f'0x{s:08x}' for s in found)}")
            site = found[0]
        else:
            print("  No references found.")
            continue
    else:
        print(f"  Direct reference at 0x{site:08x}")

    # Walk back to prologue
    fn_start = site
    for q in range(site, max(0x1000, site - 0x600), -2):
        if is_prologue(av, q):
            fn_start = q
            break
    print(f"  Function starts at 0x{fn_start:08x} (VA 0x{0x635c6000 + fn_start:08x})")
    
    # Disasm first 30 instructions of function
    body = walk(md, av, fn_start, 0x400)
    print(f"  Function has {len(body)} instructions:")
    for ins in body[:25]:
        print(f"    0x{ins.address:08x} (VA 0x{0x635c6000 + ins.address:08x}): {ins.mnemonic:8s} {ins.op_str}")
