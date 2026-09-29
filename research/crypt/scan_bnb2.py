import os, re
ROOT = r"C:\Users\Minhsnguhoa\pmca-re\fw"
data = open(os.path.join(ROOT, "av-cam.bin"), "rb").read()
strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
uniq = sorted(set(strs))

print("=== BNB / FILE_BNB context strings ===")
for s in uniq:
    if "BNB" in s or "BnB" in s or "FILE_BNB" in s:
        print("  " + s)

# byte context around first BNB_ occurrence
m = re.search(rb"BNB_", data)
if m:
    off = m.start()
    print("\n=== 256B around first BNB_ (0x%X) ===" % off)
    print(data[max(0,off-128):off+128].decode("latin1","replace"))

# functions mentioning Body / BnB / Load / Read / Update
print("\n=== Body/Load/Update-ish function/symbol names ===")
for s in uniq:
    if re.search(r"Body|BnB|LoadBody|ReadBody|bnblib|BnbLib|UpdateBody|FirmUp|"
                 r"LoadFirm|RecoverFirm|SelfFlash|BootUpdate|SDUpdate|CardUpdate", s):
        print("  " + s)

# the update-trigger command: search for "start" + update, or SDF update exec
print("\n=== update-start / trigger candidates ===")
for s in uniq:
    if re.search(r"start[_]?update|update[_]?start|begin[_]?update|do[_]?update|"
                 r"update[_]?mode|enter[_]?update|force[_]?update|update[_]?now|"
                 r"firm[_]?up|body[_]?load|load[_]?body", s, re.I):
        print("  " + s)
