"""Dump ALL ZV-E10 flash partitions: chunked dd -> /tmp staging -> pmca pull.

The tty is far too slow for bulk data (~12 B/chunk) and pmca's readFile chokes
on block devices, so for each partition we:
   dd if=<part> of=/tmp/_d.bin bs=512 skip=<blk> count=<blk>  (on-camera, 1.6MB/s)
   readFile('/tmp/_d.bin')                                    (bulk protocol)
   rm /tmp/_d.bin
and append each chunk to the local file. Resumes: an existing local file is
kept and we continue from its current size.

usage: zve10_dumpall.py [name=dev:size ...]   (defaults to the full table)
"""
import sys, os, time, re, hashlib
import senser_fix  # noqa: F401  -- fixes 0x8000 payload loss on PID 0x0336
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend

OUTDIR = os.environ.get("ZVE10_OUTDIR", "dumps")
# Throughput notes: the bottleneck is NOT the USB link, it's tty round-trips --
# every shell command costs a ~1.5s silence timeout in pump(). So use BIG chunks
# and as few commands per chunk as possible. dd runs ~1.6MB/s on-camera and
# SenserMaxSize is 0x100000, but readFile happily streams far more.
# /log (nflasha11, 500MB) is the staging area -- /tmp is only 12MB.
CHUNK  = int(os.environ.get("ZVE10_CHUNK", 128 * 1024 * 1024))
STAGE  = os.environ.get("ZVE10_STAGE", "/log/_d.bin")

# Partitions that HOST a staging area -- dumping these while staging into them
# would write into the very partition being read. Stage elsewhere for these.
STAGE_CONFLICT = {
    "/dev/nflasha11": ("/tmp/_d.bin", 8 * 1024 * 1024),   # /log  -> stage in /tmp (12MB)
    "/dev/nflasha10": ("/log/_d.bin", 128 * 1024 * 1024), # /tmp  -> stage in /log
}

# name, device, size in bytes (from /proc/partitions, blocks*1024)
TABLE = [
    ("nflasha7_rootfs",   "/dev/nflasha7",     8192 * 1024),
    ("nflashaB0_exbl",    "/dev/nflashaB0",    2048 * 1024),
    ("nflashaB1",         "/dev/nflashaB1",    2048 * 1024),
    ("nflasha1",          "/dev/nflasha1",     8128 * 1024),
    ("nflasha2_setting",  "/dev/nflasha2",    20480 * 1024),
    ("nflasha3_system",   "/dev/nflasha3",    49152 * 1024),
    ("nflasha4_cmmex",    "/dev/nflasha4",    12288 * 1024),
    ("nflasha5_wbi1",     "/dev/nflasha5",    61440 * 1024),
    ("nflasha6",          "/dev/nflasha6",    16384 * 1024),
    ("nflasha10_tmp",     "/dev/nflasha10",   12288 * 1024),
    ("nflasha12_cert",    "/dev/nflasha12",   40960 * 1024),
    ("nflasha13",         "/dev/nflasha13",    4096 * 1024),
    ("nflasha16",         "/dev/nflasha16",  143360 * 1024),
    ("nflasha17",         "/dev/nflasha17",  102400 * 1024),
    ("nflasha18_lens",    "/dev/nflasha18",   20480 * 1024),
    ("nflasha23",         "/dev/nflasha23",   65536 * 1024),
    ("nflasha15_usr",     "/dev/nflasha15",  307200 * 1024),
    ("nflasha11_log",     "/dev/nflasha11",  512000 * 1024),
]

def pump(raw, idle=1.0, hard=180.0):
    buf, last, end = b"", time.time(), time.time() + hard
    while time.time() < end:
        d = raw.readTerminal()
        if d:
            buf += d; last = time.time()
        elif time.time() - last > idle:
            break
        else:
            time.sleep(0.01)
    return buf.decode("latin1")

def sh(raw, cmd, idle=1.0, hard=180.0, until=None):
    """Send a command and drain output.

    `until`: a regex string -- keep reading until it appears (or `hard` elapses)
    instead of giving up after `idle` seconds of silence. Essential for long
    on-camera work like a 128MB dd, where the shell is quiet for minutes before
    the result marker shows up.
    """
    raw.writeTerminal(cmd.encode("latin1") + b"\n")
    if until is None:
        return pump(raw, idle, hard)
    pat, buf, end = re.compile(until), "", time.time() + hard
    while time.time() < end:
        buf += pump(raw, idle, min(15.0, max(1.0, end - time.time())))
        if pat.search(buf):
            break
    return buf

def complete(dev):
    SenserPlatformBackend(dev).start()
    raw = dev.dev
    dev.setTerminalEnable(False); dev.setTerminalEnable(True)
    pump(raw, 1.0, 5.0)
    os.makedirs(OUTDIR, exist_ok=True)
    try:
        for name, device, size in TABLE:
            stage, chunk = STAGE_CONFLICT.get(device, (STAGE, CHUNK))
            local = os.path.join(OUTDIR, name + ".bin")
            done = os.path.getsize(local) if os.path.exists(local) else 0
            if done >= size:
                print("[skip] %s already complete (%d B)" % (name, done), flush=True)
                continue
            print("[dump] %s %s  %d B  (resume at %d, stage %s)" % (name, device, size, done, stage), flush=True)
            with open(local, "ab") as f:
                while done < size:
                    n = min(chunk, size - done)
                    # ONE round-trip: dd the chunk, then emit its size+md5 between
                    # markers. dd's own completion gates the md5 (sequential shell),
                    # so no separate size-polling is needed.
                    t0 = time.time()
                    r = sh(raw, "dd if=%s of=%s bs=512 skip=%d count=%d 2>/dev/null; "
                                "echo S=$(busybox stat -c %%s %s) M=$(busybox md5sum %s | busybox cut -d' ' -f1)"
                                % (device, stage, done // 512, n // 512, stage, stage),
                           idle=1.0, hard=900.0, until=r"S=\d+\s+M=[0-9a-f]{32}")
                    mi = re.search(r"S=(\d+)\s+M=([0-9a-f]{32})", r)
                    if not mi:
                        print("   ! no S=/M= marker (dd failed?), stopping: %r" % r[-120:], flush=True); break
                    cam_size, cam_md5 = int(mi.group(1)), mi.group(2)
                    if cam_size < n:
                        print("   ! staged only %d < %d, stopping" % (cam_size, n), flush=True); break
                    tdd = time.time()
                    try:
                        import io
                        buf = io.BytesIO()
                        dev.readFile(stage, buf)
                        data = buf.getvalue()
                    except Exception as e:
                        print("   ! pull failed at %d: %r" % (done, e), flush=True); break
                    if len(data) < n:
                        print("   ! short pull %d < %d at %d, stopping (resumable)" % (len(data), n, done), flush=True)
                        if data: f.write(data); f.flush(); done += len(data)
                        break
                    if hashlib.md5(data[:n]).hexdigest() != cam_md5:
                        print("   ! MD5 MISMATCH at %d (host %s vs cam %s), stopping"
                              % (done, hashlib.md5(data[:n]).hexdigest(), cam_md5), flush=True)
                        break
                    f.write(data[:n]); f.flush()
                    done += n
                    dt = time.time() - t0
                    print("   %d / %d  (%.1f%%)  %.1fMB in %.0fs = %.2f MB/s (dd %.0fs pull %.0fs)"
                          % (done, size, 100.0 * done / size, n / 1e6, dt, n / 1e6 / max(dt, .1),
                             tdd - t0, time.time() - tdd), flush=True)
            sh(raw, "rm -f %s" % stage, idle=0.5, hard=30.0)
            print("   -> %s  %d B" % (local, os.path.getsize(local)), flush=True)
    finally:
        try:
            sh(raw, "rm -f /log/_d.bin /tmp/_d.bin", idle=0.5, hard=15.0)
        except Exception: pass
        dev.setTerminalEnable(False)

def _preflight():
    """Refuse to start if another pmca-re python is already holding the camera.

    Background runs that 'exited' can leave an orphaned child alive (the bash /
    timeout wrapper dies, the python child does not). A stale process keeps the
    USB interface pinned, which both wedges the camera in service mode and
    causes bogus GenericUsbExceptions in the new run.
    """
    import subprocess
    # Exclude ourselves AND our whole process tree -- under bash/timeout the
    # wrapper spawns children, so a bare os.getpid() check sees itself and
    # refuses to start.
    mine = {os.getpid(), os.getppid()}
    try:
        tree = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "$ids=@(%s); $all=@($ids); "
             "1..4 | ForEach-Object { "
             "  $kids = Get-CimInstance Win32_Process | "
             "    Where-Object { $all -contains $_.ParentProcessId } | "
             "    ForEach-Object { $_.ProcessId }; "
             "  $all = @($all + $kids | Sort-Object -Unique) }; "
             "$all -join ' '" % ",".join(str(p) for p in mine)],
            capture_output=True, text=True, timeout=30).stdout
        mine |= {int(x) for x in tree.split() if x.strip().isdigit()}
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "Get-Process python* -ErrorAction SilentlyContinue | "
             "Where-Object { $_.Path -like '*pmca-re*' } | "
             "ForEach-Object { $_.Id }"],
            capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return
    others = [int(x) for x in out.split() if x.strip().isdigit() and int(x) not in mine]
    if others:
        sys.exit("REFUSING TO START: pmca-re python already running (PID %s).\n"
                 "It is holding the camera's USB session. Kill it first:\n"
                 "  powershell.exe -Command \"Stop-Process -Id %s -Force\""
                 % (others, ",".join(map(str, others))))


if __name__ == "__main__":
    _preflight()
    senserShellCommand(complete=complete)
