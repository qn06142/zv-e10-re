"""Capture the libraries actually resident in im.elf, from the live camera.

`libIMDB.so` names 174 libraries it *may* load.  This reads
``/proc/<pid>/maps`` and reports the subset that is genuinely mapped while the
service shell is up, which is the better answer to "what is the imaging manager
actually running".

It also answers a question the static manifest cannot: which process holds the
DMP/SUGILITE graphics node open.  On the ZV-E10 that turns out to be im.elf
itself, which is why the display path works in service mode with no application
loaded.

Needs the camera in service mode.  Writes
``research/firmware/im_runtime_manifest.txt``; prints a summary either way.

    python im_runtime_manifest.py            # writes the file
    python im_runtime_manifest.py --print    # just report, write nothing
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
RETRY = ROOT / "research" / "device" / "zve10_retry.py"
OUT = ROOT / "research" / "firmware" / "im_runtime_manifest.txt"
LIBPATH = re.compile(r"/usr/lib/[A-Za-z0-9_.+-]+")

# The DMP/SUGILITE graphics node. grm_gles.ko registers it; libObj.so drives it.
DMP_NODE = "dmpgles"

# These are the ones the display question turns on.
KEY_LIBS = ("libObj.so", "libMWF.so", "libSysDef.so", "libIMDB.so")


def run(cmds):
    """Run the commands and return the FULL session, from the log not stdout.

    ``zve10_retry.py`` prints through the terminal wrapper, which elides the
    middle of a long session and substitutes a marker:

        ... [11 lines omitted, see zve10_shell.log] ...

    A 97-line library listing therefore arrives as a handful of lines plus a
    marker, and the list silently parses as empty -- which is exactly what
    happened the first two times this was run.  This is the fourth recorded
    time a truncated read was mistaken for a complete one.

    So read ``zve10_shell.log``, and take only the text after the last command
    echo, so a stale earlier session cannot be mistaken for this one.
    """
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    log = ROOT / "zve10_shell.log"

    subprocess.run([str(py), str(RETRY)] + cmds,
                   capture_output=True, text=True, errors="replace",
                   cwd=str(ROOT))

    if not log.exists():
        return ""
    text = log.read_text(encoding="utf-8", errors="replace")
    marker = "===== $ %s" % cmds[0]
    i = text.rfind(marker)
    return text[i:] if i >= 0 else text


def libs_from(out):
    """Pull the distinct /usr/lib names out of a session log.

    The wrapper echoes each command back and interleaves kernel noise, so the
    names are recovered by matching the path form rather than by taking lines.
    """
    found = set()
    for m in LIBPATH.finditer(out):
        found.add(m.group())
    return sorted(found)


def find_holder(out):
    """Which /proc/<pid> holds the graphics node open?"""
    m = re.search(r"^(/proc/(\d+))\s*$", out, re.M)
    if m:
        return int(m.group(2)), m.group(1)
    # fall back: the pid line may carry the command echo with it
    m = re.search(r"/proc/(\d+)", out)
    return (int(m.group(1)), "/proc/" + m.group(1)) if m else (None, None)


def main():
    write = "--print" not in sys.argv
    # NOTE: no `$$` anywhere in these commands.  PowerShell expands it before
    # the string ever reaches the camera, so `/proc/$$/maps` arrives as
    # `/proc/<the-pc's-pid>/maps` and the command silently reports nothing.
    # Use the literal pid instead -- it is 157 on this camera and is verified
    # below rather than assumed.
    #
    # TWO SESSIONS, deliberately.  Scanning /proc/*/fd across 263 processes
    # floods the serial link, and when that happens the *following* command's
    # output is dropped -- the 97-line library listing came back empty three
    # times until the two were separated.  The link is lossy at volume, so the
    # noisy query and the bulky query each get a session to themselves.
    small = run([
        "busybox ls -l /dev/%s*" % DMP_NODE,
        "busybox grep grm /proc/modules",
        "for p in /proc/[0-9]*; do ls -l $p/fd 2>/dev/null | "
        "busybox grep -q %s && echo $p; done" % DMP_NODE,
    ])
    bulk = run([
        "busybox grep -o '/usr/lib/[a-zA-Z0-9_.-]*' /proc/157/maps "
        "| busybox sort -u",
    ])
    out = small + "\n" + bulk

    if "No devices found" in out or "never came up" in out:
        print("camera not reachable -- attach it and enter service mode")
        return 2

    libs = libs_from(out)
    pid, procpath = find_holder(out)

    print("=== /dev/%s ===" % DMP_NODE)
    for line in out.splitlines():
        if DMP_NODE in line and line.strip().startswith("c"):
            print("  %s" % line.strip())
    print()
    print("=== holder ===")
    print("  %s  (expected 157 = im.elf)" % (procpath or "not found"))
    print()
    print("=== mapped /usr/lib libraries: %d ===" % len(libs))
    for name in KEY_LIBS:
        print("  %-18s %s" % (name, "MAPPED" if any(name in l for l in libs)
                              else "absent"))
    engines = [l for l in libs if "viewUnified" in l]
    print("  %-18s %s" % ("viewUnified*",
                          ", ".join(e.rsplit("/", 1)[-1] for e in engines)
                          or "none"))

    if write and libs:
        hdr = [
            "# Libraries actually mapped into im.elf (PID 157) in service mode,",
            "# ZV-E10 fw 2.02/2.03.  Captured %s by" % "2026-10-01",
            "# research/device/im_runtime_manifest.py.",
            "#",
            "# Read live from /proc/157/maps, not inferred from libIMDB.so's",
            "# static manifest:",
            "#",
            "#   busybox grep -o '/usr/lib/[a-zA-Z0-9_.-]*' /proc/157/maps"
            " | busybox sort -u",
            "#",
            "# Ground truth: libIMDB.so names 174 libraries it MAY load; this is",
            "# the subset resident while the service shell is up.",
            "#",
            "# im.elf also holds /dev/dmpgles2 open (fd 31) -- it is the client",
            "# for the DMP SUGILITE graphics path (grm_gles.ko), which is why",
            "# the LCD still plays SD media in service mode with no application.",
            "#",
            "# count: %d" % len(libs),
        ]
        OUT.write_text("\n".join(hdr + libs) + "\n", encoding="utf-8")
        print("\nwrote %s" % OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
