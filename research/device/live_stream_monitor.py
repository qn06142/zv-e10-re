import time
import sys
from pathlib import Path
import cv2
import numpy as np

OUT_DIR = Path(".local/captures/live_monitor_v47")
OUT_DIR.mkdir(parents=True, exist_ok=True)

print("[*] Opening DirectShow camera 0 at 1920x1080 @ 24fps YUY2...")
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
if not cap.isOpened():
    print("[-] Error: Cannot open DirectShow camera 0")
    sys.exit(1)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
cap.set(cv2.CAP_PROP_FPS, 24.0)
try:
    fourcc = cv2.VideoWriter_fourcc(*"YUY2")
    cap.set(cv2.CAP_PROP_FOURCC, fourcc)
except Exception:
    pass

actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
actual_fps = cap.get(cv2.CAP_PROP_FPS)
print(f"[+] Device opened: {actual_w}x{actual_h} @ {actual_fps} fps")

TOTAL_FRAMES = 50
frames_read = 0
real_frames = 0
last_t = time.perf_counter()
start_t = last_t

spooled = 0
for i in range(TOTAL_FRAMES):
    ret, frame = cap.read()
    now = time.perf_counter()
    dt_ms = (now - last_t) * 1000.0
    last_t = now
    if not ret:
        print(f"[-] Frame {i}: read() failed!")
        break

    mean_val = float(frame.mean())
    std_val = float(frame.std())
    min_val = int(frame.min())
    max_val = int(frame.max())

    is_real = mean_val > 5.0
    if is_real:
        real_frames += 1
        if spooled < 5:
            cv2.imwrite(str(OUT_DIR / f"real_frame_{spooled:02d}.png"), frame)
            spooled += 1

    status = "REAL_FRAME" if is_real else "TIMEOUT_BLACK"
    print(f"  Frame {i:02d} (+{dt_ms:6.1f} ms): mean={mean_val:6.2f}, std={std_val:5.2f}, range=[{min_val:3d}..{max_val:3d}] -> {status}")

cap.release()
elapsed = time.perf_counter() - start_t
print(f"\n[+] Capture summary: {real_frames}/{TOTAL_FRAMES} real frames captured in {elapsed:.2f} s")
if real_frames > 0:
    print(f"[+] Successfully saved {spooled} real image frames to {OUT_DIR}/")
