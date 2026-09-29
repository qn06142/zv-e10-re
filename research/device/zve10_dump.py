"""Dump a ZV-E10 flash partition over the service-mode terminal via base64.

usage: zve10_dump.py <device> <outfile> [max_bytes]
   eg: zve10_dump.py /dev/nflashaB0 dumps/nflashaB0.bin
"""
import sys, os, time, base64, re
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend

DEV = sys.argv[1]
OUT = sys.argv[2]
MAX = int(sys.argv[3]) if len(sys.argv) > 3 else 0
CHUNK = 4096                     # bytes of raw data per dd read

def pump(raw, idle=1.2, hard=25.0):
    buf, last, end = b"", time.time(), time.time() + hard
    while time.time() < end:
        d = raw.readTerminal()
        if d:
            buf += d; last = time.time()
        elif time.time() - last > idle:
            break
        else:
            time.sleep(0.01)
    return buf

def run(raw, cmd, idle=1.2, hard=25.0):
    raw.writeTerminal(cmd.encode("latin1") + b"\n")
    return pump(raw, idle, hard).decode("latin1")

def complete(dev):
    SenserPlatformBackend(dev).start()
    raw = dev.dev
    dev.setTerminalEnable(False); dev.setTerminalEnable(True)
    pump(raw, 1.0, 4.0)
    try:
        size = MAX
        if not size:
            r = run(raw, "busybox blockdev --getsize64 %s" % DEV)
            m = re.search(r"^\s*(\d{2,})\s*$", r, re.M)
            size = int(m.group(1)) if m else 0
            print("size: %s bytes" % (size or "unknown"), flush=True)
        if not size:
            print("could not determine size; pass max_bytes"); return

        os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
        got = 0
        with open(OUT, "wb") as f:
            while got < size:
                n = min(CHUNK, size - got)
                # bs=1 is slow -- use block-aligned reads whenever we can
                aligned = got % 512 == 0 and n % 512 == 0
                bs, skip, cnt = (512, got // 512, n // 512) if aligned else (1, got, n)
                r = run(raw, "dd if=%s bs=%d skip=%d count=%d 2>/dev/null"
                             " | busybox base64 | busybox tr -d '\\n'; echo READY"
                             % (DEV, bs, skip, cnt), idle=1.5, hard=60.0)
                if "READY" not in r:
                    print("no READY marker at offset %d; aborting" % got); break
                body = r.split("READY")[0]
                b64 = "".join(re.findall(r"[A-Za-z0-9+/=]{16,}", body))
                try:
                    data = base64.b64decode(b64 + "=" * (-len(b64) % 4))
                except Exception as e:
                    print("b64 error at %d: %s" % (got, e)); break
                if not data:
                    print("empty chunk at %d; aborting" % got); break
                f.write(data); f.flush()
                got += len(data)
                print("  %d / %d bytes (%.1f%%)" % (got, size, 100.0 * got / size), flush=True)
        print("wrote %s (%d bytes)" % (OUT, got))
    finally:
        dev.setTerminalEnable(False)

if __name__ == "__main__":
    senserShellCommand(complete=complete)
