"""Verify reference VPH panel clock GPIO, selector and divider transactions."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_MODE_THUMB, Uc
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_SP

BASE = 0x635C6000
PIN_ENABLE = 0x63A60C10
PIN_DISABLE = 0x63A60B9C
PIN_TABLE = 0x6441CDC4
PANEL_SWITCH = 0x63A696C4
PANEL_SWITCH_INPUTS = (0x6441DDD4, 0x6441DE30, 0x6441DE20, 0x6441DC40)
ARG_REGS = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)
RETURN = 0x02000100
REFERENCE = "bc6cba98c1ce5ef9c7692b9701ed855c25958d285a646ef90dc3fdf398f5c4fa"
DIVIDERS = (
    (0x63A25474, 0xF2A01130, 0xF2A01030, 0xF2A00020, 0x1000, (5, 7, 15, 19)),
    (0x63A25704, 0xF2A11150, 0xF2A11030, 0xF2A10020, 0x1000000, (3, 9, 15)),
    (0x63A25760, 0xF2A12150, 0xF2A12030, 0xF2A10020, 0x2000000, (3, 9, 15)),
)


def audit(image):
    digest = hashlib.sha256(image).hexdigest()
    assert digest == REFERENCE
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    cpu.mem_map(BASE, (len(image) + 0xFFF) & ~0xFFF)
    cpu.mem_write(BASE, image)
    cpu.mem_map(0x02000000, 0x2000)
    cpu.mem_map(0xF2900000, 0x1000)
    cpu.mem_map(0xF2910000, 0x3000)
    cpu.mem_map(0xF2A00000, 0x13000)
    cpu.mem_map(0xF3440000, 0x1000)
    writes = []
    busy = {commit: [] for _, _, commit, _, _, _ in DIVIDERS}
    poll_counts = {}
    pin_calls = []

    def record(_cpu, _access, address, size, value, _data):
        assert size == 4
        writes.append((address, value))
        if address in busy:
            assert value == 1
            # Echo the command once on readback, remain busy for one poll, then clear.
            busy[address] = [1, 1, 0]
            poll_counts[address] = 0

    def update_read(emulator, _access, address, _size, _value, _data):
        if address in busy and busy[address]:
            poll_counts[address] += 1
            emulator.mem_write(address, busy[address].pop(0).to_bytes(4, "little"))

    def intercept_pin_enable(emulator, _address, _size, _data):
        pin_calls.append(emulator.reg_read(UC_ARM_REG_R0))
        emulator.reg_write(UC_ARM_REG_PC, emulator.reg_read(UC_ARM_REG_LR))

    for start, end in ((0xF2900000, 0xF2900FFF), (0xF2910000, 0xF2912FFF), (0xF2A00000, 0xF2A12FFF)):
        cpu.hook_add(UC_HOOK_MEM_WRITE, record, begin=start, end=end)
        cpu.hook_add(UC_HOOK_MEM_READ, update_read, begin=start, end=end)
    cpu.hook_add(UC_HOOK_MEM_WRITE, record, begin=0xF3440000, end=0xF3440FFF)

    def run(entry, args, stop=RETURN):
        writes.clear()
        poll_counts.clear()
        for reg, value in zip(ARG_REGS, args):
            cpu.reg_write(reg, value & 0xFFFFFFFF)
        cpu.reg_write(UC_ARM_REG_SP, RETURN + 0xE00)
        cpu.reg_write(UC_ARM_REG_LR, RETURN | 1)
        cpu.emu_start(entry | 1, stop, count=1500)
        assert cpu.reg_read(UC_ARM_REG_PC) == stop
        return list(writes)

    divider_reports = []
    for entry, divisor, commit, gate, mask, presets in DIVIDERS:
        assert run(entry, (-1,)) == [(gate + 8, mask)]
        assert run(entry, (-2,)) == [(gate + 4, mask)]
        assert run(entry, (0,)) == []
        for value in presets:
            assert run(entry, (value,)) == [(divisor, value), (commit, 1), (gate + 4, mask)]
            assert poll_counts == {commit: 3}
        divider_reports.append({
            "setter_va": hex(entry), "divider_word": hex(divisor), "commit_word": hex(commit),
            "gate_data": hex(gate), "gate_mask": hex(mask), "tested_presets": presets,
            "argument_minus_1": "clear gate bit", "argument_minus_2": "set gate bit without updating divider",
        })

    selectors = (
        [(0xF2900008, 0x300)],
        [(0xF2900004, 0x100), (0xF2900008, 0x200)],
        [(0xF2900008, 0x100), (0xF2900004, 0x200)],
    )
    for value, expected in enumerate(selectors):
        assert run(0x63A254D4, (value,)) == expected
    gate_clears = [(0xF2A00028, 0x1000), (0xF2A10028, 0x1000000), (0xF2A10028, 0x2000000)]
    mode_reports = []
    pin_hook = cpu.hook_add(UC_HOOK_CODE, intercept_pin_enable, begin=PIN_ENABLE, end=PIN_ENABLE)
    for mode, option, expected in (
        (0x1B, 0, selectors[2] + gate_clears),
        (0x30, 0, selectors[2] + [(0xF2A01130, 7), (0xF2A01030, 1), (0xF2A00024, 0x1000)] + gate_clears[1:]),
    ):
        pin_calls.clear()
        assert run(0x63A60994, (0, mode, option), stop=0x63A60A64) == expected
        assert pin_calls == [0]
        mode_reports.append({"mode_argument": hex(mode), "option": option,
                             "writes": [[hex(a), hex(v)] for a, v in expected]})

    # The alternate panel modes choose one of the two auxiliary divider banks.
    auxiliary_modes = []
    for mode, divisor in ((0x14, 15), (0x1C, 3), (0x1D, 3)):
        for option, selector, index in ((0, 1, 2), (1, 0, 1)):
            _, word, commit, gate, mask, _ = DIVIDERS[index]
            gates = list(gate_clears)
            gates[index:index + 1] = [(word, divisor), (commit, 1), (gate + 4, mask)]
            expected = selectors[selector] + gates
            pin_calls.clear()
            assert run(0x63A60994, (0, mode, option), stop=0x63A60A64) == expected
            assert pin_calls == [0]
            assert poll_counts == {commit: 3}
            auxiliary_modes.append({"mode_argument": hex(mode), "option": option, "selector": selector,
                                    "divider_word": hex(word), "divider_value": divisor,
                                    "writes": [[hex(a), hex(v)] for a, v in expected]})
    cpu.hook_del(pin_hook)

    # Readiness is seeded on the emulated clock pages. Update completion still
    # uses the same poll model as an individual divider transaction.
    for block in (0xF2A01000, 0xF2A11000, 0xF2A12000):
        cpu.mem_write(block + 4, (1).to_bytes(4, "little"))
        cpu.mem_write(block + 0x2C, (0x10000002).to_bytes(4, "little"))
    clock_profile = 0x645E5588
    expected_primary = [
        (0xF2A01020, 0x100), (0xF2A01024, 1), (0xF2A01010, 0), (0xF2A01000, 0x1B),
        (0xF2A01100, 11), (0xF2A01110, 23), (0xF2A01120, 47), (0xF2A01160, 7), (0xF2A01030, 1),
    ]
    expected_auxiliary = [
        (0xF2A11020, 0x100), (0xF2A11024, 1), (0xF2A11010, 0), (0xF2A11000, 0x21),
        (0xF2A11100, 3), (0xF2A11110, 3), (0xF2A11120, 7), (0xF2A11130, 15), (0xF2A11140, 1),
        (0xF2A11030, 1),
        (0xF2A12020, 0x100), (0xF2A12024, 1), (0xF2A12010, 0), (0xF2A12000, 0x119),
        (0xF2A12100, 3), (0xF2A12110, 3), (0xF2A12120, 7), (0xF2A12130, 15), (0xF2A12140, 3),
        (0xF2A12030, 1),
    ]
    upstream_cases = []
    for profile, primary_control, auxiliary_control in ((0, 0x1B, 0x21), (0x60000, 0x0C, 0x20)):
        cpu.mem_write(clock_profile, profile.to_bytes(4, "little"))
        for entry, stop, template, updates, control in (
            (0x63A271A8, RETURN, expected_primary, (0xF2A01030,), primary_control),
            (0x63A2733E, 0x63A274B8, expected_auxiliary, (0xF2A11030, 0xF2A12030), auxiliary_control),
        ):
            # Each run starts these read/modify/write control words at zero.
            for block in (0xF2A01000, 0xF2A11000, 0xF2A12000):
                cpu.mem_write(block, bytes(4))
            cpu.reg_write(UC_ARM_REG_R4, 0)
            expected = list(template)
            expected[3] = (template[3][0], control)
            assert run(entry, (), stop=stop) == expected
            assert poll_counts == dict.fromkeys(updates, 3)
            upstream_cases.append({"entry_va": hex(entry), "stop_address": hex(stop), "r4": 0,
                                   "profile_value": hex(profile),
                                   "writes": [[hex(a), hex(v)] for a, v in expected]})

    def skip_call(emulator, _address, _size, _data):
        emulator.reg_write(UC_ARM_REG_PC, emulator.reg_read(UC_ARM_REG_LR))

    diagnostics = (0x63DC8D56, 0x63DC8DD6, 0x63DC8E56, 0x63DC8EB8)
    for address in diagnostics:
        cpu.hook_add(UC_HOOK_CODE, skip_call, begin=address, end=address)
    mask = 1 << 26
    pin_reports = []
    for option in (0, 1):
        cpu.mem_write(PIN_TABLE, struct.pack("<12I", 4, 26, option, *([0xFFFFFFFF] * 9)))
        for entry, alias, extra_alias in ((PIN_ENABLE, 0xF2912404, 0xF2912444),
                                          (PIN_DISABLE, 0xF2912408, 0xF2912448)):
            expected = [(alias, mask)]
            if option == 1:
                expected += [(extra_alias, mask), (0xF2912458, mask)]
            assert run(entry, (0,)) == expected
            for selector in range(1, 5):
                assert run(entry, (selector,)) == []
            pin_reports.append({"entry_va": hex(entry), "row": [4, 26, option],
                                "writes": [[hex(a), hex(v)] for a, v in expected]})
    cpu.mem_write(PIN_TABLE, struct.pack("<12I", 4, 26, 0, *([0xFFFFFFFF] * 9)))
    top_enable = [(0xF3440050, 0x2062A), (0xF3440058, 0x200000), (0xF3440054, 0x33),
                  (0xF344005C, 1), (0xF3440040, 0x70077), (0xF3440048, 0x10010B77)]
    top_disable = [(0xF3440054, 0), (0xF344005C, 0), (0xF344004C, 0x10), (0xF344004C, 0x40),
                   (0xF3440044, 0x70077), (0xF344004C, 0x11117F77)]
    switch_reports = []
    for args, expected in (
        ((0, 0x1B, 1, 0), [(0xF2912404, mask)] + selectors[2] + gate_clears + top_enable),
        ((0, 0x30, 1, 0), [(0xF2912404, mask)] + selectors[2]
         + [(0xF2A01130, 7), (0xF2A01030, 1), (0xF2A00024, 0x1000)] + gate_clears[1:] + top_enable),
        ((0, 8, 0, 0), top_disable + gate_clears + selectors[2] + [(0xF2912408, mask)]),
    ):
        assert run(PANEL_SWITCH, args) == expected
        switch_reports.append({"arguments_r0_to_r3": list(args),
                               "writes": [[hex(a), hex(v)] for a, v in expected]})

    # Check the complete argument setup on both branches under the same mode pointer.
    mode_classifier = 0x63DC99C4
    alternate_modes = (0x1A, 0x1C, 0x1D, 0x30, 0xD0, 0xD1)
    for mode in (*range(256), 0x100, 0xFFFFFFFF):
        assert run(mode_classifier, (mode,)) == []
        assert cpu.reg_read(UC_ARM_REG_R0) == int(mode in alternate_modes)

    mode_preparation = 0x63A6818C
    cpu.hook_add(UC_HOOK_CODE, skip_call, begin=mode_preparation, end=mode_preparation)
    caller_reports = []
    for start, call, target in (
        (0x63A68BEC, 0x63A68C06, 0x63A6980C),
        (0x63A68C14, 0x63A68C36, PANEL_SWITCH),
    ):
        for inputs in ((3, 0x30, 1, 2), (0, 0x1B, 1, 0)):
            for address, value in zip(PANEL_SWITCH_INPUTS, inputs):
                cpu.mem_write(address, value.to_bytes(4, "little"))
            cpu.reg_write(UC_ARM_REG_R4, PANEL_SWITCH_INPUTS[1])
            assert run(start, (), stop=call) == []
            assert tuple(cpu.reg_read(reg) for reg in ARG_REGS) == inputs
        caller_reports.append({"argument_setup_va": hex(start), "call_va": hex(call),
                               "target_va": hex(target)})

    request_entry = 0x63A680C4
    request_source_flag = 0x6441AF60
    request_pending = 0x6441DDFC
    request_latched = 0x6441DE38
    request_dispatch = 0x63A69020
    request_stubs = (0x63DC9684, 0x63DC96F8, 0x63A6E8D8, 0x63DCDF20, 0x63A89F8C)
    for address in request_stubs:
        cpu.hook_add(UC_HOOK_CODE, skip_call, begin=address, end=address)
    mode_writes = []

    def record_mode_write(_cpu, _access, _address, size, value, _data):
        assert size == 4
        mode_writes.append(value)

    mode_word = PANEL_SWITCH_INPUTS[1]
    cpu.hook_add(UC_HOOK_MEM_WRITE, record_mode_write, begin=mode_word, end=mode_word)
    request_reports = []
    for mode, expected_mode_writes, call in ((0x1B, [0x1B, 0x1B], 0x63A68C36), (0x30, [0x30, 0x30], 0x63A68C06),
                                              (0x47, [7, 0x47], 0x63A68C36)):
        # Idle request bookkeeping, with the caller requesting a new active mode.
        for address in (request_pending, request_latched, 0x6441DE18, 0x6441DDB0,
                        0x6441DC40, 0x6452273D, 0x64522741, 0x64522747):
            cpu.mem_write(address, bytes(4))
        words = (1, mode, 1, 0, 0, 0) if mode == 0x1B else (1, mode, 0x91, 0x92, 0, 0x93)
        payload = struct.pack("<6I", *words)
        cpu.mem_write(request_source_flag, b"\x00")
        cpu.mem_write(request_source_flag + 4, payload)
        assert run(0x63A5D7B8, (), stop=0x63A5D7CC) == []
        assert cpu.mem_read(request_pending, 1) == b"\x00"
        cpu.mem_write(request_source_flag, b"\x01")
        assert run(0x63A5D7B8, (), stop=0x63A5D7CC) == []
        assert cpu.mem_read(request_pending, 1) == b"\x01"
        assert cpu.mem_read(request_pending + 4, len(payload)) == payload
        mode_writes.clear()
        assert run(request_dispatch, (), stop=call) == []
        assert cpu.mem_read(request_pending, 1) == b"\x00"
        assert cpu.mem_read(request_latched, len(payload)) == payload
        assert mode_writes == expected_mode_writes
        args = (0, mode, 1, 0)
        actual = tuple(cpu.reg_read(reg) for reg in ARG_REGS)
        assert actual == args, (mode, actual, args)
        request_reports.append({"record_words": list(words), "clock_call_va": hex(call),
                                "mode_word_writes": list(mode_writes),
                                "clock_arguments_r0_to_r3": list(args)})
    return {
        "reference_image_sha256": digest,
        "clock_setter_va": "0x63a60994",
        "divider_transactions": divider_reports,
        "selector_va": "0x63a254d4",
        "selector_writes": [[[hex(a), hex(v)] for a, v in writes] for writes in selectors],
        "mode_examples_with_mocked_pin_helper": mode_reports,
        "auxiliary_modes_with_mocked_pin_helper": auxiliary_modes,
        "upstream_clock_profile_va": hex(clock_profile),
        "upstream_clock_setup_cases_with_simulated_readiness": upstream_cases,
        "pin_table_va": hex(PIN_TABLE),
        "pin_cases_with_mocked_diagnostics": pin_reports,
        "mocked_diagnostic_vas": [hex(address) for address in diagnostics],
        "panel_switch_va": hex(PANEL_SWITCH),
        "panel_switch_cases": switch_reports,
        "panel_switch_argument_vas_r0_to_r3": [hex(address) for address in PANEL_SWITCH_INPUTS],
        "panel_switch_callers": caller_reports,
        "panel_switch_mode_classifier_va": hex(mode_classifier),
        "alternate_switch_modes": [hex(mode) for mode in alternate_modes],
        "mocked_caller_mode_preparation_va": hex(mode_preparation),
        "panel_request_path": {
            "submit_va": hex(request_entry), "pending_flag_va": hex(request_pending),
            "pending_record_va": hex(request_pending + 4), "latched_record_va": hex(request_latched),
            "submit_call_va": "0x63a5d7c8", "source_flag_va": hex(request_source_flag),
            "source_record_va": hex(request_source_flag + 4),
            "dispatch_va": hex(request_dispatch), "additional_mocked_calls": [hex(a) for a in request_stubs],
            "cases": request_reports,
        },
        "commit_clear_is_simulated": True,
        "camera_access_performed_by_audit": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not __debug__:
        parser.error("Run without Python optimization to retain instruction assertions")
    result = audit(args.firmware.read_bytes())
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("Panel clock divider, selector, mode, pin, switch, caller and upstream setup checks passed.")


if __name__ == "__main__":
    main()
