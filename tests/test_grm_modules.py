"""Tests for the grm_* / SUGILITE identification.

These assert the *correction* rather than the original claim.  The docs used to
say "grm_ma.ko and grm_gles.ko are the renderer -- the UI draws through OpenGL
ES", inferred from the letters in a filename.  Reading the modules refutes that:
`grm_gles.ko` is a character-device and MMIO driver for DMP's SUGILITE imaging
coprocessor, and `grm_ma.ko` is a memory allocator for DMP memory.

The test that matters most is ``test_gles_hits_are_not_byte_coincidences``: a
substring search over decoded bytes reported ten files containing "GLES".  Only
one does when the match has to fall inside a printable ASCII run.  Pinning that
difference stops the ten-file version creeping back in.

Skipped without the camera dump on disk.
"""
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research" / "firmware"))

import grm_modules

KMOD = REPO / "dumps" / "camera_2025" / "usr" / "usr" / "kmod"
LIBOBJ = REPO / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"


def _elf(path):
    from elftools.elf.elffile import ELFFile
    return ELFFile(open(path, "rb"))


@unittest.skipUnless(KMOD.is_dir(), "camera dump not present")
class TestGrmModules(unittest.TestCase):
    def test_gles_module_is_a_sugilite_driver(self):
        """.modinfo must name SUGILITE, not anything GL."""
        elf = _elf(KMOD / "grm_gles.ko")
        info = " ".join(grm_modules.modinfo(elf, ".modinfo"))
        self.assertIn("SUGILITE Driver", info)
        self.assertIn("DMP/Sony", info)

    def test_gles_text_is_too_small_to_be_a_gl_implementation(self):
        """6,092 bytes of .text. A GL driver is orders of magnitude larger."""
        elf = _elf(KMOD / "grm_gles.ko")
        text = elf.get_section_by_name(".text").header.sh_size
        self.assertEqual(text, 6092)
        self.assertLess(text, 16 * 1024)

    def test_gles_exposes_the_driver_verbs(self):
        """open/ioctl/mmap/interrupt/clock and register accessors."""
        elf = _elf(KMOD / "grm_gles.ko")
        names = {n for _sz, _b, n in grm_modules.functions(elf)}
        for required in ("sugilite_ioctl", "sugilite_open", "sugilite_mmap_dev",
                         "sugilite_interrupt", "sugilite_clock_up_internal",
                         "sugilite_ioread32", "sugilite_iowrite32",
                         "sugilite_chdev_register"):
            self.assertIn(required, names)

    def test_gles_uses_pcie_bar_remapping(self):
        """BAR remap is a PCIe concept: SUGILITE is a separate chip."""
        elf = _elf(KMOD / "grm_gles.ko")
        sec = elf.get_section_by_name(".rodata.str1.1")
        blob = sec.data() if sec else b""
        self.assertIn(b"bar remap", blob)
        self.assertIn(b"dmpgles2", blob)

    def test_both_modules_come_from_the_guiengine_build(self):
        """Guiengine_161H -- Sony's GUI engine for this platform."""
        for name in ("grm_gles.ko", "grm_ma.ko"):
            elf = _elf(KMOD / name)
            ro = elf.get_section_by_name(".rodata")
            self.assertIn(b"Guiengine_161H", ro.data(), name)

    def test_ma_module_is_an_allocator_not_a_renderer(self):
        """mspace zone allocator plus the DMP memory bridge."""
        elf = _elf(KMOD / "grm_ma.ko")
        names = {n for _sz, _b, n in grm_modules.functions(elf)}
        for required in ("mspace_malloc", "mspace_free", "mspace_memalign",
                         "ma_dmm_open_send_recv", "ma_findbyphys_impl",
                         "ma_cache_flush_impl", "ma_cache_invalidate_impl"):
            self.assertIn(required, names)
        self.assertNotIn("sugilite_ioctl", names)

    def test_ma_exports_its_module_name(self):
        elf = _elf(KMOD / "grm_ma.ko")
        ksym = elf.get_section_by_name("__ksymtab_strings")
        self.assertIn(b"udif_MA_MOD_NAME", ksym.data())


@unittest.skipUnless(LIBOBJ.exists(), "camera dump not present")
class TestLibObjIsTheOnlyConsumer(unittest.TestCase):
    def setUp(self):
        self.texts = [t for _o, t in grm_modules.printable_strings(
            LIBOBJ.read_bytes())]

    def test_libobj_opens_the_sugilite_node(self):
        self.assertIn("/dev/dmpgles2", self.texts)
        self.assertIn("failed to open sugilite device", self.texts)

    def test_libobj_carries_the_dmp_egl_extensions(self):
        found = {m.group() for t in self.texts
                 for m in [grm_modules.DMP_EGL.search(t)] if m}
        for required in ("eglAsyncSwapBuffersDMP", "eglSuspendDMP",
                         "eglResumeDMP", "eglSetHardwareStateDMP"):
            self.assertIn(required, found)

    def test_gles_hits_are_not_byte_coincidences(self):
        """The trap, in three stages, each narrowing.

        * **case-insensitive raw bytes** (PowerShell's ``-match``) reported
          **10 files**. That is simply wrong: it matches lowercase ``gles``
          anywhere, including inside unrelated words.
        * **case-sensitive raw bytes** -> 2 files: ``libObj.so`` and
          ``wpa_supplicant``.
        * **printable ASCII runs** -> still 2, because wpa_supplicant's MIT
          licence text literally contains the capitals "NEGL**IGL**ENCE".
        * **word boundaries** -> **1**: ``libObj.so``.

        Only the last is a real hit. Pinning the chain stops any earlier stage's
        number from being quoted as a finding.
        """
        import re
        token = re.compile(r"\b(GLES|GLES2|EGL|libGL\.)\b")
        libdir = LIBOBJ.parent
        binary_dirs = [libdir, libdir.parent / "bin", libdir.parent / "scenario"]

        ci_hits, raw_hits, run_hits, real_hits = set(), set(), set(), set()
        for d in binary_dirs:
            if not d.is_dir():
                continue
            for p in d.iterdir():
                if not p.is_file():
                    continue
                blob = p.read_bytes()
                if re.search(rb"GLES|EGL", blob, re.IGNORECASE):
                    ci_hits.add(p.name)
                if re.search(rb"GLES|EGL", blob):
                    raw_hits.add(p.name)
                strings = [t for _o, t in grm_modules.printable_strings(blob)]
                if any(re.search(r"GLES|EGL", t) for t in strings):
                    run_hits.add(p.name)
                if any(token.search(t) for t in strings):
                    real_hits.add(p.name)

        self.assertEqual(real_hits, {"libObj.so"})
        self.assertEqual(raw_hits, {"libObj.so", "wpa_supplicant"})
        self.assertEqual(run_hits, raw_hits,
                         "the printable-run filter removes nothing at this stage")
        self.assertLess(len(run_hits), len(ci_hits),
                        "case-insensitive matching is what inflated the count")

    def test_no_linux_library_implements_gles(self):
        """If nothing links GLES/EGL, the renderer cannot be on the A9s."""
        import re
        libdir = LIBOBJ.parent
        offenders = sorted(p.name for p in libdir.glob("*.so*")
                           if re.search(r"GLES|EGL|libGL\.", p.name))
        self.assertEqual(offenders, [])
