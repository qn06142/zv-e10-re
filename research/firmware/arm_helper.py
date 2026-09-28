"""Build tiny static ARM Linux helpers with Keystone, in stages.

No cross-compiler is available, but keystone-engine is, so the ARM code is
assembled here and wrapped in a hand-made ELF32.  These are raw-syscall
binaries: no libc, no dynamic loader, nothing to fail at runtime except the
syscalls themselves.

The camera has /bin/busybox, whose `base64 -d` applet is the transport (there
is no push command in zve10_live.py, and the SD card is inside the camera).

FILE LAYOUT -- and this is the whole trick
-------------------------------------------
    file 0x000   ELF header (52) + one program header (32) = 0x54 bytes
    file 0x054   strings
    file 0x200   code   <- entry point

p_offset is 0x54, deliberately NOT page-aligned, and p_align is 1.  The
kernel maps at p_vaddr - p_offset, so

    vaddr(X) = 0x10000 + (X - 0x54)

which means every string address is known before assembly, so movw/movt
immediates are emitted directly with no PC dependence and no patch pass.

Why not page-align?  A page-aligned PT_LOAD forces a 4 KB file, whose base64
is ~6.2 KB of shell text -- and a command that long WEDGES the camera shell.
That was reproduced: a 6480-character command timed out the whole session and
left the camera needing a manual replug.  Unaligned keeps the helper under
~1 KB of text, which the shell accepts.

STAGES -- separate binaries, so a bug in one cannot wedge the camera:

  ok    write "OK" to stdout and exit.  Proves the ELF header, the transfer
        and exec, before any device is touched.
  dump  mmap a /dev/stream surface and save it to a file.  Does not modify the
        surface: this is how the panel is identified, by its pixels.
  poke  mmap the same surface and fill it with a pattern.  Only run after a
        dump has positively identified the surface.

Writing to a display surface cannot crash the camera: worst case we paint a
buffer nothing scans out, and the next UI frame overwrites it.
"""
import base64
import hashlib
import struct
from pathlib import Path

from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM, KS_MODE_LITTLE_ENDIAN

OUT = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera')
OUT.mkdir(parents=True, exist_ok=True)

DEV_STREAM = b'/dev/stream\x00'

O_WRONLY, O_RDWR = 1, 2
O_CREAT, O_TRUNC = 64, 512
PROT_RW = 3
MAP_SHARED = 1
NR_WRITE, NR_READ, NR_OPEN, NR_EXIT, NR_MMAP2 = 4, 3, 5, 1, 192

HDR = 0x54          # ELF header + program header
STR_OFF = 0x54
CODE_OFF = 0x200
VADDR = 0x00010000

# p_offset and p_vaddr MUST be congruent modulo the page size.  If they are
# not, the kernel maps the file page CONTAINING p_offset at the page-aligned
# p_vaddr, so every address derived from p_offset is wrong by the intra-page
# delta.  Getting this wrong put the entry point in the padding and the
# process was SIGKILLed (rc=137).  With p_offset = 0x54 and p_vaddr = 0x10054
# they are congruent (both 0x54 mod 0x1000) and the mapping is simply:
def vaddr(off):
    return VADDR + off


def pvaddr():
    """p_vaddr: congruent with p_offset mod page size."""
    return VADDR + HDR


def imm(v):
    return v & 0xFFFF, (v >> 16) & 0xFFFF


class Builder:
    def __init__(self):
        self.lines = []
        self.strings = bytearray()

    def emit(self, s):
        self.lines.append('    ' + s.strip())

    def put_str(self, data):
        while len(self.strings) % 4:
            self.strings += b'\x00'
        off = STR_OFF + len(self.strings)
        self.strings += data
        return vaddr(off)

    def load_addr(self, reg, a):
        lo, hi = imm(a)
        self.emit('movw %s, #%d' % (reg, lo))
        self.emit('movt %s, #%d' % (reg, hi))

    def set_imm(self, reg, val):
        """Load a 32-bit constant, using plain MOV only when it encodes.

        ARM's MOV (immediate) is an 8-bit value rotated by an EVEN amount, so
        anything needing more than 8 significant bits is not encodable -- e.g.
        a mmap page offset of 0x22312 (18 bits).  keystone raises
        KS_ERR_ASM_INVALID_OPERAND for those, so fall back to MOVW/MOVT.
        """
        ks = Ks(KS_ARCH_ARM, KS_MODE_ARM | KS_MODE_LITTLE_ENDIAN)
        try:
            ks.asm('mov %s, #%d' % (reg, val), 0)
            self.emit('mov %s, #%d' % (reg, val))
        except Exception:
            lo, hi = imm(val)
            self.emit('movw %s, #%d' % (reg, lo))
            self.emit('movt %s, #%d' % (reg, hi))

    def assemble(self):
        ks = Ks(KS_ARCH_ARM, KS_MODE_ARM | KS_MODE_LITTLE_ENDIAN)
        enc, _ = ks.asm('\n'.join(self.lines), vaddr(CODE_OFF))
        return bytes(enc)


def build(mode, offset=0, length=0, path=b'/setting/dump.bin\x00',
          pattern=0xFF, dev=b'/dev/stream\x00'):
    b = Builder()
    # NB: the label must not start with an underscore -- keystone rejects
    # `_start:` with KS_ERR_ASM_INVALID_OPERAND when it leads the block.
    b.emit('start:')

    if mode == 'ok':
        msg = b.put_str(b'ZV-E10 helper OK\n')
        b.emit('mov r7, #%d' % NR_WRITE)
        b.emit('mov r0, #1')
        b.load_addr('r1', msg)
        b.emit('mov r2, #16')
        b.emit('svc #0')
        b.emit('mov r0, #0')
        b.emit('mov r7, #%d' % NR_EXIT)
        b.emit('svc #0')

    elif mode in ('dump', 'poke'):
        a_dev = b.put_str(dev)
        a_out = b.put_str(path)

        if mode == 'dump':
            # Read (page_offset, length) from /setting/parm.bin instead of
            # baking them in, so trying a different /dev/stream surface costs
            # 8 bytes on the camera rather than a whole binary re-transfer.
            # pgoff is stored already divided by 4096 to avoid needing a
            # division routine.
            a_parm = b.put_str(b'/setting/parm.bin\x00')
            b.emit('sub sp, sp, #32')
            b.load_addr('r0', a_parm)
            b.emit('mov r1, #0')                 # O_RDONLY
            b.emit('mov r2, #0')
            b.emit('mov r7, #%d' % NR_OPEN)
            b.emit('svc #0')
            b.emit('cmp r0, #0')
            b.emit('blt fail')
            b.emit('mov r10, r0')
            b.emit('mov r0, r10')
            b.emit('mov r1, sp')
            b.emit('mov r2, #8')
            b.emit('mov r7, #%d' % NR_READ)
            b.emit('svc #0')

        # fd = open(dev, O_RDWR)
        b.load_addr('r0', a_dev)
        b.emit('mov r1, #%d' % O_RDWR)
        b.emit('mov r2, #0')
        b.emit('mov r7, #%d' % NR_OPEN)
        b.emit('svc #0')
        b.emit('cmp r0, #0')
        b.emit('blt fail')
        b.emit('mov r12, r0')                    # r12 = fd_dev

        # map = mmap2(NULL, length, PROT_RW, MAP_SHARED, fd, pgoff)
        b.emit('mov r0, #0')
        if mode == 'dump':
            b.emit('ldr r1, [sp, #4]')           # length from parm.bin
            b.emit('ldr r5, [sp]')               # page offset from parm.bin
        else:
            b.set_imm('r1', length)
            b.set_imm('r5', offset // 4096)
        b.emit('mov r2, #%d' % PROT_RW)
        b.emit('mov r3, #%d' % MAP_SHARED)
        b.emit('mov r4, r12')
        b.emit('mov r7, #%d' % NR_MMAP2)
        b.emit('svc #0')
        b.emit('movw r1, #0')
        b.emit('movt r1, #0x8000')
        b.emit('cmp r0, r1')
        b.emit('bhs fail')
        b.emit('mov r7, r0')                     # r7 = mapped base
        b.emit('mov r8, r0')                     # keep it for the header

        if mode == 'poke':
            b.emit('mov r0, r7')
            b.emit('mov r2, #%d' % pattern)
            b.set_imm('r3', length)
            b.emit('fill:')
            b.emit('strb r2, [r0], #1')
            b.emit('subs r3, r3, #1')
            b.emit('bne fill')
        else:
            # ofd = open(path, O_WRONLY|O_CREAT|O_TRUNC, 0666)
            b.load_addr('r0', a_out)
            b.emit('mov r1, #%d' % (O_WRONLY | O_CREAT | O_TRUNC))
            b.emit('mov r2, #0x1b6')
            b.emit('mov r7, #%d' % NR_OPEN)
            b.emit('svc #0')
            b.emit('cmp r0, #0')
            b.emit('mov r12, r0')                # keep ofd
            b.emit('blt fail')
            b.emit('mov r6, r12')

            # Write an 8-byte header first: magic 'ZVD1' then the mmap result.
            # If the surface write below turns out to be short or negative,
            # the file still exists with the header, so the mmap address and
            # the failure can be read back instead of guessed at.
            # The header buffer goes ABOVE the parm bytes, WITHOUT moving sp:
            # the parm word at [sp,#4] is read again later for the write
            # length, so decrementing sp here made that read pick up the
            # header's mmap address instead and every dump came back short
            # (exit 93).
            b.emit('add r9, sp, #16')
            b.emit('movw r0, #%d' % (0x3156445A & 0xFFFF))
            b.emit('movt r0, #%d' % (0x3156445A >> 16))
            b.emit('str r0, [r9]')
            b.emit('str r8, [r9, #4]')
            b.emit('mov r0, r6')
            b.emit('mov r1, r9')
            b.emit('mov r2, #8')
            b.emit('mov r7, #%d' % NR_WRITE)
            b.emit('svc #0')

            # write(ofd, map, length) -- report the result via the exit code
            b.emit('mov r0, r6')
            b.emit('mov r1, r8')
            if mode == 'dump':
                b.emit('ldr r2, [sp, #4]')
            else:
                b.set_imm('r2', length)
            b.emit('mov r7, #%d' % NR_WRITE)
            b.emit('svc #0')
            b.emit('cmp r0, #0')
            b.emit('bgt gotcount')
            b.emit('mov r0, #92')                # 92: write returned <= 0
            b.emit('mov r7, #%d' % NR_EXIT)
            b.emit('svc #0')
            b.emit('gotcount:')
            if mode == 'dump':
                b.emit('ldr r1, [sp, #4]')
            else:
                b.set_imm('r1', length)
            b.emit('cmp r0, r1')
            b.emit('beq alldone')
            b.emit('mov r0, #93')                # 93: short write
            b.emit('mov r7, #%d' % NR_EXIT)
            b.emit('svc #0')
            b.emit('alldone:')

        b.emit('mov r0, #0')
        b.emit('mov r7, #%d' % NR_EXIT)
        b.emit('svc #0')

    b.emit('fail:')
    b.emit('mov r0, #1')
    b.emit('mov r7, #%d' % NR_EXIT)
    b.emit('svc #0')
    return b.strings, b.assemble()


def elf(strings, code):
    eh = bytearray(52)
    eh[0:4] = b'\x7fELF'
    eh[4], eh[5], eh[6], eh[7] = 1, 1, 1, 0
    entry = vaddr(CODE_OFF)
    struct.pack_into('<HHIIIIIHHHHHH', eh, 16,
                     2, 40, 1, entry, 52, 0, 0x05000000,
                     52, 32, 1, 40, 0, 0)
    body = bytearray(HDR)
    body[0:52] = eh
    body[52:84] = struct.pack('<IIIIIIII', 1, HDR, pvaddr(), pvaddr(),
                              0, 0, 5, 0x1000)
    body += strings
    body += b'\x00' * (CODE_OFF - len(body))
    body += code
    # p_filesz/p_memsz must cover exactly the bytes that follow p_offset; a
    # value larger than the file makes the kernel's read of the segment fail.
    span = len(body) - HDR
    struct.pack_into('<I', body, 52 + 16, span)     # p_filesz
    struct.pack_into('<I', body, 52 + 20, span)     # p_memsz
    return bytes(body)


def emit(name, mode, **kw):
    strings, code = build(mode, **kw)
    img = elf(strings, code)
    (OUT / name).write_bytes(img)
    (OUT / name).chmod(0o755)
    b64 = base64.b64encode(img).decode()
    (OUT / (name + '.b64')).write_text(b64)
    print('%-16s %5d B  md5 %s  b64 %d chars'
          % (name, len(img), hashlib.md5(img).hexdigest(), len(b64)))
    return b64


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] in ('dump', 'poke'):
        mode = sys.argv[1]
        off = int(sys.argv[2], 0)
        length = int(sys.argv[3], 0)
        outp = sys.argv[4].encode() if len(sys.argv) > 4 else b'/setting/dump.bin\x00'
        dev = sys.argv[5].encode() if len(sys.argv) > 5 else b'/dev/stream\x00'
        pat = int(sys.argv[6], 0) if len(sys.argv) > 6 else 0xFF
        emit('h_%s.bin' % mode, mode, offset=off, length=length,
             path=outp, dev=dev, pattern=pat)
    else:
        emit('h_ok.bin', 'ok')
