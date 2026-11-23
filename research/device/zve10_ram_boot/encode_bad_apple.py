"""Encode a video (e.g. Bad Apple) into a 1-bit XOR-RLE ZVBA clip.bin for the ZV-E10."""
import argparse
import struct
import subprocess
from pathlib import Path

import numpy as np

ZVBA_MAGIC = 0x4142565A  # "ZVBA"
ZVBA_HEADER = struct.Struct("<IHHII")  # magic, width, height, fps, frame_count
MAX_CLIP_BYTES = 16 * 1024 * 1024


def packbits_encode(data: bytes) -> bytes:
    """Encode bytes using PackBits: 0x00..0x7F = c+1 literals, 0x80..0xFF = (c&0x7F)+2 repeats."""
    out = bytearray()
    n = len(data)
    i = 0
    while i < n:
        # Check for run of >= 2 identical bytes (prefer runs of >= 3 unless at boundary).
        run = 1
        while i + run < n and run < 129 and data[i + run] == data[i]:
            run += 1
        if run >= 3 or (run == 2 and i + 2 == n):
            out.append(0x80 | (run - 2))
            out.append(data[i])
            i += run
            continue
        # Literal run up to 128 bytes.
        lit_start = i
        i += 1
        while i < n and (i - lit_start) < 128:
            if i + 2 < n and data[i] == data[i + 1] == data[i + 2]:
                break
            i += 1
        out.append((i - lit_start) - 1)
        out.extend(data[lit_start:i])
    return bytes(out)


def packbits_decode_xor(payload: bytes, shadow: bytearray) -> None:
    """Decode PackBits XOR delta in-place into shadow (used for round-trip verification)."""
    pos = 0
    i = 0
    n = len(payload)
    while i < n:
        ctrl = payload[i]
        i += 1
        if ctrl & 0x80:
            count = (ctrl & 0x7F) + 2
            val = payload[i]
            i += 1
            if val:
                for _ in range(count):
                    shadow[pos] ^= val
                    pos += 1
            else:
                pos += count
        else:
            count = ctrl + 1
            for _ in range(count):
                shadow[pos] ^= payload[i]
                i += 1
                pos += 1
    assert pos == len(shadow), (pos, len(shadow))


def encode_frames(frames_1bit: list[bytes], width: int, height: int, fps: int) -> bytes:
    row_bytes = width // 8
    frame_bytes = row_bytes * height
    prev = bytearray(frame_bytes)
    verify_shadow = bytearray(frame_bytes)
    chunks = [ZVBA_HEADER.pack(ZVBA_MAGIC, width, height, fps, len(frames_1bit))]

    for idx, cur in enumerate(frames_1bit):
        assert len(cur) == frame_bytes
        delta = bytes(a ^ b for a, b in zip(cur, prev))
        comp = packbits_encode(delta)
        packbits_decode_xor(comp, verify_shadow)
        assert bytes(verify_shadow) == cur, f"Round-trip mismatch on frame {idx}"
        pad = (-len(comp)) & 3
        chunks.append(struct.pack("<I", len(comp)))
        chunks.append(comp)
        if pad:
            chunks.append(b"\x00" * pad)
        prev[:] = cur

    return b"".join(chunks)


def extract_1bit_frames(video_path: Path, width: int, height: int, fps: int, threshold: int) -> list[bytes]:
    vf = f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,format=gray"
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(video_path),
        "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
    ]
    raw = subprocess.check_output(cmd)
    frame_pixels = width * height
    count = len(raw) // frame_pixels
    frames = []
    for i in range(count):
        gray = np.frombuffer(raw, dtype=np.uint8, count=frame_pixels, offset=i * frame_pixels)
        bits = (gray >= threshold).astype(np.uint8)
        packed = np.packbits(bits, bitorder="big").tobytes()
        frames.append(packed)
    return frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--threshold", type=int, default=128)
    args = parser.parse_args()

    frames = extract_1bit_frames(args.input, args.width, args.height, args.fps, args.threshold)
    blob = encode_frames(frames, args.width, args.height, args.fps)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(blob)
    print(f"Encoded {len(frames)} frames ({args.width}x{args.height} @ {args.fps} fps) -> {args.out} ({len(blob)} bytes, {len(blob) / (1024 * 1024):.2f} MiB)")
    if len(blob) > MAX_CLIP_BYTES:
        raise SystemExit(f"Clip exceeds 16 MiB limit ({len(blob)} > {MAX_CLIP_BYTES})")


if __name__ == "__main__":
    main()
