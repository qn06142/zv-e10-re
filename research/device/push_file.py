"""Push a file to the camera by streaming base64 into the terminal's stdin.

Why streaming rather than chunked commands
------------------------------------------
Commands on this link are bounded at about 1,022 characters; a 4,000-character
command is accepted and silently discarded, taking the session with it.  The
font is 614,336 bytes, which base64-encodes to 819,120 characters, so delivering
it as commands would need some 800 of them, each one a chance for the link to
drop.  The string table was flashed with eleven `dd` appends only because a copy
was already sitting on the card; the bytes still had to cross the wire somehow
once, and that step is what this replaces.

The terminal is a pty, so it has a stdin, and stdin is not subject to the
command-length limit.  `base64 -d > FILE` followed by a stream of base64 and a
Ctrl-D moves the whole file in one session.

Compression
-----------
xz takes the font to 43.4% and base64 of that is 355,344 characters rather than
819,120.  The camera has no compressor of its own, but the toolbelt busybox on
the card does, so the stream is `font.ttf.xz` and the camera finishes the job.

What can still go wrong
-----------------------
The pty input buffer is finite, and if the device firmware will not block on a
full buffer the stream is silently truncated.  That is not detectable from this
side except by checking the result, so the md5 is checked afterwards and the
script says so plainly rather than reporting success.  Echo is turned off first,
because a pty echoes what it is sent and 355 KB of echoed base64 would fill the
device's output buffer and wedge the link in the other direction.
"""
import base64
import hashlib
import lzma
import sys
import time
from pathlib import Path

import os as _os
import sys as _sys

_d = _os.path.dirname(_os.path.abspath(__file__))
_sys.path[:0] = [_os.path.normpath(_os.path.join(_d, '..', 'common')),
                 _os.path.normpath(_os.path.join(_d, '..', '..'))]
import senser_fix  # noqa: F401  -- 0x8000 payload loss on PID 0x0336
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend

BB = '/tmp/sd/tools/busybox-armel'
CTRL_D = b'\x04'
WRITE = 3072          # bytes per writeTerminal call
SETTLE = 0.02         # pause between writes, so the pty can drain


def drain(raw, seconds=0.4):
    """read and discard, so the device's output buffer does not back up"""
    end = time.time() + seconds
    while time.time() < end:
        d = raw.readTerminal()
        if not d:
            time.sleep(0.01)


def cmd(raw, c, settle=1.2):
    raw.writeTerminal(c.encode('latin1') + b'\n')
    time.sleep(settle)
    return drain(raw, settle)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) < 2:
        print(__doc__)
        print('usage: push_file.py LOCAL REMOTE')
        sys.exit(1)
    local = Path(args[0])
    remote = args[1]
    if not local.exists():
        print('no such file: %s' % local)
        sys.exit(1)

    data = local.read_bytes()
    want = hashlib.md5(data).hexdigest()
    comp = lzma.compress(data, format=lzma.FORMAT_XZ, preset=6)
    b64 = base64.b64encode(comp)
    # wrap at 76 columns: standard base64, and safe for a line-oriented reader
    lines = [b64[i:i + 76] for i in range(0, len(b64), 76)]
    stream = b'\n'.join(lines) + b'\n'
    print('local   %s' % local)
    print('  %d bytes, md5 %s' % (len(data), want))
    print('  xz %d bytes, base64 %d chars, %d lines'
          % (len(comp), len(b64), len(lines)))

    def go(dev):
        raw = dev.dev
        SenserPlatformBackend(dev).start()
        dev.setTerminalEnable(False)
        dev.setTerminalEnable(True)
        try:
            drain(raw, 3.0)
            raw.writeTerminal(b'\n')
            drain(raw, 1.0)
            # echo off: a pty echoes stdin, and the echoed stream would fill the
            # device's output buffer rather than the input one
            cmd(raw, 'stty -echo')
            staged = remote + '.xz.b64'
            print('staging %s' % staged)
            cmd(raw, 'rm -f %s %s.xz' % (staged, remote))
            cmd(raw, 'base64 -d > %s' % staged)
            print('streaming...')
            t0 = time.time()
            sent = 0
            for i in range(0, len(stream), WRITE):
                raw.writeTerminal(stream[i:i + WRITE])
                sent += min(WRITE, len(stream) - i)
                time.sleep(SETTLE)
                if sent % (WRITE * 40) < WRITE:
                    raw.readTerminal()          # keep the output side drained
                    print('  %6.1f%%  %d/%d chars'
                          % (100.0 * sent / len(stream), sent, len(stream)),
                          flush=True)
            print('  %6.1f%%  %d/%d chars in %.0fs'
                  % (100.0 * sent / len(stream), sent, len(stream),
                     time.time() - t0))
            print('closing stdin (Ctrl-D)')
            raw.writeTerminal(CTRL_D)
            time.sleep(2.0)
            drain(raw, 3.0)
            cmd(raw, 'stty echo')
            print('decoding and decompressing on the camera')
            cmd(raw, '%s base64 -d %s && rm -f %s' % (BB, staged, staged), 3.0)
            cmd(raw, '%s xz -d -k -f %s.xz && rm -f %s.xz' % (BB, remote, remote), 4.0)
            print('verifying')
            out = cmd(raw, '%s md5sum %s' % (BB, remote), 3.0)
            txt = out.decode('latin1', 'replace') if isinstance(out, bytes) else str(out)
            print(txt.strip())
            got = None
            for tok in txt.split():
                if len(tok) == 32 and all(c in '0123456789abcdef' for c in tok):
                    got = tok
                    break
            print()
            print('want md5 %s' % want)
            print('got  md5 %s' % got)
            if got == want:
                print('MATCH')
            else:
                print('MISMATCH -- the font on the card is not the local file')
            return got == want
        finally:
            dev.setTerminalEnable(False)

    ok = senserShellCommand(complete=go)
    sys.exit(0 if ok else 3)


if __name__ == '__main__':
    main()
