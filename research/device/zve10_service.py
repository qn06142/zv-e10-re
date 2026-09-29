
"""Drive the ZV-E10 service-mode shell programmatically (pmca's input() prompt
does not work through a piped/PTY stdin, so we feed the parser directly)."""
import sys
from pmca.commands.usb import senserShellCommand
from pmca.platform import CameraShell
from pmca.platform.backend.senser import SenserPlatformBackend
from pmca.shell.parser import ArgParser

CMDS = sys.argv[1:] or ["info"]

def complete(dev):
    shell = CameraShell(SenserPlatformBackend(dev))
    shell.backend.start()
    try:
        for c in CMDS:
            print("\n===== > %s =====" % c, flush=True)
            try:
                p = ArgParser(c)
                if p.available():
                    shell.commands.run(p)
            except Exception as e:
                print("Error: %s" % e)
    finally:
        try: shell.backend.stop()
        except Exception as e: print("stop: %s" % e)

senserShellCommand(complete=complete)
