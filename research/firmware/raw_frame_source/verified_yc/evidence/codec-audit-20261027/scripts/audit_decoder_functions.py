import struct

def zigzag(z: int) -> int:
    if z == 0:
        return 0
    return (z + 1) // 2 if (z & 1) else -(z // 2)

def decode_block_luma64(blk: bytes) -> list[float]:
    """
    Decodes full 64 individual luma pixels for a 64-pixel strip:
    1. Decodes 8 sub-block anchors using true luma polarity.
    2. Parses subsequent Laplacian residual deltas for intra-subblock 8-pixel refinement.
    """
    ws = struct.unpack_from("<8Q", blk, 0)
    w0 = ws[0]
    t16 = (w0 >> 48) & 0xFFFF
    nib = t16 & 0xF
    b5 = (w0 >> 40) & 0xFF
    b16 = (w0 >> 32) & 0xFFFF
    s0 = "".join(f"{ws[k]:064b}" for k in [0, 2, 3, 4, 5])

    # 1. Base anchor Y0
    if nib >= 0xC:
        if nib == 0xC:
            if b5 >= 0x40:
                y0 = 76.0 + (0x4800 - min(0x4800, max(0x4000, b16))) / 2048.0 * 8.0
                cur = 23
            else:
                y0 = 18.0 + max(0.0, min(1.0, (b16 - 0x1380) / 3456.0)) * 58.0
                cur = 22
        else:
            y0 = 80.0 - (nib - 0xC) * 2.0
            cur = 24
    elif nib in (0xA, 0xB):
        if nib == 0xB:
            y0, cur = 82.0, 24
        elif b5 >= 0x80:
            y0, cur = 78.0 + max(0.0, min(1.0, (b16 - 0x8200) / 3584.0)) * 14.0, 23
        elif b5 >= 0x20:
            y0, cur = 92.0 + max(0.0, min(1.0, (0x3600 - b16) / 6144.0)) * 16.0, 24
        else:
            y0, cur = 110.0 + max(0.0, min(1.0, (0x1200 - b16) / 1536.0)) * 14.0, 24
    else:
        if nib == 0x1:
            y0, cur = 248.0, 24
        elif b5 >= 0x80 and b5 < 0xA0:
            y0, cur = 126.0 + max(0.0, min(1.0, (b16 - 0x8200) / 3584.0)) * 18.0, 23
        elif b5 >= 0xA0:
            y0, cur = 145.0 + max(0.0, min(1.0, (b16 - 0xA000) / 4096.0)) * 10.0, 24
        elif b5 >= 0x20:
            y0, cur = 155.0 + max(0.0, min(1.0, (0x3500 - b16) / 5632.0)) * 27.0, 24
        else:
            y0, cur = 182.0 + max(0.0, min(1.0, (0x1E00 - b16) / 5632.0)) * 60.0, 24

    subs = [y0]
    val = y0
    for sb_idx in range(1, 8):
        q2 = (t16 >> (16 - 2 * sb_idx)) & 0x3
        step = 1.6 * (1 << (3 - q2)) if q2 < 3 else 1.6
        z = 0
        while cur < len(s0) and s0[cur] == '0' and z < 10:
            z += 1
            cur += 1
        if cur < len(s0) and s0[cur] == '1':
            cur += 1
        val = max(0.0, min(255.0, val + zigzag(z) * step))
        subs.append(val)

    # 2. Parse residual deltas for intra-subblock pixels
    # Parse available tokens
    res_tokens = []
    cur_z = 0
    for b in s0[cur:]:
        if b == '0':
            cur_z += 1
            if cur_z > 16:
                break
        else:
            res_tokens.append(zigzag(cur_z))
            cur_z = 0
            if len(res_tokens) >= 56:
                break

    # Reconstruct 64 pixels:
    # Each sub-block sb has 8 pixels. sb 0 uses subs[0], sb 1 uses subs[1], etc.
    # The 56 residual tokens refine the 7 intra-subblock pixels in each sub-block.
    pixels = []
    tok_idx = 0
    for sb in range(8):
        base = subs[sb]
        pixels.append(base)
        cur_px = base
        for p in range(7):
            if tok_idx < len(res_tokens):
                d = res_tokens[tok_idx] * 0.8
                tok_idx += 1
            else:
                d = 0.0
            cur_px = max(0.0, min(255.0, cur_px + d))
            pixels.append(cur_px)
    return pixels, {"tokens":len(res_tokens),"anchor_end":cur,"y0":y0}

def decode_block_chroma64(blk: bytes) -> tuple[list[float], list[float]]:
    """
    Decodes 32 Cb and 32 Cr chroma samples for a 64-pixel strip.
    Stream 1 carries Cb base, Cr base, followed by planar/interleaved delta tokens.
    """
    ws = struct.unpack_from("<8Q", blk, 0)
    s1 = "".join(f"{ws[k]:064b}"[::-1] for k in [1, 7, 6, 5, 4])
    h6 = s1[:6]

    cur = 6
    z1 = 0
    while cur < 14 and s1[cur] == '0':
        z1 += 1
        cur += 1
    rem7 = int(s1[6:13][::-1], 2) if len(s1) >= 13 else 0

    if h6 in ("010000", "010001"):
        cb_base = 128.0 - 20.0 + z1 * 2.2 + (rem7 / 128.0) * 3.0
        cur_cr = 13
    elif h6 in ("000100", "000101"):
        cb_base = 128.0 - 10.0 + z1 * 2.5 + (rem7 / 128.0) * 3.0
        cur_cr = 13 if z1 <= 1 else 14
    elif h6 == "000001":
        cb_base = 128.0 - 3.0 + (z1 - 3) * 1.8 + (rem7 / 128.0) * 2.0
        cur_cr = 14
    else:  # "000000" and "100xxx" (desaturated shadows / neutral)
        cb_base = 128.0 + 0.5 + (z1 - 1) * 1.2 + ((rem7 - 48) / 128.0) * 2.0
        cur_cr = 13 if z1 == 0 else min(20, 12 + z1)

    c = cur_cr
    z2 = 0
    while c < 30 and c < len(s1) and s1[c] == '0':
        z2 += 1
        c += 1
    cr_base = 128.0 - (cb_base - 128.0) * 0.55 + zigzag(min(z2, 6)) * 1.4

    # Parse residual chroma tokens from bit 20 onwards
    chroma_tokens = []
    cur_z = 0
    for b in s1[20:]:
        if b == '0':
            cur_z += 1
            if cur_z > 16:
                break
        else:
            chroma_tokens.append(zigzag(cur_z))
            cur_z = 0
            if len(chroma_tokens) >= 64:
                break

    # Planar layout: first 32 tokens -> Cb deltas, next 32 tokens -> Cr deltas
    cb_samples = []
    val = cb_base
    for i in range(32):
        if i < len(chroma_tokens):
            val = max(16.0, min(240.0, val + chroma_tokens[i] * 0.75))
        cb_samples.append(val)

    cr_samples = []
    val = cr_base
    for i in range(32):
        tok_i = 32 + i
        if tok_i < len(chroma_tokens):
            val = max(16.0, min(240.0, val + chroma_tokens[tok_i] * 0.75))
        cr_samples.append(val)

    return cb_samples, cr_samples, {"tokens":len(chroma_tokens),"cb_base":cb_base,"cr_base":cr_base}
