"""Tests for MWF message tables and vocabulary extraction."""
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research" / "firmware"))

from annotate import load, load_segs, v2o


class TestMwfCatalog(unittest.TestCase):
    def test_mwf_core_tables(self):
        """libMWF.so must export base and pin message tables with expected counts."""
        p = REPO / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libMWF.so"
        if not p.exists():
            self.skipTest(f"{p} not found")
        data, f = load(p)
        segs = load_segs(f)

        # m_baseMsgTbl at 0x428b8, 12 records of 8 bytes
        off = v2o(segs, 0x428b8)
        self.assertIsNotNone(off)
        base_recs = []
        for i in range(12):
            rec = data[off + i*8 : off + (i+1)*8]
            mid = int.from_bytes(rec[:4], "little")
            saddr = int.from_bytes(rec[4:], "little")
            soff = v2o(segs, saddr)
            z = data.find(b"\x00", soff)
            base_recs.append((mid, data[soff:z].decode("ascii")))

        self.assertEqual(len(base_recs), 12)
        base_dict = dict(base_recs)
        self.assertEqual(base_dict[0x1002], "MSGID_START_OBJ_CMD")
        self.assertEqual(base_dict[0x1003], "MSGID_STOP_OBJ_CMD")
        self.assertEqual(base_dict[0x1008], "MSGID_RESUME_OBJ_CMD")
        self.assertEqual(base_dict[0x1009], "MSGID_SUSPEND_OBJ_CMD")
        self.assertEqual(base_dict[0x1004], "MSGID_KILL_OBJ_CMD")

        # m_pinMsgTbl at 0x42918, 11 records of 8 bytes
        off = v2o(segs, 0x42918)
        self.assertIsNotNone(off)
        pin_recs = []
        for i in range(11):
            rec = data[off + i*8 : off + (i+1)*8]
            mid = int.from_bytes(rec[:4], "little")
            saddr = int.from_bytes(rec[4:], "little")
            soff = v2o(segs, saddr)
            z = data.find(b"\x00", soff)
            pin_recs.append((mid, data[soff:z].decode("ascii")))

        self.assertEqual(len(pin_recs), 11)
        pin_dict = dict(pin_recs)
        self.assertEqual(pin_dict[0x1000], "MSGID_OPEN")
        self.assertEqual(pin_dict[0x1001], "MSGID_CLOSE")
        self.assertEqual(pin_dict[0x1002], "MSGID_DELIVER")
        self.assertEqual(pin_dict[0x1003], "MSGID_NOTIFY")
        self.assertEqual(pin_dict[0x2000], "MSGID_REQ_OPEN")
        self.assertEqual(pin_dict[0x3000], "MSGID_CONNECT")
        self.assertEqual(pin_dict[0x3001], "MSGID_DISCONNECT")

    def test_apicd_database_table(self):
        """libObj.so must contain the APICD table at 0x13ec720."""
        p = REPO / "dumps" / "engine" / "libObj.so"
        if not p.exists():
            self.skipTest(f"{p} not found")
        data = p.read_bytes()

        mid_0 = int.from_bytes(data[0x13ec720 : 0x13ec724], "little")
        saddr_0 = int.from_bytes(data[0x13ec724 : 0x13ec728], "little")
        z0 = data.find(b"\x00", saddr_0)
        self.assertEqual(mid_0, 0x1000)
        self.assertEqual(data[saddr_0:z0], b"APICD_CREATE_HNDL")

        mid_22 = int.from_bytes(data[0x13ecc78 : 0x13ecc7c], "little")
        saddr_22 = int.from_bytes(data[0x13ecc7c : 0x13ecc80], "little")
        z22 = data.find(b"\x00", saddr_22)
        self.assertEqual(mid_22, 0x1022)
        self.assertEqual(data[saddr_22:z22], b"APICD_GET_CONTENT_PROPERTY")

    def _apicd_records(self, data, stride):
        """Walk the APICD table at a candidate stride. Returns [(id, name)]."""
        out = []
        pos = 0x13EC720
        while pos < 0x13ED800:
            mid = int.from_bytes(data[pos : pos + 4], "little")
            saddr = int.from_bytes(data[pos + 4 : pos + 8], "little")
            if not (0x1000000 <= saddr <= 0x1200000):
                break
            z = data.find(b"\x00", saddr)
            name = data[saddr:z].decode("ascii", "replace")
            if not name.startswith("APICD_"):
                break
            out.append((mid, name))
            pos += stride
        return out

    def test_apicd_stride_is_36_not_72(self):
        """Regression: stride 72 silently reads every second record.

        Reading at 72 still starts at the right place and every name pointer
        still resolves to an APICD_ string, so it looks like it works -- it
        reports 58 records instead of 115 and pairs each id with the wrong
        name further along. APICD_DESTROY_HNDL and friends vanish silently.

        The check that catches it is contiguity: at the correct stride the ids
        run 0x1000, 0x1001, 0x1002 with no gaps. At 72 they skip odd indices.
        """
        p = REPO / "dumps" / "engine" / "libObj.so"
        if not p.exists():
            self.skipTest(f"{p} not found")
        data = p.read_bytes()

        good = self._apicd_records(data, 36)
        bad = self._apicd_records(data, 72)

        self.assertEqual(len(good), 115, "stride 36 should yield 115 records")
        self.assertEqual(good[0], (0x1000, "APICD_CREATE_HNDL"))
        self.assertEqual(good[1], (0x1001, "APICD_DESTROY_HNDL"))

        # the odd-indexed names must be present at the right stride and absent
        # from the wrong one -- that is exactly what the stride bug dropped
        self.assertIn((0x1001, "APICD_DESTROY_HNDL"), good)
        self.assertIn((0x1003, "APICD_GET_ITEM_ATTRIBUTE"), good)
        self.assertIn((0x1005, "APICD_GET_RESUME_POS"), good)

        # contiguity: 0x1000..0x1016 must all be present
        ids = {i for i, _ in good}
        for want in range(0x1000, 0x1017):
            self.assertIn(want, ids, f"0x{want:x} missing from the APICD table")

        # and the wrong stride really does miss them, so this test has teeth
        bad_ids = {i for i, _ in bad}
        self.assertNotIn(0x1001, bad_ids)
        self.assertLess(len(bad), len(good))


if __name__ == "__main__":
    unittest.main()
