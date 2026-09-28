"""Probe the ldec ioctl interface from our own code on the camera.

This is the pivot away from patching av-cam.bin.  /proc/kallsyms gives the
authoritative symbol table, so there is no more guessing at addresses from
descriptor fields:

    5f00a2e8 t ldec_ioctl          <- the display driver's ioctl entry
    5f00a03c T boss_lld_get_base_addr_ldec
    5f00afbc T boss_hw_ldec_set
    5f00a028 t ldec_resume

/dev/ldec is crwxrwxrwx, so we can open it and issue ioctls directly.  The
driver validates its own arguments, which is exactly why this is the safe
route: we are using the legitimate control path, not fabricating VDF interface
objects in userspace.

STAGING IS ON THE SD CARD, NOT /setting.  /setting is a live vfat partition
the camera writes during normal operation; leaving binaries and dumps there
risks filling it or tripping a write check.  The card is mounted at
/tmp_bt/sd (a tmpfs mountpoint over a mknod'd block node, 250:11) and the
helper plus its output live under /tmp_bt/sd/re.  Both the binary and its
output are written there by default.

Strategy, in order, stopping at the first that yields information:

  1. open /dev/ldec, report the fd
  2. ioctl(fd, <candidate>, 0) and report each return.  A driver that does not
     recognise a command returns a specific errno, which distinguishes "wrong
     number" from "right number, bad argument" -- that distinction is what lets
     the real ioctl encoding be discovered without the source.

Every result is written to a file so nothing depends on stdout.

Usage: arm_ioctl.py [outpath] [binpath]
"""
import base64
import hashlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import arm_helper as A                                                    # noqa: E402

NR_OPEN, NR_CLOSE, NR_WRITE, NR_IOCTL, NR_EXIT = 5, 6, 4, 54, 1
O_RDWR = 2
O_WRONLY, O_CREAT, O_TRUNC = 1, 64, 512

# SD card staging, per docs: /tmp_bt/sd is the mountpoint and /re is ours.
CARD = '/tmp_bt/sd/re'
DEFAULT_OUT = CARD + '/ioctl.bin'
DEFAULT_BIN = CARD + '/h_ioctl.bin'

DEV = b'/dev/ldec\x00'

# Command space discovered empirically.  The first sweep of _IOC encodings
# returned -EINVAL for all 39 of them, which is what a driver returns for an
# ioctl it does not implement -- so ldec does NOT use _IOC(dir,type,nr,size).
#
# But two small integers behaved differently, which is the useful signal:
#     cmd 1 -> -EIO     (5)    driver got somewhere, then failed
#     cmd 2 -> -EFAULT  (14)   driver TRIED TO READ OUR ARGUMENT
# -EFAULT is the important one: the command takes a pointer, and passing NULL
# made the driver fault on it.  So ldec_ioctl dispatches on a small integer
# command, and commands 1 and 2 are real.  Sweep 0..63 with a valid argument
# buffer so a recognised command can make progress instead of faulting.
CANDS = list(range(0, 64))


def build(outpath):
    b = A.Builder()
    b.emit('start:')
    a_dev = b.put_str(DEV)
    a_out = b.put_str(outpath.encode() + b'\x00')

    # out = open(OUT, WRONLY|CREAT|TRUNC, 0666)
    b.load_addr('r0', a_out)
    b.emit('mov r1, #%d' % (O_WRONLY | O_CREAT | O_TRUNC))
    b.emit('mov r2, #0x1b6')
    b.emit('mov r7, #%d' % NR_OPEN)
    b.emit('svc #0')
    b.emit('cmp r0, #0')
    b.emit('mov r12, r0')
    b.emit('blt fail')
    b.emit('mov r6, r12')                       # r6 = out fd

    # fd = open("/dev/ldec", O_RDWR)
    b.load_addr('r0', a_dev)
    b.emit('mov r1, #%d' % O_RDWR)
    b.emit('mov r2, #0')
    b.emit('mov r7, #%d' % NR_OPEN)
    b.emit('svc #0')
    b.emit('cmp r0, #0')
    b.emit('mov r9, r0')                        # r9 = dev fd (may be negative)
    b.emit('str r0, [sp, #0]')                  # record the open result
    b.emit('add sp, sp, #4')

    # accumulator, then the zeroed argument buffer above it
    ARGSZ = 256
    ACCSZ = 16 * len(CANDS)
    b.emit('sub sp, sp, #%d' % (ACCSZ + ARGSZ + 32))
    b.emit('add r8, sp, #0')                     # r8 = accumulator
    # Zero the argument buffer with a simple counted loop so a recognised
    # command sees inert data rather than stack garbage.  The bound is kept in
    # a register and decremented: `add rX, rX, #-1028` is not encodable
    # (12-bit immediate range), which is the same trap as the page-offset case.
    b.emit('add r4, sp, #%d' % ACCSZ)            # r4 = arg buffer
    b.emit('mov r5, #0')
    b.set_imm('r6', ARGSZ)                       # bytes remaining
    b.emit('clrloop:')
    b.emit('str r5, [r4], #4')
    b.emit('adds r4, r4, #4')
    b.emit('subs r6, r6, #4')
    b.emit('bne clrloop')

    for idx, cmd in enumerate(CANDS):
        lbl = 'n%d' % idx
        b.emit('add r12, r8, #%d' % (16 * idx))
        b.emit('str r9, [r12]')                  # dev fd for this slot
        # Pass a REAL argument buffer, not NULL.  Command 2 returned -EFAULT
        # with a NULL arg, which means the driver dereferences it; a valid
        # buffer lets a recognised command make progress.  256 zero bytes is
        # a safe, obviously-inert argument.
        b.set_imm('r1', cmd)
        b.emit('mov r0, r9')
        b.emit('add r2, sp, #%d' % ACCSZ)         # arg = our zeroed buffer
        b.emit('mov r3, #0')
        b.emit('mov r7, #%d' % NR_IOCTL)
        b.emit('svc #0')
        b.emit('str r0, [r12, #4]')              # ioctl return
        b.emit('b %s' % lbl)
        b.emit('%s:' % lbl)

    # write(out, acc, 16*len(CANDS))
    b.emit('mov r0, r6')
    b.emit('mov r1, r8')
    b.set_imm('r2', 16 * len(CANDS))
    b.emit('mov r7, #%d' % NR_WRITE)
    b.emit('svc #0')
    b.emit('b done')
    b.emit('done:')
    b.emit('mov r0, #0')
    b.emit('mov r7, #%d' % NR_EXIT)
    b.emit('svc #0')
    b.emit('fail:')
    b.emit('mov r0, #1')
    b.emit('mov r7, #%d' % NR_EXIT)
    b.emit('svc #0')
    return b.strings, b.assemble()


if __name__ == '__main__':
    # argv[1] is the CAMERA-side output path (POSIX, on the SD card).
    # argv[2] is the PC-side path to write the built binary to.  These are
    # deliberately different namespaces: passing the camera path as the build
    # path made Python treat "/tmp_bt/sd/re/h_ioctl.bin" as a Windows path and
    # create a junk tree in the drive root.
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    pcpath = sys.argv[2] if len(sys.argv) > 2 else str(A.OUT / 'h_ioctl.bin')
    strings, code = build(out)
    img = A.elf(strings, code)
    pc = Path(pcpath)
    pc.parent.mkdir(parents=True, exist_ok=True)
    pc.write_bytes(img)
    b64 = base64.b64encode(img).decode()
    (A.OUT / (pc.name + '.b64')).write_text(b64)
    print('%-34s %5d B  md5 %s' % (pc, len(img), hashlib.md5(img).hexdigest()))
    print('  camera-side output : %s' % out)
    print('  camera-side binary : %s' % (CARD + '/' + pc.name))
    print('  b64 for transfer   : %d chars' % len(b64))
    print('  sweeping %d ioctl encodings' % len(CANDS))
    print('  ARM _IOC: (dir<<30)|(size<<16)|(type<<8)|nr, dir 1=W 2=R 3=RW')
