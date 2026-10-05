import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
av_path = HERE / "dumps" / "av-cam.bin"
av = av_path.read_bytes()
base = 0x635c6000

# Scan instructions in 0x00070000 to 0x00095000
pend = {}
hits = {}
for addr in range(0x00070000, 0x00095000, 2):
    hw = struct.unpack_from('<H', av, addr)[0]
    if (hw & 0xF800) == 0x4800:
        rx = (hw >> 8) & 7
        disp = (hw & 0xFF) * 4
        pool = ((addr + 4) & ~3) + disp
        if pool < len(av) - 4:
            pend[rx] = struct.unpack_from('<i', av, pool)[0]
    elif 0x4478 <= hw <= 0x447f:
        rx = hw & 7
        if rx in pend:
            val = pend.pop(rx)
            target = (val + addr + 4) & 0xFFFFFFFF
            if 0x94c000 <= target <= 0x951000:
                s = av[target:target+60].split(b'\x00')[0]
                hits[addr] = (target, s)

print(f"Found {len(hits)} string references in codec area:")
for addr, (target, s) in sorted(hits.items()):
    try:
        st = s.decode('ascii')
    except:
        st = str(s)
    if any(k in st for k in ['avsc', 'scanMode', 'pictureSize', 'Aspect', 'mcMode', 'targetVideoFormat', 'CdSeqCtrlEnc']):
        print(f"  0x{addr:08x} (VA 0x{base+addr:08x}) -> [0x{target:08x}] \"{st[:50]}\"")
