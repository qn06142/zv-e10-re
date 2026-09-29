import os, re

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
ROOT = (ROOT_REPO / 'fw').as_posix()
data = open(os.path.join(ROOT, "av-cam.bin"), "rb").read()
strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
uniq = sorted(set(strs))

print("=== LensFirmUpdate / LIF firmware flow strings ===")
for s in uniq:
    if re.search(r"LensFirm|Lens.*Firm|FirmUp|LUPDT|CAIF|lensfile|LensFile|"
                 r"lens.*updat|updat.*lens|E-mount|emount|EMOUNT", s, re.I):
        print("  " + s)

# Does the lens update path reference signature/verify/crc/auth?
print("\n=== lens-update crypto/auth strings ===")
lf = [s for s in uniq if re.search(r"LensFirm|FirmUp|LUPDT|lensfile", s, re.I)]
blob = "\n".join(lf)
for kw in ["sign","Sign","SIGN","verify","Verify","VERIFY","cert","Cert","CERT",
           "crc","Crc","CRC","rsa","Rsa","RSA","aes","Aes","AES","hash","Hash",
           "auth","Auth","key","Key","KEY","md5","sha","Sha","SHA"]:
    if kw in blob:
        print("  FOUND auth kw in lens-update context:", kw)
print("  (if nothing above, lens-update has no signature/verify string either)")

# what reads lensfile.bin? any 'read'/'load' near lensfile
print("\n=== any 'load'/'read'/'parse' near lensfile ===")
for s in uniq:
    if "lensfile" in s.lower() and re.search(r"load|read|parse|open|check|verify|sign", s, re.I):
        print("  " + s)
