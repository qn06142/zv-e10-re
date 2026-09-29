import os, re
EXE = r"D:\Update_ZVE10V203.exe"
data = open(EXE, "rb").read()
strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{5,}", data)]
print("total strings:", len(strs))

# 1) companion firmware file references (the actual blob the exe uses)
print("=== companion firmware/body file references ===")
for s in sorted(set(strs)):
    if re.search(r"\.bin|\.dat|\.img|\.upd|\.fup|\.pkg|firm|body|udtr|av-cam|"
                 r"update|Update|UPDATE|payload|Payload", s, re.I):
        if re.search(r"\.(bin|dat|img|upd|fup|pkg)\b|firmware|body|udtr|av.cam|payload", s, re.I):
            print("  " + s)

# 2) URLs / download (does it fetch the blob at runtime?)
print("\n=== URLs / download endpoints ===")
for s in sorted(set(strs)):
    if re.search(r"https?://|ftp://|\.sony|download|Download|api\.|endpoint|/firm", s, re.I):
        print("  " + s)

# 3) USB / bulk transfer verbs (does it just shovel bytes to the device?)
print("\n=== USB / device-transfer verbs ===")
for s in sorted(set(strs)):
    if re.search(r"bulk|transfer|Transfer|endpoint|Endpoint|usb|USB|WriteFile|ReadFile|"
                 r"send|Send|recv|Recv|packet|Packet|pipe|Pipe|vendor|Vendor|"
                 r"0x[0-9a-fA-F]{4,}", s, re.I):
        if len(s) < 80:
            print("  " + s)

# 4) decrypt/verify verbs (proving dumb-pipe or not)
print("\n=== decrypt/verify/decode verbs ===")
for s in sorted(set(strs)):
    if re.search(r"decrypt|Decrypt|encrypt|Encrypt|verify|Verify|decode|Decode|"
                 r"signature|Signature|hash|Hash|checksum|Checksum|auth|Auth", s):
        print("  " + s)

# 5) any Sony firmware version string
print("\n=== firmware version / model strings ===")
for s in sorted(set(strs)):
    if re.search(r"ZV-E10|ver\.|version|Version|2\.0[0-9]|firmware", s, re.I) and len(s) < 60:
        print("  " + s)
