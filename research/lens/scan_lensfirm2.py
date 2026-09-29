import os, re

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
ROOT = (ROOT_REPO / 'fw').as_posix()
data = open(os.path.join(ROOT, "av-cam.bin"), "rb").read()
strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
uniq = sorted(set(strs))

# lens-update related strings only
lf = [s for s in uniq if re.search(r"LensFirm|FirmUp|LUPDT|lensfile|LensFile|CAIF|Caif", s)]
blob = "\n".join(lf)
print("lens/CAIF-related strings:", len(lf))
for s in lf:
    if re.search(r"sign|Sign|SIGN|verif|Verif|VERIF|cert|Cert|CERT|crc|Crc|CRC|rsa|Rsa|RSA|"
                 r"aes|Aes|AES|hash|Hash|auth|Auth|KEY|key|md5|sha|Sha|SHA|check|Check|"
                 r"valid|Valid|illegal|Illegal|error|Error|busy|Busy|param|Param", s):
        print("  " + s)

print("\n=== auth keyword presence in lens-update context ===")
for kw in ["sign","verify","cert","crc","rsa","aes","hash","auth","key","md5","sha"]:
    hit = kw in blob
    print(f"  {kw}: {'YES' if hit else 'no'}")
