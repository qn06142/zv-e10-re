import os, re
UP = r"C:\Users\Minhsnguhoa\pmca-re\fw_update\updater"
for fn in ("FirmwareUpdaterEg.exe","FirmwareUpdaterImg.dll"):
    data = open(os.path.join(UP, fn),"rb").read()
    print("=== %s (%d bytes) ===" % (fn, len(data)))
    strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
    # validation / signature / crypto verbs
    for s in sorted(set(strs)):
        if re.search(r"sign|Sign|SIGN|verif|Verif|VERIF|cert|Cert|CERT|crc|CRC|hash|Hash|auth|Auth|"
                     r"valid|Valid|check|Check|version|Version|firm|Firm|updat|Updat|"
                     r"FirmwareData|\.dat|body|Body|load|Load|decrypt|Decrypt|"
                     r"signature|Signature|sha|SHA|md5|MD5|aes|AES|rsa|RSA|key|Key", s):
            print("    " + s)
    print()
