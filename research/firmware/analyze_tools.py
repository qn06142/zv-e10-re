import os, re, collections
TOOLS = r"C:\Users\Minhsnguhoa\pmca-re\tools"
for name in ("bk.elf", "adjstctl.elf"):
    data = open(os.path.join(TOOLS, name), "rb").read()
    strs = [s.decode("latin1", "replace") for s in re.findall(rb"[ -~]{4,}", data)]
    blob = " ".join(strs)
    print("\n================ %s (%d B, %d strings) ================" % (name, len(data), len(strs)))
    # ELF?
    print("ELF magic:", data[:4] == b"\x7fELF")
    # command-looking strings: anything with cmd/cmd_/set_/get_/exec/run/sdf
    cmds = sorted(set(re.findall(r"\b([A-Za-z_]*?(?:cmd|Cmd|CMD|set|Set|get|Get|exec|Exec|run|Run|sdf|SDF|mode|Mode)[A-Za-z0-9_]*)\b", blob)))
    print("\n-- command-ish symbols (%d) --" % len(cmds))
    for c in cmds[:60]:
        print("  " + c)
    # error/validation strings (hint at input parsing)
    errs = [s for s in strs if re.search(r"(error|invalid|fail|range|overflow|too (big|small|long)|denied|reject|param)", s, re.I)]
    print("\n-- validation/error strings (%d) --" % len(errs))
    for e in errs[:40]:
        print("  " + e)
    # SDF / exec presence
    print("\n-- SDF/Exec mentions --")
    for s in sorted(set(strs)):
        if re.search(r"SDF_|CMD_ID_|ExecCmd|uipc|LIRO|liro", s):
            print("  " + s)
