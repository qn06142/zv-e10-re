"""Read a value from a physical address on the camera and print it.

Built for the ldec scanout chain.  Static analysis of the ioctl handler at
VA 0x828B2000 (PA 0x028B2000) shows the scanout handoff:

    0x828B217A  add.w r4, r7, #0x13c0 ; driver private data + 0x13c0
    0x828B2180  adds r4, #8          ; -> r7 + 0x13c8
    0x828B2184  ldrd r2, r3, [r4]    ; 8-byte POINTER PAIR (addr, maybe flags)
    0x828B2188  bl   #0x828B0344     ; handed to the DMA engine

r7 came from `ldr r7, [r6, #0x34]`, i.e. the driver's private data block.  So
if we can find that private block we can read the live scanout pointer instead
of guessing field layouts.

`r6` is the device object; the object at PA 0x028B2000 had 0xFFFFFFFF at
+0x28 in s4's descriptor, but s4 is the USER-side descriptor, not necessarily
this object.  So: read PA 0x028B2000 + 0x34 and see whether it yields a sane
kernel pointer.

This helper reads 4 words at a physical offset and writes them to a file, so
one camera round-trip probes several offsets at once.  Written in the same
Keystone/ELF scheme as arm_helper.py, reusing its layout rules.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import arm_helper as A                                                    # noqa: E402

NR_OPEN, NR_READ, NR_WRITE, NR_LSEEK, NR_EXIT = 5, 3, 4, 19, 1
O_RDONLY, O_WRONLY, O_CREAT, O_TRUNC = 0, 1, 64, 512

# (physical address, word count) probes, from a command-line-ish table
PROBES = [
    (0x028B2000 + 0x34, 4),      # driver priv pointer, per ldr r7,[r6,#0x34]
    (0x028B2000 + 0x00, 8),      # head of the device object
    (0x0297E300 + 0x00, 4),      # the 2 MB allocation we already read
]


def build(probes, dev=b'/dev/mem\x00', out=b'/setting/probe.bin\x00'):
    b = A.Builder()
    b.emit('start:')
    a_dev = b.put_str(dev)
    a_out = b.put_str(out)

    # out = open(out, O_WRONLY|O_CREAT|O_TRUNC, 0666)
    b.load_addr('r0', a_out)
    b.emit('mov r1, #%d' % (O_WRONLY | O_CREAT | O_TRUNC))
    b.emit('mov r2, #0x1b6')
    b.emit('mov r7, #%d' % NR_OPEN)
    b.emit('svc #0')
    b.emit('cmp r0, #0')
    b.emit('mov r12, r0')
    b.emit('blt fail')
    b.emit('mov r6, r12')                     # r6 = out fd

    # fd = open("/dev/mem", O_RDONLY)
    b.load_addr('r0', a_dev)
    b.emit('mov r1, #%d' % O_RDONLY)
    b.emit('mov r2, #0')
    b.emit('mov r7, #%d' % NR_OPEN)
    b.emit('svc #0')
    b.emit('cmp r0, #0')
    b.emit('blt fail')
    b.emit('mov r5, r0')                      # r5 = mem fd

    # Stack frame.  NOTE: do NOT use r11/fp for scratch -- it is the frame
    # pointer, and letting memcpy clobber it corrupted the saved frame and
    # faulted on return (rc=139, em_get_callstack from the kernel).
    #
    # This is the ONLY sp allocation.  An earlier version also had a
    # `sub sp, sp, #96` here which survived an edit and left TWO
    # allocations in the generated code, so the real frame was 0x100 and every
    # offset computed against 0x60 was wrong.  arm_stack_sim.py now flags any
    # second `sub sp`.
    #
    # Fixed-size slots.  The earlier layout assumed a uniform stride and
    # computed data offsets as 16*(idx+1) while the probes were NOT uniform
    # (4, 8 and 4 words), so probe 1's 32 bytes ran from sp+0x50 to sp+0x70 in
    # a 0x60 frame -- overwriting the saved return address.  memcpy also
    # destroys r2, so `add sl, sl, r2` silently added 0.
    #
    # Fix: every probe gets its own fixed SLOT, the frame is sized from that,
    # each probe reads AT MOST 16 bytes, and the copy length is recomputed
    # after the call rather than carried in a clobbered register.
    SLOT = 32
    FRAME = 32 * len(probes) + 64

    b.emit('sub sp, sp, #%d' % FRAME)
    b.emit('add r9, sp, #%d' % (32 * len(probes)))    # accumulator above rc area
    for idx, (addr, count) in enumerate(probes):
        lbl = 'next%d' % idx
        nbytes = min(count * 4, 16)                    # never exceed the slot
        b.emit('add r12, r9, #%d' % (idx * SLOT))      # this probe's slot
        b.emit('str r0, [r12]')                        # rc from open(/dev/mem)
        # lseek(fd, offset, SEEK_SET) -- syscall 19, plain 32-bit off_t.
        #
        # _llseek(140) was tried first and SILENTLY did nothing: rc came back 0
        # but the file offset never moved, so read() kept returning byte 0 of
        # /dev/mem's view -- which is the start of my own ELF, and that is how
        # "    startTime" and " startEvent -\n" turned up where driver code
        # should have been.  Those are this binary's own path strings.
        #
        # So: plain lseek, and CHECK the result is the offset we asked for
        # rather than trusting rc == 0.
        b.emit('mov r0, r5')
        b.set_imm('r1', addr)
        b.emit('mov r2, #0')                           # SEEK_SET
        b.emit('mov r7, #%d' % NR_LSEEK)
        b.emit('svc #0')
        b.emit('str r0, [r12, #4]')                    # rc of lseek
        b.emit('cmp r0, #0')
        b.emit('blt %s' % lbl)
        b.set_imm('r3', addr)
        b.emit('cmp r0, r3')                           # must equal what we asked
        b.emit('bne %s' % lbl)
        b.emit('add r1, sp, #16')                      # read scratch
        b.emit('mov r0, r5')
        b.set_imm('r2', nbytes)
        b.emit('mov r7, #%d' % NR_READ)
        b.emit('svc #0')
        b.emit('str r0, [r12, #8]')                    # rc of read
        b.emit('cmp r0, #0')
        b.emit('blt %s' % lbl)
        b.emit('add r0, r12, #16')                     # dst = slot + 16
        b.emit('add r1, sp, #16')                      # src = scratch
        b.set_imm('r2', nbytes)                        # len (recomputed, not kept)
        b.emit('bl memcpy')
        b.emit('b %s' % lbl)
        b.emit('%s:' % lbl)

    # write(out, accumulator, FRAME_of_accumulator) -- the total is now a
    # compile-time constant (32 per probe), so nothing depends on a register
    # that a call clobbered.
    b.emit('mov r0, r6')
    b.emit('add r1, sp, #%d' % (32 * len(probes)))
    b.set_imm('r2', 32 * len(probes))
    b.emit('mov r7, #%d' % NR_WRITE)
    b.emit('svc #0')
    b.emit('b done')
    b.emit('done:')
    b.emit('mov r0, #0')
    b.emit('mov r7, #%d' % NR_EXIT)
    b.emit('svc #0')

    # memcpy: r0=dst r1=src r2=len
    b.emit('memcpy:')
    b.emit('cmp r2, #0')
    b.emit('beq memcpy_done')
    b.emit('ldrb r3, [r1], #1')
    b.emit('strb r3, [r0], #1')
    b.emit('subs r2, r2, #1')
    b.emit('bne memcpy')
    b.emit('memcpy_done:')
    b.emit('bx lr')

    b.emit('fail:')
    b.emit('mov r0, #1')
    b.emit('mov r7, #%d' % NR_EXIT)
    b.emit('svc #0')
    return b.strings, b.assemble()


if __name__ == '__main__':
    strings, code = build(PROBES)
    img = A.elf(strings, code)
    out = A.OUT / 'h_probe.bin'
    out.write_bytes(img)
    import base64, hashlib
    b64 = base64.b64encode(img).decode()
    (A.OUT / 'h_probe.bin.b64').write_text(b64)
    print('h_probe.bin  %d B  md5 %s  b64 %d chars'
          % (len(img), hashlib.md5(img).hexdigest(), len(b64)))
    for a, c in PROBES:
        print('   probe PA 0x%08x  x%d words' % (a, c))
    print('   total %d bytes' % (sum(c for _, c in PROBES) * 4))
