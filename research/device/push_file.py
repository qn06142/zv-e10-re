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

BB = '/tmp/busybox'
CTRL_D = b'\x04'
WRITE = 256           # bytes per writeTerminal call (safe under 1024-byte pty limit)
SETTLE = 0.05         # pause between writes, so the pty can drain


def stream_to(raw, remote, payload, label):
    """base64 `payload` into `remote` through the terminal's stdin.

    The decoder is the toolbelt busybox, not the camera's own shell.  That
    distinction is the whole reason the first attempt failed: the camera runs
    BusyBox 1.34.1 ash, but built without a base64 applet, so `base64 -d` was
    "not found" and the 446-character probe was typed into a dead prompt as
    shell commands rather than being decoded.  Anything typed at a prompt that
    is not consuming stdin is executed, so a missing decoder is not a quiet
    failure -- it is a different and much worse one.
    """
    b64 = base64.b64encode(payload)
    lines = [b64[i:i + 76] for i in range(0, len(b64), 76)]
    text = b'\n'.join(lines) + b'\n'
    cmd(raw, 'rm -f %s' % remote)
    cmd(raw, '%s base64 -d > %s' % (BB, remote))
    # Nothing can be checked between starting the decoder and sending Ctrl-D: the
    # shell is blocked inside base64 reading stdin, so any command typed in that
    # window is fed to base64 as data and lands in the output file.  An earlier
    # version tried `ls -l` here to prove the decoder had started, and quietly
    # corrupted its own payload.  The probe and the md5 afterwards are the checks.
    t0 = time.time()
    sent = 0
    for i in range(0, len(text), WRITE):
        raw.writeTerminal(text[i:i + WRITE])
        sent += min(WRITE, len(text) - i)
        time.sleep(SETTLE)
        if sent % (WRITE * 40) < WRITE:
            raw.readTerminal()          # keep the output side drained
            print('  %6.1f%%  %d/%d chars'
                  % (100.0 * sent / len(text), sent, len(text)), flush=True)
    time.sleep(0.5)
    raw.writeTerminal(b'\n')
    time.sleep(0.5)
    raw.writeTerminal(CTRL_D)
    time.sleep(2.0)
    drain(raw, 2.0)
    print('  %s: %d chars in %.0fs' % (label, sent, time.time() - t0))
    return sent


def camera_md5(raw, path, tries=4):
    """read the md5 back, retrying.

    The reply can arrive late: the decoder has only just been interrupted by
    Ctrl-D, and the shell needs a moment to unwind before it will run anything
    else.  Asking once and reporting "no md5" conflates a slow reply with a
    failed transfer, so it asks again and prints whatever came back either way.
    """
    for i in range(tries):
        out = cmd(raw, '%s md5sum %s' % (BB, path), 2.5)
        txt = out.decode('latin1', 'replace') if isinstance(out, bytes) else str(out)
        for tok in txt.split():
            if len(tok) == 32 and all(c in '0123456789abcdef' for c in tok):
                return tok
        print('  md5 attempt %d got no hash; terminal said: %r'
              % (i + 1, txt[:200]))
    return None


def drain(raw, seconds=0.4, extend=0.6):
    """read until quiet, and RETURN what came back.

    The first version of this function read and discarded, and fell off the end
    returning None.  Every caller that parsed the result therefore saw the
    string 'None' and concluded the transfer had failed, when the bytes had in
    fact arrived correctly -- the same 512-byte payload verified exactly when
    the equivalent loop in diag_stream.py was written to accumulate.  Silently
    dropping the evidence is worse than the bug it hid.
    """
    buf = b''
    end = time.time() + seconds
    while time.time() < end:
        d = raw.readTerminal()
        if d:
            buf += d
            end = time.time() + extend
        else:
            time.sleep(0.01)
    return buf


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
            # device's output buffer rather than the input one.  stty has to come
            # from the toolbelt: the camera's own ash has neither stty nor
            # base64, and that is what made the first attempt type 446 base64
            # characters at a live prompt as shell commands.
            cmd(raw, '%s stty -echo' % BB)

            # Probe before committing to the real payload.  A decoder that is
            # missing, or a pty that will not take the stream, costs 45 seconds
            # to discover with the small file and an hour with the font.
            probe = bytes(range(256)) * 2
            print('probing the stream with 512 bytes')
            stream_to(raw, remote + '.probe', probe, 'probe')
            got = camera_md5(raw, remote + '.probe')
            cmd(raw, 'rm -f %s' % (remote + '.probe'))
            want_probe = hashlib.md5(probe).hexdigest()
            print('  probe want %s' % want_probe)
            print('  probe got  %s' % got)
            if got != want_probe:
                print('PROBE FAILED -- not streaming the real file')
                return False

            staged = remote + '.xz'
            want_comp = hashlib.md5(comp).hexdigest()
            print('streaming %s (%d bytes, md5 %s)' % (staged, len(comp), want_comp))
            stream_to(raw, staged, comp, 'payload')
            print('checking staged xz md5')
            got_comp = camera_md5(raw, staged)
            print('  xz want %s' % want_comp)
            print('  xz got  %s' % got_comp)
            if got_comp != want_comp:
                print('XZ STAGING FAILED')
                return False
            print('decompressing on the camera')
            cmd(raw, '%s xz -d -f %s' % (BB, staged), 4.0)
            cmd(raw, 'chmod 755 %s' % remote, 1.0)
            print('verifying')
            got = camera_md5(raw, remote)
            print()
            print('want md5 %s' % want)
            print('got  md5 %s' % got)
            if got == want:
                print('MATCH')
            else:
                print('MISMATCH -- the file on the card is not the local file')
            return got == want
        finally:
            dev.setTerminalEnable(False)

    ok = senserShellCommand(complete=go)
    sys.exit(0 if ok else 3)


if __name__ == '__main__':
    main()
