## Hardware Codec 10-Bit Packing Modes & Pipeline Open Layout Uncovered — 30 October 2026

Dissected RTOS codec hardware interface and Imola encoder/decoder drivers in `.local/dumps/firmware/av-cam.bin`:
1. `open_param` IPC layout (`0x6368cffc..0x6368d8cc`): wire SSYC `+0x36` maps to `[open_param + 0x50]` (`input_image_bit_depth`: 0=8-bit, 1=10-bit), `+0x54` (`input_image_compress`), `+0x58` (`input_image_chroma` = 0 for 4:2:2). Dispatched via IPC message `0x2103` (subtype `0x0100` OPEN, length `0x90`) to mailbox `0x0061003c`.
2. Imola capacity checks (`0x639f506e..0x639f528c`): when `bit_depth == 1`, hardware verifies buffer capacity against discrete limits:
   - Mode 4 (10-bit packed 4:2:2): `0x004f1a00` = 5,184,000 bytes (1920x1080x2.5 bytes, 5 bytes per 2 pixels packed Y0 Cb Y1 Cr into 40 bits).
   - Mode 5 (10-bit padded 4:2:2): `0x007e9000` = 8,294,400 bytes (1920x1080x4 bytes, 16 bits per component).
   - At `0x639e953e`: in 10-bit mode, Imola bypasses 8-bit planar copying and sets up raw high-depth frame pointers (`PicAddressTop`, `PicAddressTop_C`).
3. User-space parameter `0x2007` (`PARAMID_REC_FORMAT_VIDEO_BIT_DEPTH`): fetched in `libObj.so` at `+0x970c06`, stored to `[ctx + 0x270]`, and forwarded to `libmpr.so` (`MprIf::DrawPixels`, `MprIf::GetRegionInfo`).
4. Next: trace `libmpr.so` IPC down to RTOS mailbox to identify the trigger switching pipeline config `[config + 0x37] = 1`, confirm DMM allocation size for Channel 0, and design a bit-preserving UVC 1.5 streaming descriptor (`v210` / `Y210`) bypassing the legacy 8-bit resize filter.

