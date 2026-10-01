"""Tests for the /proc/tmonitor RTOS task-monitor trace.

`/proc/tmonitor` is the proc interface of the module configured by
`tmonitor.addr=0xF00000 tmonitor.size=0x8000 tmonitor.mask=0`.  Reading it yields
a ~50 ms live window of the RTOS scheduler: per-task state, wait channel and
priority, plus a `MODULE::task` profile and an IRQ hot-spot profile.

These run with no camera attached.  They check the captured artefact and the
parsing and classification logic, and skip the live capture.

The two tests that matter most are the address-space split and the base-address
arithmetic.  Both were wrong on the first run and neither raised:

  * the split was initially `>= 0xBF000000`, which put *every* symbol on the LiRo
    side -- including `run_ksoftirqd`, `irq_thread` and `n_tty_receive_buf`, which
    are obviously Linux.  It reported a clean result, just the wrong one.
  * the base address was read straight off the symbol name, which is a string, so
    it raised `TypeError` -- the one failure in this project that did *not* fail
    silently.
"""
import pathlib
import re
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research" / "firmware"))

import tmonitor as tm  # noqa: E402

TRACE = REPO / "research" / "firmware" / "tmonitor_trace.txt"


def raw_block(text):
    """The trace lines out of the artefact's fenced raw section."""
    m = re.search(r"## raw trace\s*\n+```\n(.*?)\n```", text, re.S)
    assert m, "no raw trace block in the artefact"
    return m.group(1).splitlines()


class TestTraceArtefact(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TRACE.exists():
            raise unittest.SkipTest(f"{TRACE} not present")
        cls.text = TRACE.read_text(encoding="utf-8")
        cls.lines = raw_block(cls.text)
        cls.sched, cls.profiles, cls.other = tm.parse(cls.lines)

    # ---- the record forms ------------------------------------------------

    def test_the_trace_parses_into_two_record_forms(self):
        """A 50 ms window is hundreds of records, not a handful.

        The risk here is the console-truncation trap: the wrapper elides the
        middle of a long session, so a read that trusted stdout would see a
        marker and a handful of lines.  Assert a floor.
        """
        self.assertGreater(len(self.sched), 400)
        self.assertGreater(len(self.profiles), 200)

    def test_sched_records_carry_state_wchan_task_and_prio(self):
        r = self.sched[0]
        for field in ("state", "wchan", "addr", "task", "cpu", "prio", "next"):
            self.assertIn(field, r)
        self.assertTrue(all(isinstance(r[k], int)
                            for k in ("state", "cpu", "prio", "next")))

    def test_kernel_noise_is_not_parsed_as_records(self):
        """The session carries the command echo and the shell prompt.

        Neither may become a record.  `other` may legitimately contain them --
        they are unrecognised lines, not errors -- so what is asserted is that
        no *record form* is among them.
        """
        for line in self.other:
            self.assertFalse(
                line.lstrip().startswith("["),
                f"a record form leaked into `other`: {line!r}")
        joined = "\n".join(self.other)
        self.assertNotIn("-sched next", joined)
        self.assertNotIn("-profile user", joined)

    def test_null_wchan_is_recorded_not_dropped(self):
        """`wchan:0(0)` means runnable, not "no information".

        Dropping it would silently bias every wait-channel statistic towards
        blocked tasks, so it has to survive parsing.
        """
        nulls = [r for r in self.sched if r["wchan"] in ("0", "0(0)")]
        self.assertGreater(len(nulls), 50,
                           "the runnable/null wchan should be the largest group")

    def test_profile_records_split_into_tasks_and_irqs(self):
        """`-profile user` carries two different things.

        A task name is `MODULE::task`; an IRQ record is `irq:<n>,<count>` where
        the second field is a *count*.  Conflating them loses the profile.
        """
        tasks, irqs = set(), set()
        for p in self.profiles:
            m = tm.IRQPROF.match(p["name"])
            if m:
                irqs.add(int(m.group(1)))
            else:
                tasks.add(p["name"])
        self.assertGreaterEqual(len(tasks), 20, "module::task names missing")
        self.assertGreaterEqual(len(irqs), 5, "irq:N,count records missing")
        # the two sets must be disjoint: no task name is also an IRQ record
        self.assertFalse(tasks & {str(i) for i in irqs})

    def test_a_task_name_containing_a_space_still_parses(self):
        """`TC::VD_Seq S` has a space in it.

        Matching the name as `\\S+` dropped the record into `other` and lost it.
        This is the one parser bug the tests caught on the first run.
        """
        self.assertIn("TC::VD_Seq S", self.profiles_names(),
                      "a task name with a space was dropped")
        self.assertNotIn("TC::VD_Seq S", self.other)

    def profiles_names(self):
        return {p["name"] for p in self.profiles}

    # ---- the classification that was wrong -------------------------------

    def test_the_two_kernels_split_cleanly_at_the_threshold(self):
        """`run_ksoftirqd` is Linux.  `trcv_mbf` is LiRo.  Both must classify.

        This is the null model for the threshold: it is not fitted to the labels,
        because every symbol is independently known.  A threshold that only
        worked on the ambiguous symbols would not discriminate.
        """
        linux = {"run_ksoftirqd", "irq_thread", "hrtimer_nanosleep",
                 "poll_schedule_timeout", "hwtimer_schedule_timeout",
                 "do_wait", "futex_wait_queue_me", "n_tty_receive_buf",
                 "prepare_to_wait", "svc_preempt", "rmond"}
        liro = {"trcv_mbf", "twai_flg", "tslp_tsk", "osal_rcv_msg_tmo",
                "osal_wai_sem_tmo", "tx_thread", "utimer_res_sleep",
                "os_unlock", "hdmi_workqueue", "hdmi_inter_req_queue",
                "__k_4u_wait_cb", "__k_user_msg_cb"}

        a = tm.analyse(self.sched, self.profiles)
        seen = a["wchans"]

        checked = 0
        for sym in linux & set(seen):
            self.assertGreaterEqual(seen[sym]["base"], tm.LINUX_KERN_BASE,
                                    f"{sym} is Linux but classified as LiRo")
            checked += 1
        for sym in liro & set(seen):
            self.assertLess(seen[sym]["base"], tm.LINUX_KERN_BASE,
                            f"{sym} is LiRo but classified as Linux")
            checked += 1

        self.assertGreaterEqual(checked, 8,
                                "too few known symbols to test the split")

    def test_no_symbol_sits_near_the_threshold(self):
        """The split is only meaningful if nothing straddles it.

        If the two populations actually overlapped, the threshold would be
        arbitrary and the classification worthless.
        """
        a = tm.analyse(self.sched, self.profiles)
        bases = [w["base"] for w in a["wchans"].values() if w["base"]]
        below = [b for b in bases if b < tm.LINUX_KERN_BASE]
        above = [b for b in bases if b >= tm.LINUX_KERN_BASE]
        self.assertTrue(below and above, "only one kernel observed")
        self.assertGreater(max(below), 0x5F000000,
                           "a low symbol is not in the expected LiRo range")
        self.assertLess(min(above) - max(below), 0x01000000,
                        "the two populations are not cleanly separated")

    def test_base_address_is_offset_corrected_and_stable(self):
        """base = min(address - offset) over every observed call site.

        The offsets are call sites and vary between reads; the base must not,
        which is what makes it worth recording.  4-alignment is a weak but free
        check that the subtraction happened at all.
        """
        a = tm.analyse(self.sched, self.profiles)
        for sym, w in a["wchans"].items():
            if not w["base"]:
                continue
            self.assertEqual(w["base"], min(addr - off
                                           for off, addr in w["pairs"]),
                             f"{sym}: base is not min(address - offset)")
            # every recorded pair must reproduce the same base
            for off, addr in w["pairs"]:
                self.assertGreaterEqual(addr - off, w["base"])
            self.assertEqual(w["base"] % 4, 0,
                             f"{sym} base 0x{w['base']:x} is not 4-aligned")

    # ---- the content that makes the trace worth having -------------------

    def test_the_rosal_message_primitives_are_present(self):
        """The RTOS message-bus primitives, previously only inferred.

        `osal_rcv_msg_tmo` and `osal_wai_sem_tmo` are what a message to the
        firmware has to reach, and their presence here is independent of the
        offline analysis of av-cam.bin.
        """
        a = tm.analyse(self.sched, self.profiles)
        for sym in ("osal_rcv_msg_tmo", "osal_wai_sem_tmo"):
            self.assertIn(sym, a["wchans"],
                          f"{sym} missing from the wait channels")
            self.assertGreater(a["wchans"][sym]["count"], 0)

    def test_module_task_names_are_recovered(self):
        """`MODULE::task` is a direct map from av-cam.bin modules to work."""
        a = tm.analyse(self.sched, self.profiles)
        self.assertGreaterEqual(len(a["module_tasks"]), 20)
        for expected in ("LC::HS_Mai", "TC::VD_Pos", "FW::DFS_Chk",
                         "CPM::JudPrm", "IDT::OPD_TOP", "LENS::HS3_Mai",
                         "ALL::VD_Drv", "LC::BNB_Wai", "FW::UpdAcs"):
            self.assertIn(expected, a["module_tasks"])

    def test_a_module_prefix_is_not_mistaken_for_the_task(self):
        """`ALL:HS_Mai` has one colon; `LC::HS_Mai` has two.

        The set contains both spellings.  Collapsing them would lose a record,
        so the test asserts the odd one out survives rather than being cleaned up.
        """
        a = tm.analyse(self.sched, self.profiles)
        singles = [n for n in a["module_tasks"] if n.count(":") == 1]
        doubles = [n for n in a["module_tasks"] if n.count(":") == 2]
        self.assertTrue(doubles, "no MODULE::task names at all")
        self.assertIn("ALL:HS_Mai", singles)
        # K_AFMAP has no separator at all -- a third spelling, also kept verbatim
        self.assertIn("K_AFMAP", a["module_tasks"])

    def test_one_address_carries_two_names_and_the_address_is_the_key(self):
        """0x60293424 is emitted as both `..._fixed_fl` and `..._fixed_flag`.

        The shorter is a strict prefix of the longer.  The kernel symbol table
        settles which is real: `tty_insert_flip_string_fixed_flag` is
        NUL-terminated in vmlinux.bin and the short form has no exact hit at
        all, so **the trace emitted a clipped copy of a real name**.

        Consequence: a name is not an identity here.  Grouping by name would
        split one symbol into two and double-count it.

        This is a single occurrence, not a general clip width -- the short form
        is 31 characters and the long one 33, so no fixed buffer of 32 explains
        it, and no other address in the window carries two names.  An earlier
        reading of this as "names are clipped at 32 characters" was wrong.
        """
        a = tm.analyse(self.sched, self.profiles)
        long_name = "tty_insert_flip_string_fixed_flag"
        short_name = "tty_insert_flip_string_fixed_fl"
        if long_name not in a["wchans"] or short_name not in a["wchans"]:
            self.skipTest("this window did not include the tty symbol")

        self.assertEqual(len(long_name), 33)
        self.assertEqual(len(short_name), 31)
        self.assertTrue(long_name.startswith(short_name))

        self.assertEqual(a["wchans"][long_name]["base"],
                         a["wchans"][short_name]["base"],
                         "the two names should resolve to one address")
        self.assertEqual(a["wchans"][long_name]["offsets"],
                         a["wchans"][short_name]["offsets"])

        # and it is the only such pair in this window
        by_addr = {}
        for sym, w in a["wchans"].items():
            by_addr.setdefault(w["base"], []).append(sym)
        dupes = [v for v in by_addr.values() if len(v) > 1]
        self.assertEqual(len(dupes), 1,
                         f"expected exactly one duplicated address, got {dupes}")

    def test_two_irqs_dominate_the_profile(self):
        """irq 84 and irq 201 outrank everything else, and there is a gap.

        The claim is dominance plus a step down, not a fixed ratio: successive
        windows give top-two sums of 2441, 2487 and 2746 against a stable tail
        near 1970, so `top2 > rest` holds but `top2 > 2 * rest` does not, and
        asserting the latter would have been fitting the test to one window.
        """
        a = tm.analyse(self.sched, self.profiles)
        irq = a["irq"]
        self.assertGreaterEqual(len(irq), 5)
        ranked = [n for _, n in irq.most_common()]
        self.assertGreaterEqual(sum(ranked[:2]), sum(ranked[2:]),
                                "the top two IRQs do not outweigh the rest")
        # and a clear step down to third place
        self.assertGreater(ranked[1], 3 * ranked[2],
                           "no gap between the top two and the rest")


class TestKernelImages(unittest.TestCase):
    """Which kernel image could resolve these symbols.

    Both negatives here were checked rather than assumed, and together they bound
    what the trace's addresses can be used for.
    """

    def vmlinux(self):
        cands = sorted(REPO.glob("dumps/**/vmlinux.bin"))
        if not cands:
            self.skipTest("vmlinux.bin not present")
        return cands[0].read_bytes()

    def test_vmlinux_holds_the_real_tty_name_and_not_the_clipped_one(self):
        """The kernel table is the authority on which name is real."""
        data = self.vmlinux()
        long_name = b"tty_insert_flip_string_fixed_flag"
        short_name = b"tty_insert_flip_string_fixed_fl"

        # the long name must appear NUL-terminated
        exact_long = [m.start() for m in re.finditer(re.escape(long_name), data)
                      if data[m.start() + len(long_name):
                               m.start() + len(long_name) + 1] == b"\x00"]
        self.assertTrue(exact_long,
                        "the full symbol name is not in the kernel table")

        # the short name must NOT appear anywhere except inside the long one
        raw_short = [m.start() for m in re.finditer(re.escape(short_name), data)]
        exact_short = [o for o in raw_short
                       if o + len(short_name) >= len(data)
                       or data[o + len(short_name)] == 0
                       or not re.match(rb"[A-Za-z0-9_]",
                                       data[o + len(short_name):
                                           o + len(short_name) + 1])]
        self.assertEqual(exact_short, [],
                         "the clipped name turned out to be real in its own "
                         "right; update the truncation conclusion")

    def test_vmlinux_cannot_resolve_the_liro_symbols(self):
        """Every LiRo wait channel is absent from vmlinux.bin.

        This bounds the result: the trace names *and* addresses its symbols, so
        nothing is lost, but the Linux image alone cannot symbolise the RTOS
        side, which is where the interesting primitives are.
        """
        data = self.vmlinux()
        for sym in (b"trcv_mbf", b"twai_flg", b"tslp_tsk",
                    b"osal_rcv_msg_tmo", b"osal_wai_sem_tmo",
                    b"utimer_res_sleep", b"tx_thread", b"hdmi_workqueue"):
            self.assertEqual(data.count(sym), 0,
                             f"{sym.decode()} IS in vmlinux.bin -- the "
                             "LiRo/Linux boundary has changed")

    def avcam(self):
        cands = [c for c in sorted(REPO.glob("dumps/**/av-cam.bin"))
                 if c.stat().st_size > 1_000_000]
        if not cands:
            self.skipTest("av-cam.bin not present")
        return cands[0].read_bytes()

    def test_avcam_carries_some_but_not_all_liro_symbols(self):
        """`twai_flg` and `osal_wai_sem_tmo` are in the firmware; the rest are not.

        The two that are present are the ones firmware *modules* call.  The ones
        missing -- `trcv_mbf`, `tslp_tsk`, `osal_rcv_msg_tmo`, `tx_thread`,
        `hdmi_workqueue` -- are defined by the LiRo kernel itself, and that image
        is in neither `av-cam.bin` nor `vmlinux.bin`.

        So the RTOS kernel is not available offline, and the trace's LiRo
        addresses cannot be resolved from what is on disk.  They can still be
        *used*: the trace already gives the names.
        """
        data = self.avcam()

        present = (b"twai_flg", b"osal_wai_sem_tmo")
        absent = (b"trcv_mbf", b"tslp_tsk", b"osal_rcv_msg_tmo", b"tx_thread",
                  b"hdmi_workqueue", b"utimer_res_sleep")

        for sym in present:
            self.assertGreater(data.count(sym), 0,
                               f"{sym.decode()} vanished from av-cam.bin")
        for sym in absent:
            self.assertEqual(data.count(sym), 0,
                             f"{sym.decode()} IS in av-cam.bin -- the LiRo "
                             "kernel image may have been located; update the "
                             "docs, this is good news")


class TestCaptureTraps(unittest.TestCase):
    def test_the_tool_reads_the_log_not_stdout(self):
        """The trace is ~2,000 lines; stdout elides its middle."""
        src = (REPO / "research" / "firmware" / "tmonitor.py").read_text(
            encoding="utf-8")
        self.assertIn("zve10_shell.log", src)
        self.assertIn("capture_output", src,
                      "stdout must be captured and discarded, not parsed")

    def test_the_log_truncation_trap_is_documented(self):
        """`open(LOG, "w")` destroys the previous session's log.

        An earlier extraction of this trace was summarised and then lost to the
        next three commands.  The reason the artefact is written immediately has
        to survive in the source, or the tool will look redundant.
        """
        src = (REPO / "research" / "firmware" / "tmonitor.py").read_text(
            encoding="utf-8")
        self.assertIn('"w"', src)
        self.assertIn("truncates the previous", src)

        # and the scratch logger really is destructive
        logger = (REPO / "research" / "device" / "zve10_shell.py").read_text(
            encoding="utf-8")
        self.assertRegex(logger, r'open\(LOG,\s*"w"',
                         "zve10_shell.py no longer truncates; update this test")


class TestParsing(unittest.TestCase):
    def test_a_sched_line_parses(self):
        line = ("[  499.413651 ] -sched next:2016 < prev:1944 state:2 "
                "wchan:trcv_mbf+238(5f4e006c) task:liro-kliro_66 cpu:2 prio:147")
        sched, profiles, other = tm.parse([line])
        self.assertEqual(len(sched), 1)
        r = sched[0]
        self.assertEqual(r["task"], "liro-kliro_66")
        self.assertEqual(r["wchan"], "trcv_mbf+238")
        self.assertEqual(r["addr"], 0x5F4E006C)
        self.assertEqual(r["state"], 2)
        self.assertEqual(r["prio"], 147)
        self.assertFalse(profiles)
        self.assertFalse(other)

    def test_both_profile_forms_parse(self):
        lines = ["[  499.414091 ] -profile user irq:129,9 cpu:1",
                 "[  499.476338 ] -profile user CPM::JudPrm cpu:0"]
        sched, profiles, other = tm.parse(lines)
        self.assertFalse(sched)
        self.assertEqual(len(profiles), 2)
        self.assertEqual({p["name"] for p in profiles},
                         {"irq:129,9", "CPM::JudPrm"})
        self.assertFalse(other)

    def test_noise_and_echoes_are_not_records(self):
        """Console output is unrecognised, not a record.

        The `dhd_bus_init` line starts with a bracketed timestamp like a real
        record, so it is the discriminating case: it must land in `other`, and
        must not become a sched or profile entry.
        """
        console = "[ 1917.236030] dhd_bus_init: enable 0x06, ready 0x06"
        noisy = [
            "===== $ busybox cat /proc/tmonitor =====",
            "busybox cat /proc/tmonitor",
            "",
            console,
            "/usr/share/app # ",
            "[  499.413651 ] -sched next:1 < prev:2 state:0 "
            "wchan:0(0) task:swapper/0 cpu:0 prio:0",
        ]
        sched, profiles, other = tm.parse(noisy)
        self.assertEqual(len(sched), 1)
        self.assertEqual(sched[0]["task"], "swapper/0")
        self.assertFalse(profiles)
        self.assertIn(console, other,
                      "console output must be kept, just not parsed as a record")

    def test_a_task_name_with_a_slash_is_one_token(self):
        """`swapper/0` and `irq/229-dwc3` must not be split on the slash."""
        line = ("[ 1.0 ] -sched next:1 < prev:2 state:1 wchan:0(0) "
                "task:irq/229-dwc3 cpu:2 prio:0")
        sched, _, _ = tm.parse([line])
        self.assertEqual(sched[0]["task"], "irq/229-dwc3")


if __name__ == "__main__":
    unittest.main()
