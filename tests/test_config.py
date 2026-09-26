"""Regression tests for retool.config.load.

Both call shapes are covered because the function was broken in both:

  * an explicit path raised UnboundLocalError -- the default was bound to a
    different name inside the `if` branch, so `cfg_path` was never assigned when
    the caller supplied a path;
  * a partial fix then reset the default back to None, so the CLI (which calls
    load(None) unless --config is passed) failed with a TypeError.

`load()` is on the CLI's hot path: every subcommand goes through it.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from retool import config as rcfg     # noqa: E402

REPO = Path(__file__).resolve().parent.parent
REAL = REPO / "reconf.toml"

MINIMAL = """
[engine]
rizin = ""
[target.avcam]
path = "dumps/av-cam.bin"
arch = "arm"
bits = 16
cpu = "cortex"
endian = "little"
runtime_base = 0x635c6000
seeds = [0x28]
"""


class TestConfigLoad(unittest.TestCase):
    def test_default_none_resolves_to_project_config(self):
        """load() with no argument must find reconf.toml, not crash."""
        cfg = rcfg.load()
        self.assertTrue(cfg.root.is_dir())
        self.assertIn("avcam", cfg.targets)

    def test_explicit_path_is_accepted(self):
        """load(path) must not raise -- this is the case that was broken."""
        cfg = rcfg.load(REAL)
        self.assertEqual(cfg.root, REAL.parent)
        self.assertIn("avcam", cfg.targets)

    def test_explicit_path_as_string(self):
        cfg = rcfg.load(str(REAL))
        self.assertIn("avcam", cfg.targets)

    def test_explicit_temp_config(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "reconf.toml"
            p.write_text(MINIMAL, encoding="utf-8")
            cfg = rcfg.load(p)
            t = cfg.targets["avcam"]
            self.assertEqual(t.runtime_base, 0x635C6000)
            self.assertEqual(t.seeds, [0x28])
            self.assertEqual(t.arch, "arm")

    def test_env_var_default(self):
        """RETOOL_CONFIG must be honoured when no path is passed."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "reconf.toml"
            p.write_text(MINIMAL, encoding="utf-8")
            old = os.environ.get("RETOOL_CONFIG")
            os.environ["RETOOL_CONFIG"] = str(p)
            try:
                cfg = rcfg.load()
                self.assertEqual(cfg.root, Path(td).resolve())
            finally:
                if old is None:
                    os.environ.pop("RETOOL_CONFIG", None)
                else:
                    os.environ["RETOOL_CONFIG"] = old

    def test_missing_config_raises_systemexit(self):
        with self.assertRaises(SystemExit):
            rcfg.load(Path("no-such-dir") / "reconf.toml")


if __name__ == "__main__":
    unittest.main(verbosity=2)
