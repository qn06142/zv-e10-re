import sys, struct, zlib
sys.path.insert(0, (ROOT_REPO / 'fwtool_ma1co_repo').as_posix())
from fwtool.sony import dat as D
from Crypto.Cipher import AES

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]

DAT = (ROOT_REPO / 'fw_update/FirmwareData_ZVE10V203.dat').as_posix()
OUT = (ROOT_REPO / 'fdat_decrypted.bin').as_posix()

df = D.readDat(open(DAT,"rb"))
fdat = df.firmwareData.read()
print("FDAT size:", len(fdat))

AES_KEY = bytes.fromhex("E3B0C44298FC1C149AFBF4C8996FB924")
BLOCK = 1024  # AES-128-ECB, 1024-byte crypto blocks

def dec_block(block):
    out = bytearray()
    for i in range(0, len(block), 16):
        out += AES.new(AES_KEY, AES.MODE_ECB).decrypt(block[i:i+16])
    return bytes(out)

nblocks = len(fdat)//BLOCK
print("full blocks:", nblocks, "remainder:", len(fdat)%BLOCK)
# Each decrypted 1024-byte AES block = 4-byte FDAT_ENC_BLOCK_HDR + 1020 bytes data.
# Strip the fixed 4-byte header per block and concatenate the 1020-byte data.
# (Per-block checksum/lenflags parsing varies by fw; fixed strip is robust.)
out = bytearray()
for b in range(nblocks):
    blk = dec_block(fdat[b*BLOCK:(b+1)*BLOCK])
    out += blk[4:BLOCK]   # 1020 bytes of data
print("decrypted plaintext size:", len(out))
open(OUT,"wb").write(out)
for needle in [b"libupdaterbody.so", b"av-cam.bin", b"udtrbody.bin", b"crypter.elf",
               b"\x7fELF", b".so", b"UDTRFIRM"]:
    idx = out.find(needle)
    if idx>=0:
        print("  found %r at offset %d" % (needle[:20], idx))
print("head:", out[:64].hex())
