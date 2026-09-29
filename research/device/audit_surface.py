"""Audit what the service shell can reach, and keep score.

Why an audit rather than more exploring
---------------------------------------
Three conclusions in this project have now been overturned by measurement rather
than by argument: av-cam.bin was not encrypted, /usr/bin was not read-only
squashfs, and the camera firmware was on this kernel all along rather than on
another CPU.  Each was a claim about the *extent* of something, and each was
wrong in the direction of assuming less was reachable than actually was.

So the remaining risk is not "what else can I find" but "what have I not looked
at".  This walks the reachable surface in named passes and records what each one
covered, so that a gap is a visible gap rather than an absence nobody noticed.

The passes
----------
  mounts      every filesystem the service side can see
  devices     every /dev node, and which are character devices with ioctls
  procs       every process, its exe, and its open descriptors
  kmod        loaded and loadable kernel modules
  commands    every executable, with its usage string where it has one
  plugins     the dlopen-able shared objects and what they export
  network     interfaces, routes, and what is listening

Each pass is run against the camera and its output filed, so the audit is a
record rather than a recollection.
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path(r'C:\Users\qn061\AppData\Local\Temp\opencode\app_res\audit')
OUT.mkdir(parents=True, exist_ok=True)

BB = '/tmp/sd/tools/busybox-armel'

PASSES = {
    'mounts': [
        'cat /proc/mounts',
        'cat /proc/filesystems',
    ],
    'devices': [
        'ls -l /dev/',
        'cat /proc/misc',
    ],
    'procs': [
        'ls /proc/',
        '%s cat /proc/[0-9]*/comm 2>/dev/null | %s sort | %s uniq -c | %s sort -rn'
        % (BB, BB, BB, BB),
        '%s grep -H . /proc/[0-9]*/comm 2>/dev/null | %s wc -l' % (BB, BB),
    ],
    'kmod': [
        'cat /proc/modules',
        'ls /usr/kmod/',
    ],
    'network': [
        '%s ip -o addr' % BB,
        '%s ip route' % BB,
        '%s netstat -lntup 2>/dev/null || %s netstat -lntu' % (BB, BB),
    ],
    'procfs': [
        'ls /proc/osal/',
        'cat /proc/osal/minfo',
        'ls /proc/sys/ 2>/dev/null',
        'ls /proc/irq/ 2>/dev/null',
    ],
}

COMMANDS = None      # filled in from a previous pass


def run(cmds, label):
    import subprocess
    py = HERE.parent.parent / '.venv' / 'Scripts' / 'python.exe'
    p = subprocess.run([str(py), str(HERE / 'zve10_retry.py')] + cmds,
                       capture_output=True, text=True, errors='replace',
                       timeout=900)
    body = (p.stdout or '') + (p.stderr or '')
    body = body.split('--- banner ---')[-1]
    f = OUT / ('%s.txt' % label)
    f.write_text(body, encoding='utf-8', errors='replace')
    n = len([l for l in body.splitlines() if l.strip()])
    print('  %-10s %5d lines -> %s' % (label, n, f.name))
    return body


def main():
    which = sys.argv[1:] or list(PASSES)
    print('audit passes: %s' % ', '.join(which))
    for name in which:
        if name not in PASSES:
            print('no such pass: %s' % name)
            continue
        try:
            run(PASSES[name], name)
        except Exception as e:
            print('  %-10s FAILED: %s' % (name, e))
        time.sleep(1)


if __name__ == '__main__':
    main()
