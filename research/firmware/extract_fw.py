import struct, tarfile, io, gzip, zlib

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]

d = open((ROOT_REPO / 'fdat_decrypted.bin').as_posix(),"rb").read()
assert d[0:8]==b"UDTRFIRM", d[0:16]
# FDAT_IMAGE_HEADER starts at offset 0 now (4-byte header stripped per block)
h = d
def u32(o): return struct.unpack_from("<I", h, o)[0]
print("image_version:", h[0xc:0x10])
print("fw_mode_type:", h[0x10:0x14])
print("luw_flag:", h[0x14:0x18])
print("model: %#x" % u32(0x24))
print("version_minor/major:", h[0x20], h[0x21])
fw_off = u32(0x30); fw_len = u32(0x34)
fs_count = u32(0x38)
print("fw_offset=%#x fw_len=%#x fs_count=%d" % (fw_off, fw_len, fs_count))
# list fs image descs
print("--- fs images (at +0x40, 0x10 each) ---")
for i in range(fs_count):
    o = 0x40 + i*0x10
    ident = h[o]; off=u32(o+4); ln=u32(o+8); unk=u32(o+0xc)
    print("  [%d] ident=%#04x off=%#x len=%#x unk=%#x" % (i, ident, off, ln, unk))

# Extract the firmware .tar region
fw = d[fw_off : fw_off+fw_len]
print("fw blob head:", fw[:16].hex(), "is gzip?", fw[:2]==b"\x1f\x8b")
# try gzip
try:
    gz = gzip.decompress(fw)
    print("gzip decompressed ->", len(gz), "head", gz[:16].hex())
    fw = gz
except Exception as e:
    print("not gzip:", e)
# try as tar
try:
    tf = tarfile.open(fileobj=io.BytesIO(fw))
    names = tf.getnames()
    print("TAR entries:", len(names))
    for n in names[:40]:
        print("   ", n)
    # find so/elf
    hits=[n for n in names if 'libupdaterbody' in n or 'crypter' in n or n.endswith('.so') or 'av-cam' in n]
    print("TARGET HITS:", hits)
    if hits:
        m=tf.extractfile(hits[0]); data=m.read()
        print("first target %s size=%d head=%s" % (hits[0], len(data), data[:16].hex()))
except Exception as e:
    print("tar open failed:", e)
    # maybe lz77; just show what's there
    print("fw blob sample:", fw[:64].hex())
