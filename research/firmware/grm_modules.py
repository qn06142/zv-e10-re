"""Identify the grm_* graphics modules on the ZV-E10.

These are the two kernel modules that the docs had described, from their filenames
alone, as "the renderer -- the UI draws through OpenGL ES".  That was an
inference from the letters `gles` in a module name.  This script reads the
modules and settles it.

What it establishes
-------------------
``grm_gles.ko`` is **not** an OpenGL ES implementation.  It is a character-device
and MMIO driver for DMP's SUGILITE imaging coprocessor, reached over PCIe.  Its
own ``.modinfo`` says so::

    description=SUGILITE Driver
    author=DMP/Sony

and its symbol names give the mechanism away: ``sugilite_ioctl``,
``sugilite_mmap``, ``sugilite_interrupt``, ``sugilite_clock_up_internal``, and
``sugilite_ioread8/16/32`` register accessors.  Its ``.text`` is 6,092 bytes,
which is three orders of magnitude too small to be a GL implementation.

``libObj.so`` is the only userspace consumer.  It opens ``/dev/dmpgles2`` and
carries DMP's EGL extensions (``eglSwapBuffersDMP``, ``eglSuspendDMP``,
``EGL_DMP_display_query``).  So the *API* is GLES2 and the *renderer* is DMP
silicon -- Linux is the GL client, not the GL implementer.

``grm_ma.ko`` is the matching memory allocator: a ``mspace`` zone allocator plus
``ma_dmm_open_send_recv``, ``ma_findbyphys_impl`` and cache flush/invalidate,
which is what lets Linux-side buffers be addressed by the DMP chip.

Run with no arguments::

    python grm_modules.py
"""
import collections
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
KMOD = ROOT / "dumps" / "camera_2025" / "usr" / "usr" / "kmod"
LIBOBJ = ROOT / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

# The EGL/GL entry points DMP adds on top of GLES2.  Their presence is what
# identifies the DMP implementation.
DMP_EGL = re.compile(r"\begl[A-Za-z]*DMP\b")
GLES_EXT = re.compile(r"\b(GLES2?|GL_OES_\w+|EGL_DMP_\w+|EGL_KHR_\w+)\b")


def printable_strings(blob, minlen=4):
    """Yield (offset, text) for printable ASCII runs.

    Required, not cosmetic.  A substring search over the raw decoded bytes
    reports GLES/EGL inside ``iperf`` and inside ``viewUnified2.so``; both are
    byte coincidences in binary data, not text.  Anchoring to printable runs is
    what makes a hit mean something.
    """
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % minlen, blob):
        yield m.start(), m.group().decode("ascii")


def modinfo(elf, section):
    sec = elf.get_section_by_name(section)
    if not sec:
        return []
    return [c.decode("utf-8", "replace").strip()
            for c in sec.data().split(b"\x00") if c.strip()]


def functions(elf):
    st = elf.get_section_by_name(".symtab")
    out = []
    for s in st.iter_symbols():
        if s.name and s.entry.st_info.type == "STT_FUNC":
            out.append((s.entry.st_size, s.entry.st_info.bind, s.name))
    return sorted(out, reverse=True)


def report_module(path):
    from elftools.elf.elffile import ELFFile

    print("=" * 72)
    print(path.name)
    with open(path, "rb") as f:
        elf = ELFFile(f)
        print("  ELF%d %s %s   .text=%d B"
              % (elf.elfclass, elf.header.e_machine, elf.header.e_type,
                 elf.get_section_by_name(".text").header.sh_size))

        info = []
        for line in modinfo(elf, ".modinfo"):
            if line not in info:          # modinfo repeats per object
                info.append(line)
        print("  .modinfo:")
        for line in info:
            print("    %s" % line)

        ksym = elf.get_section_by_name("__ksymtab_strings")
        if ksym:
            names = [c.decode() for c in ksym.data().split(b"\x00") if c]
            print("  exported kernel symbols: %s" % ", ".join(names))

        funcs = functions(elf)
        print("  functions: %d   (top 12 by size)" % len(funcs))
        for sz, bind, name in funcs[:12]:
            print("    %6d B  %-11s %s" % (sz, bind, name))

        for sec in (".rodata", ".rodata.str1.1"):
            s = elf.get_section_by_name(sec)
            if not s:
                continue
            for _off, text in printable_strings(s.data()):
                if re.search(r"sugilite|dmpgles|GPE HW|\.c$", text):
                    print("    [%s] %s" % (sec, text[:96]))


def report_libobj():
    print("=" * 72)
    print("libObj.so -- the only userspace consumer")
    if not LIBOBJ.exists():
        print("  %s not present" % LIBOBJ)
        return
    blob = LIBOBJ.read_bytes()
    texts = list(printable_strings(blob))

    dev = [(o, t) for o, t in texts if t.startswith("/dev/dmp")]
    print("  device nodes opened:")
    for o, t in dev:
        print("    @0x%08x  %s" % (o, t))

    egl = sorted({m.group() for _o, t in texts
                  for m in [DMP_EGL.search(t)] if m})
    ext = sorted({m.group() for _o, t in texts
                  for m in [GLES_EXT.search(t)] if m})
    print("  DMP EGL entry points (%d): %s" % (len(egl), ", ".join(egl)))
    print("  GLES/EGL extensions named (%d):" % len(ext))
    for e in ext[:14]:
        print("    %s" % e)

    gpe = [t for _o, t in texts if "GPE HW" in t or t == "grm_gpe"]
    for t in gpe[:4]:
        print("  %s" % t[:96])

    # A negative worth pinning: nothing in /usr/lib links GLES or EGL, so the
    # GLES2 implementation cannot be a Linux shared object.
    libdir = LIBOBJ.parent
    gles_libs = sorted(p.name for p in libdir.glob("*.so*")
                       if re.search(r"GLES|EGL|libGL\.", p.name))
    print("  libraries in /usr/lib named GLES/EGL/libGL: %d  %s"
          % (len(gles_libs), gles_libs or "(none)"))


def main():
    if not KMOD.is_dir():
        print("%s not present -- attach the SD card dump first" % KMOD)
        return 1
    for name in ("grm_gles.ko", "grm_ma.ko"):
        p = KMOD / name
        if p.exists():
            report_module(p)
        else:
            print("%s not present" % p)
    report_libobj()
    return 0


if __name__ == "__main__":
    sys.exit(main())
