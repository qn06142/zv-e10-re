"""Tests for the recovered /dev/dmpgles2 ioctl ABI.

`sugilite_ioctl` in `grm_gles.ko` is 2,584 bytes of ARM at `.text+0x8e4`.  These
check the recovered command table, the `_IOC` decoding, the per-handler
attribution, and the finding that the module's RTOS RPC path is unreachable.

They run with no camera: everything is read from the on-disk module.

The dispatch recovery went wrong four times, each time *silently* -- every version
returned a plausible, smaller or differently-valued table rather than an error:

  1. literal pool read at ``addr+size`` instead of ``addr+8``
  2. ARM immediates taken from the printed text rather than the decoded operand
  3. r3 cleared after each ``cmp``, losing the cumulative refinement chain
  4. symbolic execution of the decision tree with a ``seen`` set shared between
     paths, which pruned blocks entered from a different predecessor

Which check catches which trap, established by mutation rather than assumed:

======  ========  ==========================================
trap    count?   caught by
======  ========  ==========================================
3       yes       the count drops to 7
4       yes       the count drops to 1
1       **no**    only the exact command *set*
2       **no**    only the exact command *set*
======  ========  ==========================================

Traps 1 and 2 produce the *right number* of commands with the *wrong values*.
With the PC offset mutated to ``addr+4`` the tool still printed "17 commands
recovered" -- the literal pool is contiguous, so reading one word early yields a
different constant per site and the derived chain still produces one entry per
comparison. So the count is a structural statistic and **cannot** detect a value
error; ``test_the_exact_command_set`` is what discriminates, and
``test_the_pc_offset_trap_stays_documented`` additionally asserts the offset the
code actually uses rather than the comment describing it.
"""
import pathlib
import re
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research" / "firmware"))

import sugilite_ioctl as si  # noqa: E402

KO = REPO / "dumps" / "camera_2025" / "usr" / "usr" / "kmod" / "grm_gles.ko"

# what the recovered table must contain
CMDS = [0x40048204, 0x80048200, 0x80048205, 0x80048206, 0x80048207,
        0x8004820A, 0x80048263, 0xC0048201, 0xC0048202, 0xC0048203,
        0xC0048208, 0xC0048209, 0xC004820C, 0xC004820D, 0xC004820F,
        0xC0048211, 0xC0048212]


def load():
    ko = si.Ko(KO)
    ent, sz = ko.func("sugilite_ioctl")
    return ko, ent, sz, si.dispatch(ko, ent, sz)


class TestIocDecoding(unittest.TestCase):
    """The encoding, checked against the kernel's own _IOC layout."""

    def test_fields_are_read_from_the_right_bit_positions(self):
        f = si.ioc(0xC004820F)
        self.assertEqual(f["dir"], 3, "0xc0.. has dir=3 (_IOC_READ)")
        self.assertEqual(f["size"], 4)
        self.assertEqual(f["type"], 0x82)
        self.assertEqual(f["nr"], 0x0F)

    def test_direction_bits(self):
        self.assertEqual(si.ioc(0x40048204)["dir"], 1, "0x4.. is write-only")
        self.assertEqual(si.ioc(0x80048200)["dir"], 2, "0x8.. is read|write")
        self.assertEqual(si.ioc(0xC0048201)["dir"], 3)

    def test_size_field_is_never_confused_with_the_dir_shift(self):
        """size sits at bits 16-29 and dir at 30-31.

        Getting this wrong turns every command into a different size, which is a
        plausible-looking wrong answer rather than an obvious one.
        """
        for c in CMDS:
            self.assertEqual(si.ioc(c)["size"], 4, "cmd 0x%08x" % c)

    def test_type_byte_is_constant(self):
        self.assertEqual({si.ioc(c)["type"] for c in CMDS}, {0x82})


@unittest.skipUnless(KO.exists(), "grm_gles.ko not present")
class TestDispatchRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ko, cls.ent, cls.sz, cls.cmds = load()

    def test_function_geometry(self):
        self.assertEqual(self.ent, 0x8E4)
        self.assertEqual(self.sz, 0xA18)
        self.assertEqual(self.sz, 2584)

    def test_all_seventeen_commands_are_recovered(self):
        """Catches the two traps that change the *number* of commands.

        Established by mutation: reintroducing the cumulative-r3 bug gives 7 and
        the decision-tree bug gives 1.  It does NOT catch a wrong literal-pool
        offset or a mis-decoded immediate -- those keep all 17 and change their
        values, which is what ``test_the_exact_command_set`` is for.
        """
        self.assertEqual(len(self.cmds), 17,
                         "recovered %d commands, expected 17"
                         % len(self.cmds))

    def test_the_exact_command_set(self):
        """The discriminating check: count *and* values.

        This is the only assertion that fails when the literal pool is read at
        the wrong offset -- a mutation that still yields 17 entries.
        """
        self.assertEqual(sorted(self.cmds), sorted(CMDS))

    def test_the_commands_are_contiguous_where_they_should_be(self):
        """A structural sanity check on the recovered values.

        Sixteen of the seventeen are `_IOC(dir, 0x82, nr, 4)` with nr in
        0x00..0x12.  Reading the pool one word early would scatter these across
        unrelated bit patterns, so requiring 16 of 17 to land in that family is
        a cheap null model for "these are really ioctl encodings".
        """
        fam = [c for c in self.cmds
               if si.ioc(c)["type"] == 0x82 and si.ioc(c)["size"] == 4
               and si.ioc(c)["nr"] <= 0x12]
        self.assertEqual(len(fam), 16,
                         "only %d of 17 commands decode as _IOC(.,0x82,nr<=0x12,4)"
                         % len(fam))

    def test_every_command_has_a_handler(self):
        for c, e in self.cmds.items():
            self.assertIsNotNone(e["eq"],
                                 "cmd 0x%08x has no beq target" % c)

    def test_handlers_are_inside_the_function(self):
        for c, e in self.cmds.items():
            self.assertTrue(self.ent <= e["eq"] < self.ent + self.sz,
                            "cmd 0x%08x handler 0x%x is outside the function"
                            % (c, e["eq"]))

    def test_no_command_constant_is_an_instruction_word(self):
        """The `addr+size` literal-pool bug produced prologue words.

        0x0a000055 and 0x8a00001c are `mov ip,sp` / `push {...}` in this
        function, so if either appears as a "command" the PC offset is wrong.
        """
        for c in self.cmds:
            for word in (0x0A000055, 0x8A00001C, 0xE1A0C00D, 0xE92DDDF0):
                self.assertNotEqual(c, word,
                                    "an instruction word leaked into the table")

    def test_nr_layout_is_dense_with_three_holes_and_one_outlier(self):
        nrs = sorted(si.ioc(c)["nr"] for c in self.cmds)
        self.assertEqual(nrs, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0x0A, 0x0C, 0x0D,
                               0x0F, 0x11, 0x12, 0x63])
        dense = [n for n in nrs if n <= 0x12]
        self.assertEqual([n for n in range(max(dense) + 1) if n not in dense],
                         [0x0B, 0x0E, 0x10])

    def test_the_cumulative_r3_chain_is_what_makes_17_work(self):
        """Guards trap 3: the chain refines one register across comparisons.

        Counting the distinct `cmp r1, r3` sites that resolve to a constant must
        equal the number of commands.  If r3 were cleared after each cmp, the
        derived constants would vanish and this would drop to 7.
        """
        resolved = [e["cmp"] for e in self.cmds.values()]
        self.assertEqual(len(resolved), len(set(resolved)),
                         "two commands share a cmp site -- the scan double-counted")
        self.assertEqual(len(resolved), 17)


@unittest.skipUnless(KO.exists(), "grm_gles.ko not present")
class TestHandlers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ko, cls.ent, cls.sz, cls.cmds = load()
        cls.info, cls.starts = si.attribute(cls.ko, cls.cmds)

    def handler_for(self, nr):
        c = next(c for c in self.cmds if si.ioc(c)["nr"] == nr)
        return self.cmds[c]["eq"]

    def test_lock_and_unlock_are_a_pair(self):
        """nr=17 takes a semaphore, nr=18 releases it."""
        self.assertIn("down_interruptible", self.info[self.handler_for(17)][0])
        self.assertIn("up", self.info[self.handler_for(18)][0])

    def test_nr_13_is_the_only_synchronous_wait(self):
        """It is the only handler using the completion machinery."""
        others = sorted(si.ioc(c)["nr"] for c in self.cmds
                        if si.ioc(c)["nr"] != 13
                        and "wait_for_completion_interruptible_timeout"
                        in self.info[self.cmds[c]["eq"]][0])
        self.assertEqual(others, [], "another handler also waits on a completion")

    def test_only_nr_15_reaches_the_hardware(self):
        """Exactly one handler calls sugilite_iowrite32.

        This is the load-bearing negative: if a second handler poked registers,
        the ioctl would be a more capable door than the docs claim.
        """
        touching = sorted(si.ioc(c)["nr"] for c in self.cmds
                          if "sugilite_iowrite32" in self.info[self.cmds[c]["eq"]][0])
        self.assertEqual(touching, [15])

    def test_nr_15_is_a_fixed_kick_not_a_register_write(self):
        """It writes 0x20000001 to BAR+0xC0, and only for input == 1.

        Read from the disassembly: `cmp r2,#1` / `orr r0,r2,#0x20000000` /
        `add r1,r1,#0xc0`.  A general register-write door would take the offset
        and the value from the user; this one takes neither.
        """
        h = self.handler_for(15)
        text = "\n".join("%08x %-8s %s" % (i.address, i.mnemonic, i.op_str)
                         for i in self.ko.disasm(h, h + 0x4C))
        self.assertIn("cmp      r2, #1", text)
        self.assertIn("orr      r0, r2, #0x20000000", text)
        self.assertIn("add      r1, r1, #0xc0", text)

    def test_nr_4_calls_nothing(self):
        """The only pure-write command is a bare field store."""
        self.assertEqual(self.info[self.handler_for(4)][0], [])


@unittest.skipUnless(KO.exists(), "grm_gles.ko not present")
class TestRpcsPathIsUnreachable(unittest.TestCase):
    """The module's RTOS door exists and cannot be called."""

    @classmethod
    def setUpClass(cls):
        cls.ko = si.Ko(KO)
        cls.funcs, cls.gaps, _ = si.uncalled_gap(cls.ko)

    def test_the_osal_message_calls_are_outside_every_function(self):
        rel = self.ko.reloc.get(".rel.text", {})
        osal = {"osal_snd_msg", "osal_snd_sync_msg", "osal_snd_sync_direct",
                "osal_valloc_msg_wait", "osal_free_msg"}
        sites = sorted({o for o, names in rel.items() if osal & set(names)})
        self.assertEqual(len(sites), 7, "expected 7 osal_* call sites")
        for o in sites:
            inside = any(lo <= o < hi for lo, hi, _n in self.funcs)
            self.assertFalse(inside,
                             "osal call at 0x%x is now inside a sized function; "
                             "re-check whether the RPC is reachable" % o)

    def test_nothing_branches_to_the_rpc_region(self):
        rel = self.ko.reloc.get(".rel.text", {})
        osal = {"osal_snd_msg", "osal_snd_sync_msg", "osal_snd_sync_direct",
                "osal_valloc_msg_wait", "osal_free_msg"}
        sites = sorted({o for o, names in rel.items() if osal & set(names)})
        lo, hi = sites[0], sites[-1] + 4
        # every address a branch could target inside that run
        targets = set(range(lo & ~3, hi + 4, 4))
        hits = si.find_callers(self.ko, targets)
        self.assertEqual(hits, [],
                         "something now branches into the RPC region: %r" % hits)

    def test_the_region_has_no_symbol_so_no_pointer_can_reach_it(self):
        """The reachability argument needs both halves.

        No direct branch, *and* no symbol, means no relocated function pointer
        can target it either.  Either alone would be weak.
        """
        names = {n for n, _v, _s, _b, t in self.ko.symlist if t == "STT_FUNC"}
        for n in ("sugilite_ioctl", "sugilite_interrupt"):
            self.assertIn(n, names)
        # no STT_FUNC symbol starts inside the gap
        gap_lo, gap_hi = 0x744, 0x8E4
        for n, v, s, _b, t in self.ko.symlist:
            if t == "STT_FUNC" and gap_lo <= v < gap_hi:
                self.fail("a symbol %s now covers the gap at 0x%x" % (n, v))

    def test_the_rpc_payload_is_twelve_bytes(self):
        """The message header carries 0x0c and memcpy copies 0xc bytes."""
        rel = self.ko.reloc.get(".rel.text", {})
        memcpy_sites = sorted(o for o, names in rel.items()
                              if "memcpy" in names and 0x744 <= o < 0x8E4)
        self.assertEqual(len(memcpy_sites), 1)
        text = "\n".join("%08x %-8s %s" % (i.address, i.mnemonic, i.op_str)
                         for i in self.ko.disasm(0x744, 0x8E4))
        self.assertIn("mov      r2, #0xc", text)
        self.assertIn("mov      r3, #0xc", text)


class TestToolInvariants(unittest.TestCase):
    """Guards on the tool's own claims, which outlive the module."""

    SRC = REPO / "research" / "firmware" / "sugilite_ioctl.py"

    @staticmethod
    def flat(path):
        """Source with runs of whitespace collapsed to single spaces.

        Docstrings are hard-wrapped, so a phrase like "jump table" can straddle a
        newline.  Searching the raw text for it fails for a reason that has
        nothing to do with the claim being checked.
        """
        return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))

    def test_the_pc_offset_trap_stays_documented(self):
        text = self.flat(self.SRC)
        self.assertIn("addr + 8", text,
                      "the ARM PC = addr+8 note must survive")
        # and it must be what the code actually does
        self.assertRegex(self.SRC.read_text(encoding="utf-8"),
                         r"i\.address \+ 8 \+ dsp")

    def test_the_jump_table_correction_is_recorded(self):
        """An earlier note claimed jump-table dispatch.  It is a compare chain."""
        text = self.flat(self.SRC)
        self.assertIn("binary search", text)
        self.assertIn("not a jump table", text,
                      "the correction to the jump-table claim must stay visible")
        self.assertIn("jump-table dispatch", text,
                      "the superseded claim should be named, not just denied")

    def test_r3_is_not_cleared_after_a_cmp(self):
        self.assertIn("r3 is deliberately NOT cleared", self.flat(self.SRC))

    def test_the_script_runs_clean_with_no_camera(self):
        """It is a pure file reader, so it must not require the device."""
        import subprocess
        py = REPO / ".venv" / "Scripts" / "python.exe"
        p = subprocess.run([str(py), "-B", str(self.SRC)],
                           capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(p.returncode, 0, p.stderr[-800:])
        self.assertIn("verdict", p.stdout)


if __name__ == "__main__":
    unittest.main()
