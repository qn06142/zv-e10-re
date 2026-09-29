import os, re
TOOLS = r"C:\Users\Minhsnguhoa\pmca-re\tools"
for name in ("testcmd.elf", "sndcmd.elf", "rcvcmd.elf", "crypter.elf"):
    data = open(os.path.join(TOOLS, name), "rb").read()
    print("\n================ %s (%d B) ================" % (name, len(data)))
    print("ELF:", data[:4] == b"\x7fELF")
    strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
    blob = " ".join(strs)
    # command-like symbols
    cmds = sorted(set(re.findall(r"\b([A-Za-z_]*(?:cmd|Cmd|CMD|command|Command|exec|Exec|send|Send|recv|Recv|msg|Msg|test|Test|uipc|osal|adjust|Adjust|set|Set|get|Get|port|Port|sd|SD|gpio|GPIO|crypt|crypt|sign|Sign|verif|Verif|key|Key|img|Img|load|Load)[A-Za-z0-9_]*)\b", blob)))
    print("-- cmd-ish strings (%d) --" % len(cmds))
    for c in cmds[:50]:
        print("  " + c)
    # error/validation
    errs = [s for s in strs if re.search(r"(error|invalid|fail|range|overflow|too |denied|reject|param|usage|help)", s, re.I)]
    print("-- validation/error strings (%d) --" % len(errs))
    for e in errs[:25]:
        print("  " + e)
    # SDF/exec/testcmd references
    print("-- SDF/EXEC/testcmd/uipc mentions --")
    for s in sorted(set(strs)):
        if re.search(r"SDF_|CMD_ID_|ExecCmd|testcmd|uipc|osal|EXEC_|sndmsg|rcvmsg", s, re.I):
            print("  " + s)
