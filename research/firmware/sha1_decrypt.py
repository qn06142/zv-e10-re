import hashlib

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]

KEY = bytes([
    0x8D,0xE5,0xA8,0x56,0xD2,0xEE,0x76,0xE0,0x6C,0x45,0xDD,0x9F,0x57,0x12,0xC6,0x3A,
    0x0A,0xDB,0x05,0xC1,0xAF,0x80,0x8F,0xC3,0x97,0x7B,0x21,0x87,0x75,0x22,0x69,0xDE,
    0x83,0xCC,0xA6,0xC6,0x12,0xF0,0xDC,0x49,
])

def sha1_stream_decrypt(data: bytes) -> bytes:
    """Mirror nex-hack fdc_sha1_cipher_bytes: continuous SHA1-XOR stream."""
    ctx = hashlib.sha1()
    ctx.update(KEY[0:20])
    ctx.update(KEY[20:40])
    out = bytearray(len(data))
    i = 0
    n = len(data)
    while n > 0:
        digest = ctx.digest()  # sha1_finish
        this = 20 if n >= 20 else n
        for j in range(this):
            out[i+j] = data[i+j] ^ digest[j]
        # reseed: sha1(digest || KEY[20:40])
        ctx = hashlib.sha1()
        ctx.update(digest)
        ctx.update(KEY[20:40])
        i += this
        n -= this
    return bytes(out)

def main():
    raw = open((ROOT_REPO / 'fdat_raw.bin').as_posix(),"rb").read()
    print("raw fdat size:", len(raw))
    dec = sha1_stream_decrypt(raw)
    print("decrypted size:", len(dec))
    print("first 16:", dec[:16].hex(), repr(dec[:16]))

    # segment into 1000-byte blocks, strip 4-byte header, take 996
    BLOCK = 1000
    nblocks = len(dec) // BLOCK
    stripped = bytearray()
    for b in range(nblocks):
        blk = dec[b*BLOCK:(b+1)*BLOCK]
        stripped += blk[4: BLOCK]   # strip 4-byte FDAT_ENC_BLOCK_HDR
    # last partial block
    rem = dec[nblocks*BLOCK:]
    if rem:
        stripped += rem[4:] if len(rem) > 4 else rem
    print("stripped size:", len(stripped))

    # check TPZL near fih_fw_offset 0x24200
    idx = stripped.find(b"TPZL")
    print("TPZL at:", hex(idx) if idx>=0 else "NOT FOUND")
    if len(stripped) > 0x24200:
        print("at 0x24200:", stripped[0x24200:0x24210].hex())
        print("at 0x24200 ascii:", repr(stripped[0x24200:0x24210]))
    # check UDTRFIRM
    print("UDTRFIRM at:", stripped.find(b"UDTRFIRM"))

    if idx >= 0:
        open((ROOT_REPO / 'fdat_dec_sha1.bin').as_posix(),"wb").write(stripped)
        print("WROTE fdat_dec_sha1.bin")

if __name__ == "__main__":
    main()
