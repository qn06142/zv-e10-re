
import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
# Ghidra headless analyzer for ZV-E10 av-cam.bin (run via analyzeHeadless).
# Sets image base 0x635c6000, auto-analyzes, dumps functions/xrefs/strings to JSON.
# Usage: analyzeHeadless <project_dir> avcam -import <av-cam.bin> -postScript ghidra_headless.py -scriptPath <dir>
# Or place in Ghidra script dir and run "Analyze" then this as post-script.

BASE = 0x635c6000
OUT  = (ROOT_REPO / 'avcam_re/out/ghidra_analysis.json').as_posix()

def main():
    from ghidra.app.util.headless import HeadlessAnalyzer  # noqa (headless ctx)
    program = currentProgram
    # set image base
    try:
        base = toAddr(BASE)
        memory = program.getMemory()
        # move all blocks to new base if needed
        tx = program.startTransaction("setBase")
        try:
            program.setImageBase(base, True)
        finally:
            program.endTransaction(tx)
    except Exception as e:
        print("setBase warn:", e)

    # analysis is auto-run on import; ensure analyzers executed
    # export
    fm = program.getFunctionManager()
    funcs = []
    for f in fm.getFunctions(True):
        funcs.append({
            "name": f.getName(),
            "entry": f.getEntryPoint().getOffset(),
            "body_start": f.getBody().getMinAddress().getOffset(),
            "body_end": f.getBody().getMaxAddress().getOffset(),
            "size": f.getBody().getNumAddresses(),
        })

    # xrefs from/to
    xrefs = []
    mem = program.getMemory()
    addr_set = program.getMemory().getAddresses(True)
    refs = program.getReferenceManager()
    for f in funcs:
        a = toAddr(f["entry"])
        for r in refs.getReferencesFrom(a):
            xrefs.append({"src": a.getOffset(), "dst": r.getToAddress().getOffset(), "type": str(r.getReferenceType())})

    # strings
    strings = []
    ds = program.getDataTypeManager()
    # use defined data + string search
    strs = program.getListing().getDefinedData(False)
    while strs.hasNext():
        d = strs.next()
        if d.getDataType().getName().startswith("string") or "char" in d.getDataType().getName().lower():
            strings.append({"addr": d.getAddress().getOffset(), "value": str(d.getDefaultValueRepresentation())[:200]})

    import json
    with open(OUT, "w") as fh:
        json.dump({"base": BASE, "functions": funcs, "xrefs": xrefs, "strings": strings}, fh, indent=1)
    print("WROTE", OUT, "funcs=", len(funcs), "xrefs=", len(xrefs), "strings=", len(strings))

if __name__ == "__main__":
    main()
else:
    main()
