"""Host receiver/unpacker for Sony ZV-E10 full-size Bayer RAW over UVC (ZVRAW001)."""
import argparse, json, struct, subprocess, sys, zlib
from pathlib import Path

HDR_MAGIC = b"ZVRAW001"
HDR_SIZE = 64
UVC_WIDTH = 6144
UVC_HEIGHT = 4100
UVC_FRAME_BYTES = UVC_WIDTH * UVC_HEIGHT * 2


def parse_header(hdr: bytes) -> dict:
    if len(hdr) != HDR_SIZE or hdr[:8] != HDR_MAGIC:
        raise ValueError("Invalid ZVRAW001 magic")
    fields = struct.unpack_from("<12I", hdr, 8)
    (version, hdr_bytes, frame_seq, raw_bytes, raw_addr, op_tag,
     seq_mode_ab, pkt_c, pkt_d, payload_crc32, hdr_crc32, reserved) = fields
    if version != 1 or hdr_bytes != HDR_SIZE:
        raise ValueError(f"Unsupported header version={version} hdr_bytes={hdr_bytes}")
    calc_hcrc = zlib.crc32(hdr[:48]) & 0xFFFFFFFF
    if calc_hcrc != hdr_crc32:
        raise ValueError(f"Header CRC mismatch: got {calc_hcrc:#x}, expected {hdr_crc32:#x}")
    if raw_bytes == 0 or raw_bytes > UVC_FRAME_BYTES - HDR_SIZE:
        raise ValueError(f"Invalid raw_bytes={raw_bytes}")
    return {
        "version": version,
        "frame_seq": frame_seq,
        "raw_bytes": raw_bytes,
        "raw_address": f"0x{raw_addr:08x}",
        "op": op_tag & 0xFFFF,
        "tag": (op_tag >> 16) & 0xFFFF,
        "sequence": seq_mode_ab & 0xFF,
        "mode": (seq_mode_ab >> 8) & 0xFF,
        "a": (seq_mode_ab >> 16) & 0xFF,
        "b": (seq_mode_ab >> 24) & 0xFF,
        "c": pkt_c,
        "d": pkt_d,
        "payload_crc32": f"0x{payload_crc32:08x}",
        "payload_crc32_int": payload_crc32,
        "header_crc32": f"0x{hdr_crc32:08x}",
        "reserved": reserved,
    }


def extract_frames(data: bytes, out_dir: Path) -> list:
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    pos = 0
    idx = 0
    while True:
        hit = data.find(HDR_MAGIC, pos)
        if hit < 0 or hit + UVC_FRAME_BYTES > len(data):
            break
        frame_blob = data[hit : hit + UVC_FRAME_BYTES]
        try:
            meta = parse_header(frame_blob[:HDR_SIZE])
        except ValueError:
            pos = hit + 8
            continue
        raw = frame_blob[HDR_SIZE : HDR_SIZE + meta["raw_bytes"]]
        calc_pcrc = zlib.crc32(raw) & 0xFFFFFFFF
        if calc_pcrc != meta["payload_crc32_int"]:
            raise ValueError(
                f"Frame {idx} payload CRC mismatch: got {calc_pcrc:#x}, expected {meta['payload_crc32']}"
            )
        idx += 1
        stem = f"raw_frame_{idx:03d}_seq{meta['frame_seq']}"
        raw_path = out_dir / f"{stem}.raw"
        json_path = out_dir / f"{stem}.json"
        raw_path.write_bytes(raw)
        meta["extracted_file"] = str(raw_path)
        meta["frame_offset_in_capture"] = hit
        json_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        results.append(meta)
        pos = hit + UVC_FRAME_BYTES
    return results


def capture_dshow(device_name: str, frames: int, out_capture: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-f", "dshow",
        "-video_size", f"{UVC_WIDTH}x{UVC_HEIGHT}",
        "-pixel_format", "yuyv422",
        "-i", f"video={device_name}",
        "-frames:v", str(frames),
        "-c:v", "copy", "-f", "rawvideo",
        str(out_capture),
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, help="Existing rawvideo UVC capture file to unpack")
    ap.add_argument("--dshow", type=str, help="Windows DirectShow camera name to capture from via ffmpeg")
    ap.add_argument("--frames", type=int, default=2, help="Number of UVC frames to capture")
    ap.add_argument("--output", type=Path, required=True, help="Output directory")
    args = ap.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    cap_path = args.input or (args.output / "uvc_capture.bin")
    if args.dshow:
        capture_dshow(args.dshow, args.frames, cap_path)
    elif not cap_path.exists():
        ap.error("Provide --input <file> or --dshow <device>")

    res = extract_frames(cap_path.read_bytes(), args.output)
    print(json.dumps(res, indent=2))
    if not res:
        print("NO_VALID_ZVRAW001_FRAMES_FOUND", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
