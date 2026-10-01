"""Capture the RTOS task monitor trace from the live camera, and keep it.

``/proc/tmonitor`` is the proc interface of the kernel module configured by the
command-line parameters

    tmonitor.addr=0xF00000 tmonitor.size=0x8000 tmonitor.mask=0

Reading it yields a scheduler trace of the RTOS side of the system: every task
with its state, wait channel and priority, plus a per-module task profile and an
IRQ hot-spot profile.  Three record forms::

    [ t ] -sched next:2016 < prev:1944 state:2 wchan:trcv_mbf+238(5f4e006c) \
                             task:liro-kliro_66 cpu:2 prio:147
    [ t ] -profile user CPM::JudPrm cpu:0
    [ t ] -profile user irq:84,7 cpu:1

Two things make this worth having.  The wait channels carry **kernel addresses**
for symbols that were previously only names -- including ``osal_rcv_msg_tmo`` and
``osal_wai_sem_tmo``, the RTOS message-bus primitives.  And the ``profile user``
records carry ``MODULE::task`` names, which is a direct map from ``av-cam.bin``'s
modules to the tasks they run.

**Read the log, never the console.**  The terminal wrapper elides the middle of a
long session; the trace is ~2,000 lines and arrives with a marker like
``[1002 lines omitted, see zve10_shell.log]`` in its place.

**Each read is a fresh live window**, about 46 ms wide. Two reads give different
start timestamps and different counts, so this is not a stored snapshot replayed.
The absolute timestamps are boot-relative and differ per read; only the shape of
the trace repeats.

**Capture it before running anything else.**  ``zve10_shell.py`` opens
``zve10_shell.log`` with mode ``"w"``, so *every* session truncates the previous
one.  An earlier extraction of this trace was summarised from the log and then
destroyed by the next three commands.  ``zve10_shell.log`` is a per-session
scratch file, not a cumulative record.  That is why this tool writes the trace to
a tracked artefact immediately.

    python tmonitor.py              # capture, analyse, write the artefact
    python tmonitor.py --print      # analyse only, write nothing
"""
import pathlib
import re
import subprocess
import sys
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
RETRY = ROOT / "research" / "device" / "zve10_retry.py"
LOG = ROOT / "zve10_shell.log"
OUT = ROOT / "research" / "firmware" / "tmonitor_trace.txt"

# The trace is >25 lines, so it MUST be its own session -- anything noisy before
# it floods the link and drops its output (see im_runtime_manifest.py).
CMD = "busybox cat /proc/tmonitor"

SCHED = re.compile(
    r"^\[\s*([0-9.]+)\s*\]\s*-sched\s+next:(\d+)\s*<\s*prev:(\d+)\s+"
    r"state:(\d+)\s+wchan:(\S+?)\((\S+?)\)\s+task:(\S+)\s+cpu:(\d+)\s+prio:(\d+)")

# A task name may CONTAIN A SPACE -- the trace contains `TC::VD_Seq S` -- so the
# name cannot be \S+.  Anchoring on the trailing `cpu:N` is what makes it safe.
PROFILE = re.compile(r"^\[\s*([0-9.]+)\s*\]\s*-profile\s+user\s+(.+?)\s+cpu:(\d+)")

IRQPROF = re.compile(r"^irq:(\d+),(\d+)$")

# Address-space split between the two kernels.
#
# There are two kernels in the image.  The LiRo kernel -- the RTOS that runs the
# camera's real-time tasks, reachable as `liro-kliro_*` -- is mapped low, and its
# modules with it: `grm_ma` at 0x5f3f0000 and `grm_gles` at 0x5f3f8000 from
# /proc/modules, its own symbols (`trcv_mbf`, `twai_flg`, `tslp_tsk`,
# `osal_*`, `utimer_res_sleep`) at 0x5f0d-0x5f5xxxx.  The Linux kernel is mapped
# above, at 0x60xxxxxx.
#
# The threshold is not fitted to the labels.  Every symbol above it is
# independently recognisable as Linux -- run_ksoftirqd, irq_thread,
# hrtimer_nanosleep, poll_schedule_timeout, futex_wait_queue_me, do_wait,
# n_tty_receive_buf, prepare_to_wait, svc_preempt, hwtimer_schedule_timeout --
# and every symbol below it is LiRo or a LiRo module (hdmi_workqueue,
# osal_rcv_msg_tmo).  The split is clean with no exceptions, which is the check
# that makes the threshold usable rather than arbitrary.  Pinned by
# tests/test_tmonitor.py.
LINUX_KERN_BASE = 0x60000000


def capture():
    """Read /proc/tmonitor and return the trace lines from the session log.

    Returns [] if the camera is not reachable.
    """
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    subprocess.run([str(py), str(RETRY), CMD],
                   capture_output=True, text=True, errors="replace",
                   cwd=str(ROOT))

    if not LOG.exists():
        return []
    text = LOG.read_text(encoding="latin1", errors="replace")

    # Take only this session, and only from the command echo onward, so a stale
    # block cannot be mistaken for a fresh one.
    i = text.rfind("===== $ %s" % CMD)
    if i < 0:
        return []
    return text[i:].splitlines()


def parse(lines):
    """Split trace lines into the three record forms."""
    sched, profiles, other = [], [], []
    for line in lines:
        m = SCHED.match(line.strip())
        if m:
            sched.append({
                "t": float(m.group(1)),
                "next": int(m.group(2)),
                "prev": int(m.group(3)),
                "state": int(m.group(4)),
                "wchan": m.group(5),
                "addr": int(m.group(6), 16),
                "task": m.group(7),
                "cpu": int(m.group(8)),
                "prio": int(m.group(9)),
            })
            continue
        m = PROFILE.match(line.strip())
        if m:
            profiles.append({
                "t": float(m.group(1)),
                "name": m.group(2),
                "cpu": int(m.group(3)),
            })
            continue
        if line.strip():
            other.append(line.strip())
    return sched, profiles, other


def analyse(sched, profiles):
    tasks = Counter(r["task"] for r in sched)
    states = Counter(r["state"] for r in sched)
    cpus = Counter(r["cpu"] for r in sched)

    # wchan symbol -> the (offset, address) pairs it was seen at.  One symbol is
    # normally seen at a handful of call sites, so the *base* address is the
    # minimum of (address - offset); that base is what can be looked up in a
    # symbol table, and it is stable across reads even though the offsets are not.
    seen = defaultdict(set)
    for r in sched:
        sym, _, off = r["wchan"].partition("+")
        try:
            seen[sym].add((int(off, 16), r["addr"]))
        except ValueError:
            seen[sym].add((0, r["addr"]))

    wchans = {}
    for sym, pairs in seen.items():
        base = min(addr - off for off, addr in pairs)
        wchans[sym] = {
            "base": base,
            "pairs": sorted(pairs),
            "offsets": sorted(off for off, _ in pairs),
            "count": sum(1 for r in sched
                         if r["wchan"].partition("+")[0] == sym),
        }

    irq_totals = Counter()
    for p in profiles:
        m = IRQPROF.match(p["name"])
        if m:
            irq_totals[int(m.group(1))] += int(m.group(2))

    module_tasks = sorted({p["name"] for p in profiles
                           if not IRQPROF.match(p["name"])})
    modules = Counter(n.split(":")[0] for n in module_tasks)

    return {
        "tasks": tasks,
        "states": states,
        "cpus": cpus,
        "wchans": wchans,
        "irq": irq_totals,
        "module_tasks": module_tasks,
        "modules": modules,
    }


def report(sched, profiles, other, a):
    print("=== records ===")
    print("  sched          %d" % len(sched))
    print("  profile user   %d" % len(profiles))
    if other:
        print("  unparsed       %d   %s" % (len(other), other[:2]))

    if not sched:
        print("\nno sched records -- camera absent, or /proc/tmonitor empty")
        return

    t0 = min(r["t"] for r in sched)
    t1 = max(r["t"] for r in sched)
    print("\n=== window: t=%.3f .. %.3f s (%.1f ms) ===" % (t0, t1, (t1 - t0) * 1000))

    print("\n=== distinct tasks: %d ===" % len(a["tasks"]))
    for name, n in a["tasks"].most_common(12):
        print("  %-24s %d" % (name, n))

    print("\n=== wchan symbols, with base kernel address and space ===")
    for sym in sorted(a["wchans"], key=lambda s: -a["wchans"][s]["count"]):
        w = a["wchans"][sym]
        space = "linux" if w["base"] >= LINUX_KERN_BASE else "liro"
        offs = ",".join("%x" % o for o in w["offsets"][:4])
        print("  %-26s 0x%08x  %-5s  %4d  off %s"
              % (sym, w["base"], space, w["count"], offs))

    print("\n=== profile: module::task names, %d distinct ===" % len(a["module_tasks"]))
    print("  modules: %s" % ", ".join("%s(%d)" % (m, n)
                                      for m, n in a["modules"].most_common()))
    for n in a["module_tasks"]:
        print("    %s" % n)

    print("\n=== IRQ hot spots, %d distinct ===" % len(a["irq"]))
    for irq, tot in a["irq"].most_common(10):
        print("  irq %-5d total %d" % (irq, tot))


def write_artefact(lines, sched, profiles, other, a):
    hdr = [
        "# /proc/tmonitor trace, Sony ZV-E10 fw 2.02/2.03, service mode.",
        "# Captured from the device by research/firmware/tmonitor.py:",
        "#",
        "#   busybox cat /proc/tmonitor",
        "#",
        "# proc interface of the module configured by the command-line parameters",
        "# tmonitor.addr=0xF00000 tmonitor.size=0x8000 tmonitor.mask=0",
        "#",
        "# mask=0 is NOT 'disabled' -- it means no module is masked out, i.e. the",
        "# most permissive setting. The trace is complete.",
        "#",
        "# Records: %d sched, %d profile-user, %d other" % (
            len(sched), len(profiles), len(other)),
        "# (the raw block below also carries kernel console noise and blank",
        "#  lines; `other` is everything non-blank that is not one of the two",
        "#  record forms)",
        "# window:  t=%.3f .. %.3f s" % (min(r["t"] for r in sched),
                                        max(r["t"] for r in sched)),
        "# tasks:   %d distinct" % len(a["tasks"]),
        "# modules: %d distinct module::task names" % len(a["module_tasks"]),
        "#",
        "# Each read is a fresh ~46 ms live window, so counts vary between reads",
        "# and the absolute timestamps are per-read. The wchan base addresses and",
        "# the module::task names are the stable parts.",
        "#",
        "## RTOS module -> task names",
        "",
    ]
    hdr += ["    %s" % n for n in a["module_tasks"]]
    hdr += [
        "",
        "## wait channels, by symbol",
        "",
        "base = min(address - offset), so it is the symbol's own address and is",
        "stable across reads. Offsets are call sites and do vary.",
        "",
        "| symbol | base address | space | records | call-site offsets |",
        "|---|---:|---|---:|---|",
    ]
    for sym in sorted(a["wchans"], key=lambda s: -a["wchans"][s]["count"]):
        w = a["wchans"][sym]
        space = "linux" if w["base"] >= LINUX_KERN_BASE else "liro"
        hdr.append("| `%s` | `0x%08x` | %s | %d | `%s` |"
                   % (sym, w["base"], space, w["count"],
                      ",".join("0x%x" % o for o in w["offsets"][:8])))

    hdr += [
        "",
        "## IRQ hot spots",
        "",
        "| irq | total |",
        "|---:|---:|",
    ]
    hdr += ["| %d | %d |" % (i, n) for i, n in a["irq"].most_common()]

    hdr += ["", "## raw trace", "", "```"]
    hdr += lines
    hdr += ["```", ""]

    OUT.write_text("\n".join(hdr), encoding="utf-8", newline="\n")
    return OUT


def main():
    lines = capture()
    sched, profiles, other = parse(lines)
    if not sched and not profiles:
        print("camera not reachable -- attach it and enter service mode")
        return 2

    a = analyse(sched, profiles)
    report(sched, profiles, other, a)

    if "--print" not in sys.argv and sched:
        out = write_artefact(lines, sched, profiles, other, a)
        print("\nwrote %s" % out.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
