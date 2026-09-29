import os, re
TOOLS = r"C:\Users\Minhsnguhoa\pmca-re\tools"
for fn in ("sndcmd.elf","testcmd.elf","rcvcmd.elf"):
    data = open(os.path.join(TOOLS, fn), "rb").read()
    print("=== %s (%d bytes) ===" % (fn, len(data)))
    # all hex literals (possible osal_ids)
    lits = sorted(set(m.group().decode() for m in re.finditer(rb"0x[0-9a-fA-F]{4,8}", data)))
    print("  hex literals:", lits[:40])
    # interesting strings
    strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
    for s in sorted(set(strs)):
        if re.search(r"osal|OSAL|uipc|UIPC|sdf|SDF|firm|Firm|updat|Updat|body|Body|"
                     r"0x|sid|SID|endpoint|Endpoint|target|Target|dest|Dest|cmd|CMD|"
                     r"sync|Sync|testcmd|TestCmd|exec|Exec|load|Load", s):
            print("    " + s)
    print()
