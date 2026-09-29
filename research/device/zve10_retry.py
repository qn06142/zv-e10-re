"""Run a command on the camera, retrying while the USB link drops.

Why this exists
---------------
The service-mode terminal link fails often enough that every command is a
coin flip.  Observed in one session: the device vanished mid-command and the
next invocation reported "No devices found", a backgrounded subshell died with
its parent, and a 4,000-character command was silently discarded while a
4,000-character command in a different form was not.

The failures are not distinguishable from the caller's point of view -- a dropped
link and a command that genuinely produced no output look the same -- so the
only honest policy is to retry the whole thing and say how many attempts it
took.  A command is only accepted as having run when the device was found and
the terminal produced a prompt back, which is what the wrapper checks for.

usage: zve10_retry.py "cmd one" "cmd two" ...
       zve10_retry.py -f commands.txt
"""
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHELL = HERE / 'zve10_shell.py'
PY = HERE.parent.parent / '.venv' / 'Scripts' / 'python.exe'

# "No devices found" is the link being absent rather than a command failing;
# a prompt coming back is the signal that the terminal is alive again.
ALIVE = 'app #'
DEAD = 'No devices found'


def run(cmds, attempts=6, pause=4.0):
    last = ''
    for i in range(1, attempts + 1):
        try:
            p = subprocess.run([str(PY), str(SHELL)] + list(cmds),
                               capture_output=True, text=True,
                               errors='replace', timeout=600)
            last = (p.stdout or '') + (p.stderr or '')
        except subprocess.TimeoutExpired:
            last = 'TIMEOUT'
        if ALIVE in last:
            return last, i
        sys.stderr.write('attempt %d/%d did not complete; retrying in %.0fs\n'
                         % (i, attempts, pause))
        sys.stderr.flush()
        time.sleep(pause)
    return last, -1


def main():
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == '-f':
        cmds = [l.strip() for l in open(a[1])
                if l.strip() and not l.startswith('#')]
    else:
        cmds = a
    if not cmds:
        cmds = ['uname -s']
    out, tries = run(cmds)
    # the kernel banner is noise on every attempt
    body = out.split('--- banner ---')[-1]
    print(body)
    if tries < 0:
        print('\n*** link never came up after every attempt ***')
        sys.exit(2)
    if tries > 1:
        print('\n*** completed on attempt %d ***' % tries)


if __name__ == '__main__':
    main()
