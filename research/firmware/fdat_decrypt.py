#!/usr/bin/env python3
"""Decrypt a Sony FDAT (UDTRFIRM) firmware container and unpack its payload.

WHY THIS EXISTS
---------------
Earlier attempts in this repo failed to decrypt the update package, and
`dumps/fdat_decrypted.bin` was a *misleading artefact*: its first block decoded to
a valid-looking `UDTRFIRM` header, but the CramFS magic was absent at offset
0x200 and every 1 MB block measured 37.1% printable -- i.e. random.  Only block 0
had come out right.  Anything concluded from that file was worthless.

The real answer was a wrong crypter *generation*, not a wrong key hunt:

  * the cipher is a 1024-byte blocked scheme, not the 1000-byte SHA-1 stream that
    `research/firmware/sha1_decrypt.py` implements, so the keystream diverged
    immediately after the first block;
  * the generation that applies to this model is `AesCbcCrypter` (CXD90045).

The tell was cheap and worth recording: run every candidate crypter over the first
block and pick the one that yields `UDTRFIRM`.  Only CXD90045 does.  A valid header
on its own proves nothing -- block 0 always looks right under the wrong scheme.

ALGORITHM (AesCbcCrypter, reimplemented here so it is auditable)
---------------------------------------------------------------
  * the ciphertext proper is the file minus a 0x110-byte trailer;
  * the 16-byte IV is the FIRST 0x10 bytes of that trailer, not its last -- the
    reference implementation seeks to -0x110 and then reads 0x10, so the IV sits
    at [-0x110:-0x100];
  * the image is cut into 1024-byte blocks;
  * block 0 is special: its low half is AES-128-**ECB** (key_aes) and its high
    half is AES-128-**CBC** (key_cxd90045) seeded with the IV;
  * every later block is AES-128-CBC continuing that chain;
  * each decrypted block is then unpacked: u16 checksum, u16 size|endflag, a
    payload of `size & 0x7fff` bytes, and the low 16 bits of the sum of the
    u16s of `block[2:]` must equal the checksum.

The checksum and end-flag checks are what make truncation or a wrong key fail
loudly instead of yielding plausible garbage.

USAGE
-----
    python fdat_decrypt.py <fdat.dat> [--out DIR] [--payload]
        decrypt and report the header
        --payload  also extract the firmware tar to DIR/fdat_payload.bin
"""
from __future__ import annotations

import argparse
import struct
import sys
import tarfile
from pathlib import Path

try:
    from Cryptodome.Cipher import AES
except ImportError:  # pragma: no cover - environment dependent
    try:
        from Crypto.Cipher import AES
    except ImportError:
        sys.exit("need pycryptodome:  pip install pycryptodome")

# AES-128-ECB key for the first half of block 0.  This is the first 16 bytes of
# SHA-256("") -- a fixed constant, not a per-device secret.
KEY_AES = bytes.fromhex("E3B0C44298FC1C149AFBF4C8996FB924")
# AES-128-CBC key for the rest of the stream.
KEY_CXD90045 = bytes.fromhex(
    "C1AA8F7C46341FFED15589FC8170A6BB5925E85F6282D7F95BA3FDF5D303E06B"
)

BLOCK = 1024
TRAILER = 0x110
IV_LEN = 0x10
FDAT_MAGIC = b"UDTRFIRM"
FDAT_VERSION = b"0100"
HDR_SIZE = 0x208
MAX_FS = 28


class FdatError(Exception):
    """Raised for any structural or checksum failure -- never silently ignored."""


def _sum16(data: bytes) -> int:
    """Sum of the little-endian u16s of `data`, masked to 16 bits."""
    n = len(data) & ~1
    return sum(struct.unpack_from(f"<{n // 2}H", data)) & 0xFFFF


def _unpack_block(data: bytes, expect_end: bool) -> bytes:
    """Validate and strip one decrypted 1024-byte block."""
    if len(data) != BLOCK:
        raise FdatError(f"short block: {len(data)} != {BLOCK}")
    checksum, size_and_end = struct.unpack_from("<HH", data)
    size = size_and_end & 0x7FFF
    end = bool(size_and_end & 0x8000)
    if _sum16(data[2:]) != checksum:
        raise FdatError(
            f"checksum mismatch: header says 0x{checksum:04x}, "
            f"computed 0x{_sum16(data[2:]):04x}"
        )
    if end != expect_end:
        raise FdatError(f"end flag {end} but expected {expect_end}")
    return data[4:4 + size]


def _decrypt_blocks(body: bytes, iv: bytes):
    """Yield the unpacked plaintext of each 1024-byte block."""
    if len(body) % BLOCK:
        raise FdatError(
            f"ciphertext {len(body)} is not a multiple of {BLOCK}"
        )
    nblocks = len(body) // BLOCK
    ecb = AES.new(KEY_AES, AES.MODE_ECB)
    cbc = AES.new(KEY_CXD90045, AES.MODE_CBC, iv)
    for i in range(nblocks):
        blk = body[i * BLOCK:(i + 1) * BLOCK]
        if i == 0:
            plain = ecb.decrypt(blk[:512]) + cbc.decrypt(blk[512:])
        else:
            plain = cbc.decrypt(blk)
        yield _unpack_block(plain, expect_end=(i == nblocks - 1))


def decrypt(raw: bytes) -> bytes:
    """Decrypt a whole FDAT image to plaintext."""
    if len(raw) <= TRAILER:
        raise FdatError(f"file too small to be an FDAT: {len(raw)} bytes")
    # The trailer is 0x110 bytes and the IV is its FIRST 0x10, not its last:
    # the reference implementation seeks to -0x110 and then reads 0x10 bytes.
    body = raw[:-TRAILER]
    iv = raw[-TRAILER:-TRAILER + IV_LEN]
    if len(iv) != IV_LEN:
        raise FdatError(f"bad IV length {len(iv)}")
    out = bytearray()
    for chunk in _decrypt_blocks(body, iv):
        out += chunk
    return bytes(out)


def parse_header(h: bytes) -> dict:
    """Parse the 520-byte FDAT header and the file-system descriptor array."""
    if len(h) < HDR_SIZE:
        raise FdatError(f"header truncated: {len(h)} < {HDR_SIZE}")
    if h[:8] != FDAT_MAGIC:
        raise FdatError(f"bad magic {h[:8]!r}, expected {FDAT_MAGIC!r}")
    if h[12:16] != FDAT_VERSION:
        raise FdatError(f"bad version {h[12:16]!r}, expected {FDAT_VERSION!r}")
    ver_minor, ver_major = h[0x20], h[0x21]
    model, region = struct.unpack_from("<II", h, 0x24)
    fw_off, fw_len = struct.unpack_from("<II", h, 0x30)
    nfs = struct.unpack_from("<I", h, 0x38)[0]
    if nfs > MAX_FS:
        raise FdatError(f"numFileSystems {nfs} > {MAX_FS}")
    filesystems = []
    for i in range(nfs):
        o = 0x40 + i * 16
        filesystems.append({
            "modeType": chr(h[o]),
            "offset": struct.unpack_from("<I", h, o + 4)[0],
            "size": struct.unpack_from("<I", h, o + 8)[0],
        })
    return {
        "checksum": struct.unpack_from("<I", h, 8)[0],
        "modeType": chr(h[0x10]),
        "luwFlag": chr(h[0x14]),
        "version": f"{ver_major}.{ver_minor:02x}",
        "model": model,
        "region": region,
        "firmware_offset": fw_off,
        "firmware_size": fw_len,
        "filesystems": filesystems,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("fdat", type=Path)
    ap.add_argument("--out", type=Path, default=Path("."))
    ap.add_argument("--payload", action="store_true",
                    help="write the firmware tar to OUT/fdat_payload.bin")
    ap.add_argument("--list", action="store_true",
                    help="list the payload tar members")
    args = ap.parse_args(argv)

    raw = args.fdat.read_bytes()
    print(f"input   {args.fdat}  ({len(raw):,} bytes)")

    plain = decrypt(raw)
    print(f"decoded {len(plain):,} bytes")
    info = parse_header(plain[:HDR_SIZE])

    print(f"\n  magic      {FDAT_MAGIC!r}  version {FDAT_VERSION!r}")
    print(f"  model      0x{info['model']:08x}   region 0x{info['region']:08x}")
    print(f"  version    {info['version']}   modeType {info['modeType']!r} "
          f"luwFlag {info['luwFlag']!r}")
    print(f"  firmware   offset=0x{info['firmware_offset']:x} "
          f"size={info['firmware_size']:,} "
          f"(0x{info['firmware_size']:x})")
    for i, fs in enumerate(info["filesystems"]):
        print(f"    fs[{i}] modeType={fs['modeType']!r} "
              f"offset=0x{fs['offset']:x} size=0x{fs['size']:x}")

    # The CramFS body should start with its magic; a cheap independent check that
    # the unpack really worked rather than merely producing plausible bytes.
    fs0 = info["filesystems"][0]
    if fs0["size"]:
        magic = plain[fs0["offset"]:fs0["offset"] + 4]
        ok = magic == b"\x45\x3d\xcd\x28"
        print(f"\n  cramfs     magic {magic.hex(' ')} "
              f"{'OK' if ok else 'UNEXPECTED'}")

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    blob = out / "fdat_decrypted.bin"
    blob.write_bytes(plain)
    print(f"\n  wrote {blob} ({blob.stat().st_size:,} bytes)")

    if args.payload or args.list:
        fw = info["firmware_offset"]
        size = info["firmware_size"]
        if fw + size > len(plain):
            raise FdatError(
                f"firmware region 0x{fw:x}+0x{size:x} runs past the decoded "
                f"image ({len(plain):,} bytes) -- truncated package?"
            )
        pay = out / "fdat_payload.bin"
        pay.write_bytes(plain[fw:fw + size])
        print(f"  wrote {pay} ({pay.stat().st_size:,} bytes)")
        with tarfile.open(pay) as tf:
            members = tf.getmembers()
        print(f"  payload is a tar with {len(members)} members")
        if args.list:
            for m in members:
                print(f"    {m.size:>11,}  {m.name}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FdatError as exc:
        sys.exit(f"fdat_decrypt: {exc}")
