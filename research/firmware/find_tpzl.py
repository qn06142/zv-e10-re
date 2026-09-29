import struct, sys
from Crypto.Cipher import AES

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]

RAW = (ROOT_REPO / 'fdat_raw.bin').as_posix()
KEY = bytes.fromhex("E3B0C44298FC1C149AFBF4C8996FB924")
TARGET = b"TPZL"
FW_OFF = 0x24200  # from header

# read first 400KB of raw encrypted FDAT (covers blocks up to ~144 for 1024-byte blocks)
raw = open(RAW, "rb").read()
print("raw fdat size:", len(raw))

# try different strip amounts per 1024-byte block
for strip in [0, 2, 4, 8, 12, 16, 20, 32, 48, 64]:
    block = 1024
    data_per_block = block - strip
    n_blocks = min(len(raw) // block, 400)  # first 400 blocks ~400KB
    out = bytearray()
    for i in range(n_blocks):
        enc = raw[i*block:(i+1)*block]
        dec = AES.new(KEY, AES.MODE_ECB).decrypt(enc)
        out += dec[strip:strip+data_per_block]
    # check for TPZL near FW_OFF in this output
    idx = out.find(TARGET)
    if idx >= 0:
        print("STRIP=%d -> TPZL at offset %d (0x%x) in output (fw_off=0x%x)" % (strip, idx, idx, FW_OFF))
        # also check if TPZL is within 0x1000 of FW_OFF
        if abs(idx - FW_OFF) < 0x1000:
            print("  *** MATCH: TPZL is near fih_fw_offset! strip=%d is correct" % strip)
    # also print first 16 bytes of output for small strips
    if strip <= 8:
        print("  strip=%d first 32 bytes: %s" % (strip, out[:32].hex()))

# also: search for 0xF0 (LZ77_COMPRESSED tag) near FW_OFF in each variant
print("\n--- searching for 0xF0 near FW_OFF ---")
for strip in [0, 4, 8, 16]:
    block = 1024
    data_per_block = block - strip
    n_blocks = min(len(raw) // block, 400)
    out = bytearray()
    for i in range(n_blocks):
        enc = raw[i*block:(i+1)*block]
        dec = AES.new(KEY, AES.MODE_ECB).decrypt(enc)
        out += dec[strip:strip+data_per_block]
    # find 0xF0 bytes near FW_OFF
    region = out[max(0,FW_OFF-0x100):FW_OFF+0x100]
    f0_positions = [i for i, b in enumerate(region) if b == 0xF0]
    if f0_positions:
        print("  strip=%d: 0xF0 at offsets %s (relative to start of region at 0x%x)" % (strip, f0_positions, FW_OFF-0x100))
