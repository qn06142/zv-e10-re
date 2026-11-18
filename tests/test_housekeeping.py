"""Regression cases for evidence tampering, escaping paths and artifact policy."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    "check_research", Path(__file__).resolve().parents[1] / "scripts/check_research.py"
)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


class EvidenceChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "capture.txt").write_bytes(b"captured evidence\n")
        self.row = {
            "path": "capture.txt", "bytes": 18,
            "sha256": hashlib.sha256(b"captured evidence\n").hexdigest(),
        }

    def test_exact_evidence(self):
        checks.check_identity(self.root, self.row)

    def test_tampered_bytes(self):
        (self.root / "capture.txt").write_bytes(b"modified evidence\n")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            checks.check_identity(self.root, self.row)

    def test_wrong_size(self):
        with self.assertRaisesRegex(ValueError, "Size mismatch"):
            checks.check_identity(self.root, dict(self.row, bytes=19))

    def test_source_identity_survives_checkout_line_endings(self):
        (self.root / "capture.txt").write_bytes(b"captured evidence\r\n")
        row = dict(self.row, hash_mode="lf-normalized")
        del row["bytes"]
        checks.check_identity(self.root, row)

    def test_escaping_paths(self):
        for name in ("../capture.txt", "/capture.txt", "C:/capture.txt", "a/../../capture.txt"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                checks.repository_file(self.root, name)

    def test_duplicate_manifest_entry(self):
        directory = self.root / "research/firmware/evidence/session"
        directory.mkdir(parents=True)
        (directory / "manifest.json").write_text(json.dumps({"files": [self.row, self.row]}))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            checks.check_evidence(self.root)

    def test_generated_artifact_policy(self):
        for name in ("captures/session/frame.raw", "work/source.c", "research/a/test.exe", "bin/a.so"):
            self.assertTrue(checks.forbidden_artifact(name), name)
        for name in ("captures/session/summary.json", "research/a/source.c", "bin/a/README.md"):
            self.assertFalse(checks.forbidden_artifact(name), name)


if __name__ == "__main__":
    unittest.main()
