"""Diagnose the stdin stream: send a known blob and show everything that comes back.

push_file.py reports a missing md5 but not what the terminal actually said, and
the two candidate explanations -- the stream not arriving, or the reply not being
captured -- call for opposite fixes.  So this does the smallest possible version
of the sequence and prints the raw bytes after every step.
"""
import base64
import hashlib
import os
import sys
import time

_d = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.normpath(os.path.join(_d, '..', 'common')),
                os.path.normpath(os.path.join(_d, '..', '..'))]
import senser_fix  # noqa: F401
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend

BB = '/tmp/sd/tools/busybox-armel'
REMOTE = '/tmp/sd/_diag.bin'
PAYLOAD = bytes(range(256)) * 2          # 512 bytes, every byte value once twice


def show(raw, tag, seconds=2.0):
    buf = b''
    end = time.time() + seconds
    while time.time() < end:
        d = raw.readTerminal()
        if d:
            buf += d
            end = time.time() + 0.6
        else:
            time.sleep(0.02)
    print('--- %s ---' % tag)
    print(repr(buf.decode('latin1', 'replace'))[:900])
    print()
    return buf


def send(raw, text, tag, seconds=2.0):
    raw.writeTerminal(text)
    return show(raw, tag, seconds)


def go(dev):
    raw = dev.dev
    SenserPlatformBackend(dev).start()
    dev.setTerminalEnable(False)
    dev.setTerminalEnable(True)
    try:
        show(raw, 'banner', 3.0)
        send(raw, b'\n', 'newline')
        send(raw, ('%s stty -echo\n' % BB).encode(), 'stty -echo')
        send(raw, ('rm -f %s\n' % REMOTE).encode(), 'rm')
        send(raw, ('%s base64 -d > %s\n' % (BB, REMOTE)).encode(), 'start decode')
        b64 = base64.b64encode(PAYLOAD)
        lines = [b64[i:i + 76] for i in range(0, len(b64), 76)]
        text = b'\n'.join(lines) + b'\n'
        print('sending %d base64 chars in %d lines' % (len(text), len(lines)))
        raw.writeTerminal(text)
        time.sleep(1.5)
        send(raw, b'\x04', 'Ctrl-D', 3.0)
        send(raw, ('%s md5sum %s\n' % (BB, REMOTE)).encode(), 'md5', 4.0)
        send(raw, ('%s wc -c < %s\n' % (BB, REMOTE)).encode(), 'size', 3.0)
        print('want md5 %s  size %d'
              % (hashlib.md5(PAYLOAD).hexdigest(), len(PAYLOAD)))
        send(raw, ('%s stty echo\n' % BB).encode(), 'stty echo')
        return True
    finally:
        dev.setTerminalEnable(False)


if __name__ == '__main__':
    senserShellCommand(complete=go)
