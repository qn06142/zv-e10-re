import struct, zlib, io, tarfile

d = open(r"C:\Users\Minhsnguhoa\pmca-re\fdat_decrypted.bin","rb").read()
print("image size:", len(d))

# 1) broad scan for tar magic / ELF / ISP-ish strings anywhere
def findall(needle, limit=5):
    out=[]
    s=0
    while True:
        i=d.find(needle, s)
        if i<0: break
        out.append(i)
        s=i+1
        if len(out)>=limit: break
    return out

for n in [b"ustar", b"\x7fELF", b"av-cam.bin", b"libupdaterbody.so", b".tar", b"tuning", b"NR", b"Shading", b"Matrix", b"Gamma", b"Demosaic", b"ISP", b"color", b"lens", b"calib"]:
    hits=findall(n, 3)
    if hits: print("  %-14s -> %s" % (n[:14], hits))

# 2) test fw region compression
h = d
def u32(o): return struct.unpack_from("<I", h, o)[0]
fw_off = u32(0x30); fw_len = u32(0x34)
fw = d[fw_off:fw_off+fw_len]
print("\nfw region @%#x len %#x head %s" % (fw_off, fw_len, fw[:16].hex()))

# try raw zlib
try:
    dec = zlib.decompress(fw, -15)
    print("RAW ZLIB ->", len(dec), "head", dec[:16].hex(), "ustar?", b"ustar" in dec[:512])
except Exception as e:
    print("raw zlib fail:", e)
# try zlib with header
try:
    dec = zlib.decompress(fw)
    print("ZLIB ->", len(dec), "head", dec[:16].hex())
except Exception as e:
    print("zlib fail:", e)
# try lz77-ish: nex-hack lz77_inflate — no std lib; skip
# try treating fw as a nested FDAT (recursive decrypt): AES-ECB static key again
from Crypto.Cipher import AES
KEY=bytes.fromhex("E3B0C44298FC1C149AFBF4C8996FB924")
def dec_aes(b):
    o=bytearray()
    for i in range(0,len(b),16): o+=AES.new(KEY,AES.MODE_ECB).decrypt(b[i:i+16])
    return bytes(o)
fw2=dec_aes(fw[:1024])
print("AES-on-fw head:", fw2[:16].hex(), "ustar?", b"ustar" in fw2)
# scan whole fw for ustar after AES
fwA=dec_aes(fw)
i=fwA.find(b"ustar")
print("AES-on-fw ustar at:", i)
