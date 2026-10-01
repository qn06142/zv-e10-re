"""Tests for the ELF-catalog dependency analysis.

These run without the camera dumps: `elf_catalog.json` is a tracked derived
artefact, so the numbers below are reproducible on a fresh checkout.

The counts are pinned because the docs quote them, and the first version of the
doc figure was wrong.  `313 of 391 shared objects are not DT_NEEDED by anything`
counted two classes of entry that are not shared objects at all:

  * 231 carved fragments recovered from a raw image dump
    (``elf_XXXXXXXX.so`` / ``*_0xXXXXXXXX.bin``), which are not camera files
  * 134 degenerate entries with no imports, no DT_NEEDED and no exports,
    including ``camuser.elf``, whose section table is unreadable

The honest figure is 123 orphans among 165 readable shared objects.
"""
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research" / "firmware"))

import dep_graph


class TestDepGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not dep_graph.CATALOG.exists():
            raise unittest.SkipTest(f"{dep_graph.CATALOG} not found")
        cls.real = dep_graph.load()
        (cls.by_name, cls.carved, cls.degenerate,
         cls.shared, cls.execs, cls.rels) = dep_graph.classify(cls.real)

    def test_catalog_totals(self):
        """The catalog's own totals, so a refresh that changes them is noticed."""
        self.assertEqual(len(self.real), 650)
        self.assertEqual(len(self.by_name), 591)
        self.assertEqual(
            sum(len(v["needed"]) for v in self.real.values()), 2790)

    def test_classes_are_exclusive_and_exhaustive(self):
        """Every basename lands in exactly one class."""
        total = (len(self.carved) + len(self.degenerate) + len(self.shared)
                 + len(self.execs) + len(self.rels))
        self.assertEqual(total, len(self.by_name),
                         "entry classes must partition the basenames")

    def test_carved_fragments_are_not_camera_files(self):
        """The carve class must contain nothing that looks like a real library."""
        self.assertEqual(len(self.carved), 231)
        for name in self.carved:
            self.assertTrue(
                name.startswith("elf_") or "_0x" in name,
                f"{name} should have matched the carve pattern")

    def test_orphan_count_is_123_not_313(self):
        """The documented 313 counted carved and degenerate entries as libraries.

        Regression test for the doc figure: 123 orphans among 165 readable
        shared objects, of which 35 are scenario plugins and 40 are the
        libOnDemandLoader block.
        """
        import collections
        needed_by = collections.Counter()
        for v in self.real.values():
            for n in v["needed"]:
                needed_by[n] += 1

        orphans = [n for n in self.shared if needed_by[n] == 0]
        self.assertEqual(len(self.shared), 165)
        self.assertEqual(len(orphans), 123)

        scen = [n for n in orphans if "SCN" in n]
        on_dem = [n for n in orphans if dep_graph.ON_DEMAND.match(n)]
        self.assertEqual(len(scen), 35)
        self.assertEqual(len(on_dem), 40)
        self.assertEqual(len(orphans) - len(scen) - len(on_dem), 48)

    def test_osal_uipc_dependents_corroborates_the_docs(self):
        """docs/03-binaries.md says 166 dependents; that must still hold."""
        import collections
        needed_by = collections.Counter()
        for v in self.real.values():
            for n in v["needed"]:
                needed_by[n] += 1
        self.assertEqual(needed_by["libosal_uipc.so"], 166)

    def test_degenerate_basename_is_readable_if_any_copy_parsed(self):
        """libObj.so appears twice: an 81,920 B decoy and the real 21 MB file.

        A basename must count as readable when at least one copy yielded
        dynamic information, or the real library is thrown away with the decoy.
        """
        self.assertIn("libObj.so", self.shared)
        sizes = sorted(v["size"] for _p, v in self.by_name["libObj.so"])
        self.assertEqual(sizes, [81920, 21305456])
        good = [v for _p, v in self.by_name["libObj.so"] if v["exp_func"]]
        self.assertEqual(len(good), 1)
        self.assertEqual(good[0]["exp_func"], 1904)

    def test_jiritsu_lead_is_closed_offline(self):
        """libJiritsu.so exists but is degenerate, so it is not a usable lead.

        docs/05-formats.md leaves open that finding a Jiritsu library would give
        real member names.  The file is present in the catalog at 114,688 B but
        carries no imports, no DT_NEEDED and no exports, so nothing can be read
        out of it without the binary.
        """
        self.assertIn("libJiritsu.so", self.degenerate)
        self.assertNotIn("libJiritsu.so", self.shared)


if __name__ == "__main__":
    unittest.main()
