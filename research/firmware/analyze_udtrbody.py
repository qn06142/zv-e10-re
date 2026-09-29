import os, re

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
TOOLS = (ROOT_REPO / 'tools').as_posix()
data = open(os.path.join(TOOLS, "udtrbody.bin"), "rb").read()
print("udtrbody.bin: %d bytes (0x%x)" % (len(data), len(data)))
# header
print("first 64 bytes:", data[:64].hex())
print("ASCII head:", repr(data[:64]))
# known markers
for m in (b"0100UDTRFIRM", b"UDTRFIRM", b"libupdaterbody.so", b"bodyfs", b"libosal_utm",
          b"libupdatercommon", b"DLLEXT", b".so", b"ELF", b"\x7fELF"):
    c = data.count(m)
    if c: print("  found %r x%d @0x%x" % (m, c, data.find(m)))
# crypto / sig markers in the body
for kw in ("sign","Sign","verif","Verif","RSA","rsa","cert","Cert","x509","X509","sha","SHA","md5","MD5","crc","CRC","aes","AES","key","Key","hash","Hash","pem","PEM","auth","Auth"):
    c = data.count(kw.encode())
    if c: print("  crypto-str %r x%d" % (kw, c))
# string dump (short)
strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
print("\n=== sample strings (%d total) ===" % len(strs))
for s in strs[:40]:
    print("  "+s)
