import os, re
ROOT = r"C:\Users\Minhsnguhoa\pmca-re\fw"
data = open(os.path.join(ROOT, "av-cam.bin"), "rb").read()
print("av-cam.bin: %d bytes" % len(data))
# update / firmware / body / SDF-ish strings
kw = re.compile(r"updat|Updat|UPDAT|firm|Firm|FIRM|body|Body|BODY|udtr|Udtr|UDTR|"
                r"SDF_|sdf_|CryptFile|cryptfile|libupdaterbody|startupdate|endupdate|"
                r"dlopen|DllHandler|0x00dc|osal", re.I)
strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
hits = sorted(set(s for s in strs if kw.search(s)))
print("=== update/firmware/SDF-related strings in av-cam.bin (%d) ===" % len(hits))
for h in hits[:80]:
    print("  "+h)
# osal_id style hex near updater
print("\n=== osal_id-like tokens (0x00dc / 0xdc00) ===")
for m in re.finditer(rb"0x[0-9a-fA-F]{6,8}", data):
    t = m.group().decode()
    if "dc" in t.lower():
        print("  ", t)
