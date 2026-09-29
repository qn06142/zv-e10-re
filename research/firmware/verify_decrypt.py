import sys, struct
sys.path.insert(0, r"C:\Users\Minhsnguhoa\pmca-re\fwtool_ma1co_repo")
from fwtool.sony import dat as D
from Crypto.Cipher import AES

DAT = r"C:\Users\Minhsnguhoa\pmca-re\fw_update\FirmwareData_ZVE10V203.dat"
df = D.readDat(open(DAT,"rb"))
fdat = df.firmwareData.read()
print("FDAT chunk size:", len(fdat))

MAGIC = b"UDTRFIRM"

# AES-128-ECB static key (SHA1("")[:16])
AES_KEY = bytes.fromhex("E3B0C44298FC1C149AFBF4C8996FB924")
print("AES key:", AES_KEY.hex())

def try_aes(block):
    # 1024-byte encrypted block -> AES-ECB 16-byte sub-blocks
    out = bytearray()
    for i in range(0, len(block), 16):
        out += AES.new(AES_KEY, AES.MODE_ECB).decrypt(block[i:i+16])
    return bytes(out)

def try_aes_variants(data):
    # try both block sizes; AES blocklen=1024
    for blen in (1024,):
        if len(data) < blen: continue
        blk0 = try_aes(data[:blen])
        # decrypted block0: FDAT_ENC_BLOCK_HDR(4) + data; magic at +4 (header) + 0
        # nex-hack: magic at offset sizeof(FDAT_ENC_BLOCK_HDR)=4, FDAT_IMAGE_MAGIC_OFS=0
        print("  AES blk0[4:14] =", blk0[4:14])
        if MAGIC in blk0:
            print("  *** AES method MATCHES (magic found)")
            return True, blk0
    return False, None

print("=== Try AES-128-ECB on FDAT ===")
ok, blk = try_aes_variants(fdat)
if not ok:
    print("  no AES match on first block; trying first 4096 bytes scan")
    # maybe the FDAT record has a different leading header before crypto blocks
    for off in range(0, min(1024, len(fdat)-1024), 16):
        b = try_aes(fdat[off:off+1024])
        if MAGIC in b:
            print("  *** AES MATCH at offset", off); break
    else:
        print("  no AES magic at any 16-aligned offset in first 1KB")
