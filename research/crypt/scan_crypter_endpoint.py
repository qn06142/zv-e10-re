import os, re
TOOLS = r"C:\Users\Minhsnguhoa\pmca-re\tools"
data = open(os.path.join(TOOLS, "crypter.elf"), "rb").read()
print("crypter.elf %d bytes" % len(data))
# any osal_id-like hex constants
print("=== hex literals ===")
for m in re.finditer(rb"0x[0-9a-fA-F]{4,8}", data):
    print("  ", m.group().decode())
# delivery / endpoint / sdf / uipc-relevant strings
strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
print("\n=== endpoint/sdf/uipc strings ===")
for s in sorted(set(strs)):
    if re.search(r"osal|OSAL|uipc|UIPC|sdf|SDF|endpoint|Endpoint|send|Send|recv|Recv|"
                 r"msg|Msg|body|Body|firm|Firm|updat|Updat|target|Target|dest|Dest|"
                 r"0x|sid|SID", s):
        print("  "+s)
