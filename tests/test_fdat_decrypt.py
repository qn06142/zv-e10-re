"""Tests for research/firmware/fdat_decrypt.py -- the FDAT (UDTRFIRM) decrypter.

The decrypter is worth testing carefully because its failure mode is silent and
very convincing.  `dumps/fdat_decrypted.bin` from an earlier session decoded to a
flawless-looking `UDTRFIRM` header while every byte after the first 1024-byte
block was random.  Anything built on that file was wrong.

So these tests cover three things:

  1. a synthetic round trip, which proves the block layout, the IV position and
     the unpacking agree with each other;
  2. the failure paths, which must raise rather than return plausible garbage --
     that is the property the old artefact lacked;
  3. the real header and the real payload, so a change to the keys or the
     algorithm cannot pass by being self-consistent.

The image-dependent tests skip when dumps/ is absent.
"""
from __future__ import annotations

import importlib.util
import struct
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "research" / "firmware" / "fdat_decrypt.py"

_spec = importlib.util.spec_from_file_location("fdat_decrypt", MODULE_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover
    pytest.skip("fdat_decrypt.py not found", allow_module_level=True)
fdat = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fdat)

try:
    from Cryptodome.Cipher import AES as _AES
except ImportError:  # pragma: no cover
    try:
        from Crypto.Cipher import AES as _AES
    except ImportError:
        pytest.skip("pycryptodome not installed", allow_module_level=True)

DUMP = ROOT / "dumps" / "fdat_cxd90045.bin"
PAYLOAD = ROOT / "dumps" / "fdat_payload.bin"
needs_dump = pytest.mark.skipif(
    not (DUMP.is_file() and PAYLOAD.is_file()),
    reason="decrypted FDAT artefacts not present",
)


# --------------------------------------------------------------- synthesis --

def _pack_block(payload: bytes, is_last: bool) -> bytes:
    """Build a 1024-byte ciphertext block the way packBlock() does."""
    size_and_end = len(payload) | (0x8000 if is_last else 0)
    body = struct.pack("<H", size_and_end) + payload
    body += b"\xff" * (fdat.BLOCK - 4 - len(payload))
    return struct.pack("<H", fdat._sum16(body)) + body


def _build_image(plaintext: bytes) -> bytes:
    """Encrypt `plaintext` into a full FDAT file, inverting decrypt().

    Chunks by BLOCK-4, not BLOCK: each block spends 4 bytes on checksum and
    size|endflag, so 1020 is the largest payload a block can carry.  Chunking by
    BLOCK would make `b"\xff" * (BLOCK - 4 - len(payload))` multiply by a negative
    count -- which yields an empty pad and a silently malformed block.
    """
    max_payload = fdat.BLOCK - 4
    blocks = [
        plaintext[i:i + max_payload]
        for i in range(0, len(plaintext), max_payload)
    ]
    if not blocks:
        blocks = [b""]
    out = bytearray()
    iv = bytes(range(16))
    enc = _AES.new(fdat.KEY_CXD90045, _AES.MODE_CBC, iv)
    for i, blk in enumerate(blocks):
        raw = _pack_block(blk, is_last=(i == len(blocks) - 1))
        if i == 0:
            half = fdat.BLOCK // 2
            out += _AES.new(fdat.KEY_AES, _AES.MODE_ECB).encrypt(raw[:half])
            out += enc.encrypt(raw[half:])
        else:
            out += enc.encrypt(raw)
    return bytes(out) + iv + bytes(fdat.TRAILER - fdat.IV_LEN)


# ------------------------------------------------------------------- tests --

def test_round_trip_single_block():
    plain = b"UDTRFIRM" + bytes(range(0x18, 0x18 + 16))
    assert fdat.decrypt(_build_image(plain)) == plain


def test_round_trip_multi_block():
    # More than one block, so the CBC chain and the end-flag handling are both
    # exercised -- the single-block case cannot catch a wrong IV position.
    plain = bytes((i * 7 + 3) & 0xFF for i in range(fdat.BLOCK * 3 + 11))
    assert fdat.decrypt(_build_image(plain)) == plain


def test_iv_is_at_the_start_of_the_trailer():
    """The IV sits at [-0x110:-0x100], not in the last 16 bytes.

    This is the exact bug the first reimplementation had, and the block checksum
    is what caught it.  Moving the IV to the end of the trailer -- the intuitive
    reading -- must make the decode fail rather than yield garbage.
    """
    plain = bytes(range(256)) * 8
    img = _build_image(plain)
    moved = bytearray(img)
    head = bytes(moved[-fdat.TRAILER:-fdat.TRAILER + fdat.IV_LEN])
    tail = bytes(moved[-fdat.IV_LEN:])
    moved[-fdat.TRAILER:-fdat.TRAILER + fdat.IV_LEN] = tail
    moved[-fdat.IV_LEN:] = head
    with pytest.raises(fdat.FdatError):
        fdat.decrypt(bytes(moved))


def test_corrupt_block_raises_rather_than_returning_garbage():
    plain = bytes(64)
    img = bytearray(_build_image(plain))
    img[fdat.BLOCK // 2] ^= 0x01          # perturb the middle of block 0's body
    with pytest.raises(fdat.FdatError):
        fdat.decrypt(bytes(img))


def test_body_length_must_be_a_whole_number_of_blocks():
    plain = bytes(64)
    img = _build_image(plain)
    with pytest.raises(fdat.FdatError):
        fdat.decrypt(img + b"\x00")


def test_too_small_input():
    with pytest.raises(fdat.FdatError):
        fdat.decrypt(b"\x00" * 16)


def test_parse_header_rejects_bad_magic():
    h = bytearray(fdat.HDR_SIZE)
    h[12:16] = b"0100"
    with pytest.raises(fdat.FdatError, match="magic"):
        fdat.parse_header(bytes(h))


def test_parse_header_rejects_bad_version():
    h = bytearray(fdat.HDR_SIZE)
    h[0:8] = b"UDTRFIRM"
    h[12:16] = b"9999"
    with pytest.raises(fdat.FdatError, match="version"):
        fdat.parse_header(bytes(h))


def test_parse_header_rejects_too_many_filesystems():
    h = bytearray(fdat.HDR_SIZE)
    h[0:8] = b"UDTRFIRM"
    h[12:16] = b"0100"
    struct.pack_into("<I", h, 0x38, fdat.MAX_FS + 1)
    with pytest.raises(fdat.FdatError, match="numFileSystems"):
        fdat.parse_header(bytes(h))


def test_parse_header_reads_a_minimal_valid_header():
    h = bytearray(fdat.HDR_SIZE)
    h[0:8] = b"UDTRFIRM"
    h[12:16] = b"0100"
    h[0x10] = ord("U")
    h[0x14] = ord("N")
    h[0x20], h[0x21] = 0x03, 0x02          # 2.03
    struct.pack_into("<I", h, 0x24, 0x01030010)
    struct.pack_into("<I", h, 0x30, 0x24200)
    struct.pack_into("<I", h, 0x34, 0x161ABC00)
    struct.pack_into("<I", h, 0x38, 1)
    h[0x40] = ord("U")
    struct.pack_into("<I", h, 0x44, 0x200)
    struct.pack_into("<I", h, 0x48, 0x24000)
    info = fdat.parse_header(bytes(h))
    assert info["version"] == "2.03"
    assert info["model"] == 0x01030010
    assert info["firmware_offset"] == 0x24200
    assert info["firmware_size"] == 0x161ABC00
    assert info["filesystems"] == [
        {"modeType": "U", "offset": 0x200, "size": 0x24000}
    ]


# ------------------------------------------------------- real-image tests ---

@needs_dump
def test_real_header_matches_the_known_package():
    """Anchored to the actual ZV-E10 v2.03 package, not to a hand-derived guess."""
    info = fdat.parse_header(DUMP.read_bytes()[:fdat.HDR_SIZE])
    assert info["version"] == "2.03"
    assert info["model"] == 0x01030010
    assert info["firmware_offset"] == 0x24200
    assert info["firmware_size"] == 370_850_816
    assert info["filesystems"][0] == {
        "modeType": "U", "offset": 0x200, "size": 0x24000,
    }


@needs_dump
def test_real_cramfs_magic_at_the_declared_offset():
    """Independent check that the unpack produced real data, not plausible noise."""
    raw = DUMP.open("rb").read(0x400)
    assert raw[0x200:0x204] == b"\x45\x3d\xcd\x28"      # CramFS


@needs_dump
def test_real_payload_is_a_tar_with_the_expected_partitions():
    with tarfile.open(PAYLOAD) as tf:
        members = {m.name: m.size for m in tf.getmembers()}
    assert PAYLOAD.read_bytes()[257:262] == b"ustar"
    assert len(members) == 174
    # Sizes that pin down the package; nflasha15 and nflasha7 are the partitions
    # the camera's own flash dump never captured.
    assert members["0700_part_image/dev/nflasha3"] == 30_157_824
    assert members["0700_part_image/dev/nflasha7"] == 5_132_288
    assert members["0700_part_image/dev/nflasha15"] == 249_105_408


@needs_dump
def test_decrypting_fdat_raw_reproduces_the_reference_decode():
    """Pins the keys and the mode against a real decode.

    Compares against dumps/fdat_cxd90045.bin, which was produced independently
    via fwtool's own AesCbcCrypter, so a change to the keys or the chaining cannot
    pass by merely staying self-consistent.  Streams both sides: the payload is
    ~370 MB and must not be held twice in memory.
    """
    src = ROOT / "dumps" / "fdat_raw.bin"
    if not src.is_file():
        pytest.skip("fdat_raw.bin not present")
    raw = src.open("rb").read()
    body = raw[:-fdat.TRAILER]
    iv = raw[-fdat.TRAILER:-fdat.TRAILER + fdat.IV_LEN]
    ref = DUMP.open("rb")
    pos = 0
    try:
        for chunk in fdat._decrypt_blocks(body, iv):
            want = ref.read(len(chunk))
            assert want == chunk, f"diverges at decoded offset 0x{pos:x}"
            pos += len(chunk)
        assert ref.read(1) == b"", "decoded stream is longer than the reference"
    finally:
        ref.close()
    assert pos == DUMP.stat().st_size
