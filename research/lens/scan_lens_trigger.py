import os, re
ROOT = r"C:\Users\Minhsnguhoa\pmca-re\fw"
data = open(os.path.join(ROOT, "av-cam.bin"), "rb").read()
strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
uniq = sorted(set(strs))

# LensFirmUpdate trigger: what command/endpoint drives it?
print("=== strings mentioning LensFirm / FirmUp / LUPDT / CAIF / LIF ===")
for s in uniq:
    if re.search(r"LensFirm|FirmUp|LUPDT|CAIF|LIF|lens.*updat|updat.*lens", s, re.I):
        if not s.startswith("/lens/VX") and "CAIF Recieve" not in s and "CAIF Send" not in s:
            print("  " + s)

# any osal_id constant near lens update? search all 0x.... literals
print("\n=== hex literals that look like osal_ids (0x00xx0000 / 0xdc / 0xXXXX) ===")
seen=set()
for m in re.finditer(rb"0x[0-9a-fA-F]{6,8}", data):
    t = m.group().decode()
    if t.lower() in seen: continue
    seen.add(t.lower())
    print("  " + t)

# 'LensFirmUpdate' symbol context: is it a function? what calls it?
print("\n=== any 'Req'/'Send'/'Recv' near lens firmware ===")
for s in uniq:
    if re.search(r"FirmUpReq|FirmUpRes|LensFirmUpdate|LensFw|lens_fw|lensfw", s):
        print("  " + s)
