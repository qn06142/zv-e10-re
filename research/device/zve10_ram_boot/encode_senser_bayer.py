"""Package the 6048x4024 Senser adjustment capture as an embedded LCD fixture."""
import argparse
from pathlib import Path
import struct

import numpy as np


WIDTH, HEIGHT = 6048, 4024
BUFFER_BYTES = 48 * 1024 * 1024
BINNING = 8


def encode_capture(path):
    if path.stat().st_size != BUFFER_BYTES:
        raise ValueError("Expected the complete 48 MiB Senser capture buffer")
    mosaic = np.fromfile(path, "<u2", count=WIDTH * HEIGHT).reshape(HEIGHT, WIDTH)

    # Each coarse cell averages only the matching Bayer position. Trimming an
    # incomplete bottom bin keeps the phase and avoids inventing edge samples.
    coarse_width = WIDTH // (2 * BINNING)
    coarse_height = HEIGHT // (2 * BINNING)
    complete = mosaic[:coarse_height * 2 * BINNING, :coarse_width * 2 * BINNING]
    cells = complete.reshape(coarse_height, BINNING, 2, coarse_width, BINNING, 2)
    samples = cells.mean(axis=(1, 4))
    low, high = np.percentile(samples.mean(axis=(1, 3)), (1, 99.75))
    if high <= low:
        raise ValueError("Capture has no usable contrast")
    normalized = np.clip((samples - low) / (high - low), 0, 1)
    pixels = np.rint(np.sqrt(normalized) * 65535).astype("<u2")
    pixels = pixels.reshape(coarse_height * 2, coarse_width * 2)

    # The test renderer fills a 4:3 LCD. Letterbox at even row offsets to
    # preserve the 3:2 image aspect and Bayer phase.
    height = ((pixels.shape[1] * 3 + 7) // 8) * 2
    top = (height - pixels.shape[0]) // 4 * 2
    padded = np.zeros((height, pixels.shape[1]), dtype="<u2")
    padded[top:top + pixels.shape[0]] = pixels
    header = struct.pack("<4sHHII", b"ZVBR", padded.shape[1], padded.shape[0], 1, 0)
    return header + padded.tobytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_bytes(encode_capture(args.capture))


if __name__ == "__main__":
    main()
