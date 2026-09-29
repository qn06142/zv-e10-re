import os, re
EXE = r"D:\Update_ZVE10V203.exe"
print("size:", os.path.getsize(EXE))

# stream-scan (376MB) for firmware/key markers in one pass
markers = {
    "udtrbody magic 453dcd28": b"\x45\x3d\xcd\x28",
    "av-cam LIRO header 0a0000ea": b"\x0a\x00\x00\xea",
    "body magic 0100UDTRFIRM": b"0100UDTRFIRM",
    "libupdaterbody.so": b"libupdaterbody",
    "udtrbody.bin": b"udtrbody",
    "tmp_updater": b"tmp_updater",
    "Dec_ScrambleInit": b"Dec_ScrambleInit",
    "CrcChecker": b"CrcChecker",
    "DllHandler": b"DllHandler",
    "libosal_utm": b"libosal_utm",
    "libupdatercommon": b"libupdatercommon",
    # crypto lib indicators in a Windows exe
    "CRYPTO/openssl import": b"libeay32" + b"ssleay32" + b"libssl" + b"CRYPTO" + b"openssl",
    "PEM/GetLastError cert": b".pem" + b"X509" + b"CERT" + b"signature",
    # embedded PE/ELF/zip (payload containers)
    "embedded PE (MZ)": b"MZ",
    "embedded ELF": b"\x7fELF",
    "embedded ZIP": b"PK\x03\x04",
}
hits = {k: 0 for k in markers}
# also collect interesting crypto-ish strings near 'RSA'/'cert'/'verify'
samples = []
with open(EXE, "rb") as f:
    data = f.read()  # 376MB, fine on this host
for k, m in markers.items():
    if k == "CRYPTO/openssl import":
        # logical-OR group: report if ANY present
        present = any(s in data for s in [b"libeay32", b"ssleay32", b"libssl", b"CRYPTO_", b"openssl"])
        hits[k] = 1 if present else 0
    elif k == "PEM/GetLastError cert":
        present = any(s in data for s in [b".pem", b"X509", b"CERT", b"signature"])
        hits[k] = 1 if present else 0
    else:
        hits[k] = data.count(m)

print("\n=== marker counts in PC updater exe ===")
for k, v in hits.items():
    print(f"  {k}: {v}")

# What does the exe DO with firmware? Look for parse/decrypt/verify verbs near firmware strings
print("\n=== firmware-related verb strings in exe ===")
strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{5,}", data)]
fw_verbs = set()
for s in strs:
    if re.search(r"firm|Firm|FIRM|updat|Updat|UPDAT|body|Body|decrypt|Decrypt|encrypt|Encrypt|"
                 r"verify|Verify|VERIFY|sign|Sign|SIGN|checksum|Checksum|hash|Hash|"
                 r"load|Load|write|Write|send|Send|usb|USB|device|Device", s):
        if re.search(r"decrypt|encrypt|verify|sign|checksum|hash|load|write|send|parse|check|"
                     r"firm|updat|body|recv|receive", s, re.I):
            fw_verbs.add(s)
for s in sorted(fw_verbs)[:60]:
    print("  " + s)

# Does it embed a known firmware blob header?
print("\n=== does exe embed an encrypted firmware blob? ===")
print("  453dcd28 (udtrbody Compressed-ROMFS):", hits["udtrbody magic 453dcd28"])
print("  0a0000ea (av-cam LIRO):", hits["av-cam LIRO header 0a0000ea"])
print("  0100UDTRFIRM:", hits["body magic 0100UDTRFIRM"])
