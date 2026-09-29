"""Build a self-contained ARM Thumb-2 payload for the service-mode proof.

Replaces cmdline_show_revision() in libtestcmd.so with code that uses raw
Linux syscalls only -- no relocations, no PLT, no libc -- so the patched
object needs no new dynamic entries and the loader has nothing new to bind.

The payload opens /tmp/opx, writes a marker, and returns 0, which is what
the original function returned.

Armed only after the caller-visible behaviour was checked: the original is
68 bytes of which the last 28 are its own literal pool, so the whole
function is self-contained and can be replaced wholesale.
"""
import hashlib
import pathlib
import struct

from keystone import KS_ARCH_ARM, KS_MODE_THUMB, Ks

# /tmp/ox\0  ->  exactly 8 bytes, so two words and the NUL comes for free
PATH = b"/tmp/ox\x00"
# OPX\n -> written to the file
BODY = b"OPX\n"

SLOT_VADDR = 0x1A48
SLOT_SIZE = 68

ASM = """
    push  {r7, lr}
    sub   sp, sp, #16
    /* --- path at [sp,#0]: 8 bytes, NUL is the last of them --- */
    movw  r1, #%(p0)s
    movt  r1, #%(p0h)s
    str   r1, [sp, #0]
    movw  r1, #%(p1)s
    movt  r1, #%(p1h)s
    str   r1, [sp, #4]
    /* --- body at [sp,#8], past the path's terminator --- */
    movw  r1, #%(b0)s
    movt  r1, #%(b0h)s
    str   r1, [sp, #8]
    /* --- open(path, O_WRONLY|O_CREAT|O_TRUNC) --- */
    mov   r0, sp
    movw  r1, #0x0241
    mov   r7, #5
    svc   #0
    /* --- write(fd, body, 4); fd is still in r0 --- */
    add   r1, sp, #8
    mov   r2, #4
    mov   r7, #4
    svc   #0
    /* --- return 0, which is what the original returned --- */
    mov   r0, #0
    add   sp, sp, #16
    pop   {r7, pc}
"""


def imm16_pair(value):
    return value & 0xFFFF, (value >> 16) & 0xFFFF


def build():
    p0, p0h = imm16_pair(struct.unpack_from("<I", PATH, 0)[0])
    p1, p1h = imm16_pair(struct.unpack_from("<I", PATH, 4)[0])
    b0, b0h = imm16_pair(struct.unpack_from("<I", BODY, 0)[0])
    src = ASM % dict(p0=hex(p0), p0h=hex(p0h), p1=hex(p1), p1h=hex(p1h),
                     b0=hex(b0), b0h=hex(b0h))
    ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
    # assemble line by line so the per-instruction cost is visible
    out = bytearray()
    for line in src.splitlines():
        line = line.split("/*")[0].strip()
        if not line:
            continue
        enc, _ = ks.asm(line, as_bytes=True)
        enc = bytes(enc)
        print("  %3d  %s" % (len(enc), line))
        out += enc
    return bytes(out), src


def main():
    code, src = build()
    print(src)
    print("assembled %d bytes (slot is %d)" % (len(code), SLOT_SIZE))
    assert len(code) <= SLOT_SIZE, "payload does not fit in the slot"
    pad = SLOT_SIZE - len(code)
    payload = code + b"\x00" * pad

    src_lib = pathlib.Path("dumps/camera_2025/usr/usr/lib/libtestcmd.so")
    out = pathlib.Path("research/firmware/libtestcmd.OPX.so")
    d = bytearray(src_lib.read_bytes())
    orig = bytes(d[SLOT_VADDR:SLOT_VADDR + SLOT_SIZE])
    d[SLOT_VADDR:SLOT_VADDR + SLOT_SIZE] = payload
    out.write_bytes(bytes(d))

    print()
    print("original %d bytes at 0x%04x: %s" % (SLOT_SIZE, SLOT_VADDR, orig.hex()))
    print("payload  %d bytes at 0x%04x: %s" % (len(code), SLOT_VADDR, code.hex()))
    print("padding  %d bytes of 00" % pad)
    print()
    print("stock md5 : %s" % hashlib.md5(src_lib.read_bytes()).hexdigest())
    print("patched   : %s" % hashlib.md5(bytes(d)).hexdigest())
    print("size      : %d (unchanged)" % len(d))
    print("written   : %s" % out)

    # the payload must not change the file length or any header
    a, b = src_lib.read_bytes(), bytes(d)
    assert len(a) == len(b)
    diffs = [i for i in range(len(a)) if a[i] != b[i]]
    lo, hi = SLOT_VADDR, SLOT_VADDR + SLOT_SIZE
    assert all(lo <= i < hi for i in diffs), [i for i in diffs if not lo <= i < hi]
    print("byte diff %d of %d, all inside 0x%04x..0x%04x" %
          (len(diffs), SLOT_SIZE, lo, hi - 1))


if __name__ == "__main__":
    main()
