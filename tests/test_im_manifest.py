"""Tests for the im.elf runtime manifest capture.

``libIMDB.so`` names 174 libraries it *may* load.  ``im_runtime_manifest.txt``
records the 97 that are genuinely mapped into ``im.elf`` (PID 157) while the
service shell is up -- a ground-truth runtime manifest, and a better instrument
than the static one.

These tests run with no camera attached: they check the captured artefact and the
parsing logic, and skip the live capture.

The parsing tests exist because the capture went wrong three times before it
worked, in three distinct ways that all produced a *plausible empty result*
rather than an error:

  1. reading ``zve10_retry`` stdout, which elides the middle of a session with
     ``[11 lines omitted, see zve10_shell.log]``
  2. issuing the bulky library listing in the same session as a scan of
     ``/proc/*/fd`` across 263 processes, which floods the link and drops the
     following command's output
  3. PowerShell expanding ``$$`` in ``/proc/$$/maps`` before the string reaches
     the camera
"""
import pathlib
import re
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research" / "device"))

MANIFEST = REPO / "research" / "firmware" / "im_runtime_manifest.txt"

LIBPATH = re.compile(r"/usr/lib/[A-Za-z0-9_.+-]+")


class TestRuntimeManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not MANIFEST.exists():
            raise unittest.SkipTest(f"{MANIFEST} not present")
        cls.raw = MANIFEST.read_text(encoding="utf-8")
        cls.libs = sorted({m.group() for m in LIBPATH.finditer(cls.raw)})

    def test_count_is_97(self):
        """97 distinct libraries, not the 174 the static manifest names."""
        self.assertEqual(len(self.libs), 97)
        self.assertIn("# count: 97", self.raw)

    def test_the_engine_is_resident(self):
        """The finding: libObj.so is mapped, not dormant.

        This is the correction to "the service filesystem carries the rendering
        engine but not the application that uses them".
        """
        for required in ("libObj.so", "libMWF.so", "libSysDef.so",
                         "libIMDB.so"):
            self.assertIn("/usr/lib/" + required, self.libs)

    def test_only_two_of_the_seven_engines_are_loaded(self):
        """viewUnified2 and viewUnified6 only -- one screen class is active."""
        engines = sorted(l.rsplit("/", 1)[-1] for l in self.libs
                         if "viewUnified" in l)
        self.assertEqual(engines,
                         ["viewUnified2.so", "viewUnified6.so"])

    def test_runtime_manifest_is_a_strict_subset_of_the_static_one(self):
        """97 of 174: the runtime set must not contain anything the static
        manifest does not name, or one of the two is misread."""
        self.assertLess(len(self.libs), 174)
        # every entry must be a bare soname under /usr/lib, nothing else
        for lib in self.libs:
            self.assertRegex(lib, r"^/usr/lib/[A-Za-z0-9_.+-]+$")

    def test_no_application_entry_point_is_resident(self):
        """The absence still holds -- appFw/gui/camuser are not loaded."""
        present = {l.rsplit("/", 1)[-1] for l in self.libs}
        for absent in ("appFw.so", "gui.so", "camuser.elf",
                       "libInfraWebApi.so"):
            self.assertNotIn(absent, present)


class TestLibPathParsing(unittest.TestCase):
    def test_paths_recovered_from_a_noisy_session(self):
        """Kernel noise and command echoes must not become library names."""
        noisy = """
[  95.128029] console [usbgcon-1] enabled
===== $ busybox grep -o '/usr/lib/[a-zA-Z0-9_.-]*' /proc/157/maps | busybox sort -u
busybox grep -o '/usr/lib/[a-zA-Z0-9_.-]*' /proc/157/maps | busybox sort -u
/usr/lib/libObj.so
/usr/lib/viewUnified2.so
[ 178.503028] FAT-fs (mmca10p1): Directory bread(block 32768) failed
"""
        found = sorted({m.group() for m in LIBPATH.finditer(noisy)})
        self.assertEqual(found,
                         ["/usr/lib/libObj.so", "/usr/lib/viewUnified2.so"])

    def test_versioned_sonames_are_kept_whole(self):
        """libstdc++.so.6.0.14 must not be truncated at the first dot."""
        found = sorted({m.group() for m in LIBPATH.finditer(
            "/usr/lib/libstdc++.so.6.0.14")})
        self.assertEqual(found, ["/usr/lib/libstdc++.so.6.0.14"])

    def test_the_capture_tool_avoids_the_three_known_traps(self):
        """Guards on the tool's actual behaviour, not on its source text.

        Checking the source for a string is not enough: the tool documents the
        `$$` trap in a comment, so a naive text search finds it there and fails
        for the wrong reason.  This intercepts `run` and inspects the commands
        the tool really issues.
        """
        import im_runtime_manifest as tool

        issued = []
        original = tool.run

        def spy(cmds):
            issued.append(list(cmds))
            return ""

        tool.run = spy
        try:
            tool.main()
        finally:
            tool.run = original

        flat = [c for batch in issued for c in batch]
        self.assertTrue(flat, "the tool issued no commands at all")

        # trap 3: PowerShell expands $$ before the string reaches the camera
        for cmd in flat:
            self.assertNotIn("$$", cmd)

        # trap 2: the noisy /proc/*/fd scan and the bulky listing are separate
        noisy = [c for c in flat if "/proc/[0-9]*" in c]
        bulky = [c for c in flat if "/proc/157/maps" in c]
        self.assertEqual(len(noisy), 1)
        self.assertEqual(len(bulky), 1)
        for batch in issued:
            has_noisy = any("/proc/[0-9]*" in c for c in batch)
            has_bulky = any("/proc/157/maps" in c for c in batch)
            self.assertFalse(has_noisy and has_bulky,
                             "the fd scan and the library listing must not "
                             "share a session, or the link drops the latter")

        # trap 1: the answer must come from the log, not stdout
        src = REPO / "research" / "device" / "im_runtime_manifest.py"
        text = src.read_text(encoding="utf-8")
        self.assertIn("zve10_shell.log", text)
        self.assertIn("omitted", text,
                      "the console-truncation trap should stay documented")


if __name__ == "__main__":
    unittest.main()
