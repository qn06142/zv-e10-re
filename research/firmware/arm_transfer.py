"""Transfer a built helper to the camera as base64 text, in chunks.

The camera has /bin/busybox, whose `base64 -d` applet is the transport; there
is no push command in zve10_live.py and the SD card is inside the camera.

Chunks are appended with plain `echo` (which may or may not honour -n on this
ash) and then newline-stripped with `tr`, so the concatenation is byte-exact
either way.  md5 is compared on both sides before anything is executed.
"""
import base64
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

D = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera')
CHUNK = 1500


def transfer_cmd(binname, remote='/setting/h.bin'):
    raw = (D / binname).read_bytes()
    md5 = hashlib.md5(raw).hexdigest()
    b64 = base64.b64encode(raw).decode()
    parts = [b64[i:i + CHUNK] for i in range(0, len(b64), CHUNK)]
    lines = [': > /setting/h.b64']
    for p in parts:
        lines.append("echo '%s' >> /setting/h.b64" % p)
    lines.append('tr -d \'\\n\' < /setting/h.b64 > /setting/h.tmp')
    lines.append('busybox base64 -d /setting/h.tmp > %s' % remote)
    lines.append('ls -l %s' % remote)
    lines.append('busybox md5sum %s' % remote)
    return ' ; '.join(lines), md5, len(raw), len(parts)


if __name__ == '__main__':
    name = sys.argv[1] if len(sys.argv) > 1 else 'h_ok.bin'
    cmd, md5, size, nparts = transfer_cmd(name)
    print('binary   %s' % name)
    print('size     %d B' % size)
    print('md5      %s' % md5)
    print('chunks   %d' % nparts)
    print('cmd len  %d chars' % len(cmd))
    Path(D / (name + '.transfer.txt')).write_text(cmd)
    print('\n--- copy the line below into zve10_live.py shell ---')
    print(cmd)
