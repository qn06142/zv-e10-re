import os, re

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
ROOT = ROOT_REPO.as_posix()
FW = os.path.join(ROOT, "fw")
# search all dumped firmware blobs for crypto/algorithm identifiers
targets = ["av-cam.bin","vmlinux.bin","initrd.img","bonobo.bin","dfe_dat.bin",
           "dfe_app.bin","ldr_drv.bin","lif_app.bin","wole_app.bin","bt_firm.hcd"]
# also kernel module we pulled
MODS = [os.path.join(ROOT,"kmod","osal_uipc.ko")]

patterns = [rb"AES", rb"aes", rb"AES128", rb"AES256", rb"AES-", rb"DES", rb"3DES",
            rb"blowfish", rb"BLOWFISH", rb"twofish", rb"TWOFISH", rb"rijndael", rb"RIJNDAEL",
            rb"camellia", rb"CAMELLIA", rb"seed", rb"SEED", rb"aria", rb"ARIA",
            rb"chacha", rb"CHACHA", rb"poly1305", rb"sha1", rb"sha256", rb"sha512",
            rb"RSA", rb"rsa", rb"ECC", rb"ecc", rb"ECDSA", rb"XTS", rb"xts",
            rb"secure.?core", rb"SECURE.?CORE", rb"tcs", rb"TCS", rb"sce", rb"SCE",
            rb"crypto", rb"CRYPTO", rb"cipher", rb"CIPHER", rb"decrypt", rb"DECRYPT",
            rb"encrypt", rb"ENCRYPT", rb"scramble", rb"SCRAMBLE", rb"obf", rb"OBF",
            rb"0xE0", rb"0xF0", rb"0xEA", rb"0xEB",  # secure-core MMIO base hints
            rb"KEY f:", rb"KEY", rb"key_schedule", rb"key_table", rb"otp", rb"OTP",
            rb"hwcrypto", rb"hw_crypto", rb"seceng", rb"SECENG", rb"spu", rb"SPU"]

def scan(name, data):
    hits = {}
    low = data.lower()
    for pat in patterns:
        c = low.count(pat.lower())
        if c:
            hits[pat.decode("latin1","replace")] = c
    # also find SecureCore / crypto driver-ish symbol strings
    strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
    sym = sorted({s for s in strs if re.search(r"crypto|secure|scramble|decrypt|cipher|key|sec|sce|tcs|spu|otp", s, re.I)})
    return hits, sym[:40]

for fn in targets:
    p = os.path.join(FW, fn)
    if not os.path.exists(p): continue
    data = open(p,"rb").read()
    hits, sym = scan(fn, data)
    if hits or sym:
        print("=== %s (%d bytes) ===" % (fn, len(data)))
        for k,v in sorted(hits.items(), key=lambda x:-x[1])[:25]:
            print("   %s: %d" % (k, v))
        if sym:
            print("   symbols:", ", ".join(sym[:20]))
        print()
for p in MODS:
    if os.path.exists(p):
        data = open(p,"rb").read()
        hits, sym = scan(os.path.basename(p), data)
        if hits or sym:
            print("=== %s (%d bytes) ===" % (os.path.basename(p), len(data)))
            for k,v in sorted(hits.items(), key=lambda x:-x[1])[:15]:
                print("   %s: %d" % (k, v))
            if sym: print("   symbols:", ", ".join(sym[:15]))
            print()
