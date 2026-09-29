import os, re
ROOT = r"C:\Users\Minhsnguhoa\pmca-re\fw"
data = open(os.path.join(ROOT, "av-cam.bin"), "rb").read()
txt = data.decode("latin1", "replace")
strs = [s for s in (x.decode("latin1","replace") for x in re.findall(rb"[ -~]{4,}", data))]

# update / firmware / body / crypter / startupdate trigger strings
pat = re.compile(r"updat|Updat|UPDAT|firm|Firm|FIRM|body|Body|BODY|udtr|Udtr|UDTR|"
                 r"crypt|Crypt|CRYPT|startupdate|endupdate|loader_writer|bk|"
                 r"libupdaterbody|dlopen|DllHandler|firmup|firm_up|FirmUp|"
                 r"recover|Recover|RECOVER|0x00dc|0xdc00|osal", re.I)
hits = sorted(set(s for s in strs if pat.search(s)))
print("=== update/firmware/body-related strings in av-cam.bin (%d) ===" % len(hits))
for h in hits[:90]:
    print("  "+h)

# exact osal_id literals
print("\n=== hex osal_id literals (0x..dc..) ===")
for m in re.finditer(rb"0x[0-9a-fA-F]{4,8}", data):
    t = m.group().decode()
    if "dc" in t.lower() or "DC" in t:
        print("  ", t, "off=0x%x" % m.start())
