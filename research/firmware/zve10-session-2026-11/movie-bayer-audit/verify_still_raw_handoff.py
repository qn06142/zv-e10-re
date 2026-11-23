"""Replay the stock still RAW handoff using a fixture at the DMM boundary."""
import argparse
import json
from pathlib import Path
import struct
import sys


SELECT_CAPTURE = 0x63927268
QUEUE_CAPTURE = 0x638DCC94
RAW_REQUEST = 0x643B2DE4
CAPTURE_RELEASE = 0x638D963C
PUBLISH_AND_CLEANUP = 0x63D8FD52
RELEASE = 0x63926FB8
DMM_OPEN = 0x63970228
DMM_FREE = 0x6396FFD0
CAPTURE_SLOT_FREE = 0x63D8A3FC
RETAINED = 0x643D7320
RAW_LENGTH = 0x643BBB14
ROW_SAMPLES = 0x643BBB24
UNIT_TYPE = 0x643BBB28
DESCRIPTOR = 0x643BBC7C
PUBLISHED_HANDLE = 0x644A472E
INVALID_HANDLE = 0xFFFF
CAPTURE_POOL = 0x0B000000
CAPTURE_CAPACITY = 0x03000000


def verify(harness, context):
    from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_SP
    from rtos_harness import STOP

    calls = []
    source_slot = context + 0x67B0
    command, header, selector, reply = (context + offset for offset in
                                        (0x8000, 0x8100, 0x8200, 0x8300))
    harness.put(command, header)
    harness.put(command + 0x5C, selector)
    harness.put(header, 0x104)
    harness.put(selector, 0x4E)
    harness.put(selector + 4, 0x404)

    queued = []

    def stop_at_queue(args):
        sp = harness.u.reg_read(UC_ARM_REG_SP)
        queued.append([*args, harness.word(sp), harness.word(sp + 4)])
        harness.u.reg_write(UC_ARM_REG_PC, STOP)

    harness.callbacks[0x63E258B0] = lambda _: harness.ret(1)
    harness.callbacks[0x637B5904] = lambda _: harness.ret(0)
    harness.callbacks[QUEUE_CAPTURE] = stop_at_queue
    harness.run(SELECT_CAPTURE, command, reply, balanced=False)
    del harness.callbacks[QUEUE_CAPTURE]
    assert len(queued) == 1
    assert queued[0][0] == 2
    assert queued[0][3] == PUBLISH_AND_CLEANUP | 1

    for address in (0x638CE3BC, 0x638CE430, 0x635DF208, 0x635DF224, 0x63D79FA2):
        harness.callbacks[address] = lambda _: harness.ret(0)
    harness.run(QUEUE_CAPTURE, *queued[0])
    assert harness.word(RAW_REQUEST + 0x10) == 2
    assert harness.word(RAW_REQUEST + 0x1C) == PUBLISH_AND_CLEANUP | 1

    # Exercise capture-work allocation with a caller-owned object. The native
    # constructor and callback copy both execute before the last release.
    init_record = context + 0x8400
    harness.run(0x63D799F2, init_record, 0)
    harness.callbacks[0x63D79F6C] = lambda _: harness.ret(context)
    assert harness.run(0x638D95A4, init_record, RAW_REQUEST + 0x14, 0) == context
    assert harness.word(context + 0x10) == PUBLISH_AND_CLEANUP | 1
    release_slot = harness.word(harness.word(context) + 0x0C)
    assert release_slot == CAPTURE_RELEASE | 1
    row_samples = 6048
    row_count = 4024  # Fixture. The capture did not record the second dimension.

    def halfword(address):
        return struct.unpack("<H", harness.u.mem_read(address, 2))[0]

    def put_halfword(address, value):
        harness.u.mem_write(address, struct.pack("<H", value))

    def open_unit(args):
        handle, flags, timeout, reply = args
        calls.append(("open", handle, flags, timeout))
        packet = bytearray(0x70)
        struct.pack_into("<HH", packet, 0, 0x8005, 0)
        struct.pack_into("<H", packet, 4, handle)
        struct.pack_into("<H", packet, 6, 0x55)
        struct.pack_into("<H", packet, 8, 1)
        struct.pack_into("<II", packet, 16, CAPTURE_POOL, CAPTURE_CAPACITY)
        harness.u.mem_write(reply, bytes(packet))
        harness.ret(0)

    def free_unit(args):
        calls.append(("free", *args[:3]))
        harness.ret(0)

    for address in (0x6391BDE8, 0x6391BDD8, 0x6391BDC8, 0x63D94468):
        harness.callbacks[address] = lambda _: harness.ret(0)
    harness.callbacks[DMM_OPEN] = open_unit
    harness.callbacks[DMM_FREE] = free_unit
    harness.callbacks[CAPTURE_SLOT_FREE] = lambda args: (
        calls.append(("capture-slot-free", *args[:2])),
        harness.ret(0),
    )
    put_halfword(RETAINED, INVALID_HANDLE)
    for slot in range(56):
        put_halfword(source_slot + 2 * slot, INVALID_HANDLE)
    harness.put(context + 0x6844, 2)
    harness.put(context + 0x214, row_samples)
    harness.put(context + 0x218, row_count)

    put_halfword(source_slot, INVALID_HANDLE)
    harness.put(context + 4, 1)
    harness.run(release_slot & ~1, context)
    assert not calls

    for handle in (0x10F6, 0x2B68):
        put_halfword(source_slot, handle)
        harness.put(context + 4, 2)
        harness.run(release_slot & ~1, context)
        assert halfword(source_slot) == handle
        harness.run(release_slot & ~1, context)
        assert halfword(source_slot) == INVALID_HANDLE
        assert halfword(RETAINED) == halfword(PUBLISHED_HANDLE) == handle
        assert halfword(DESCRIPTOR + 4) == handle
        assert halfword(DESCRIPTOR + 8) == 1
        assert harness.word(DESCRIPTOR + 0x10) == CAPTURE_POOL
        assert harness.word(DESCRIPTOR + 0x14) == CAPTURE_CAPACITY
        assert harness.word(RAW_LENGTH) == CAPTURE_CAPACITY
        assert harness.word(ROW_SAMPLES) == row_samples
        assert harness.word(UNIT_TYPE) == 0x347
    assert calls == [
        ("open", 0x10F6, 0, 0xFFFFFFFF),
        ("free", 0x10F6, 2, 5),
        ("open", 0x2B68, 0, 0xFFFFFFFF),
    ]

    harness.run(RELEASE)
    assert calls[-1] == ("free", 0x2B68, 2, 5)
    assert halfword(RETAINED) == INVALID_HANDLE
    assert harness.word(RETAINED + 4) == 0
    # The copied public descriptor still contains the just-released handle.
    assert halfword(DESCRIPTOR + 4) == 0x2B68
    assert halfword(DESCRIPTOR + 8) == 1
    assert harness.word(DESCRIPTOR + 0x10) == CAPTURE_POOL
    harness.run(RELEASE)
    assert len(calls) == 4
    return {
        "dmm_calls": calls,
        "unit_type": "0x347",
        "factory_raw_request_selects_publisher": True,
        "last_capture_work_release_invokes_publisher": True,
        "retained_handle_survives_capture_cleanup": True,
        "retained_handle_invalidated": True,
        "public_descriptor_survives_release": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    args = parser.parse_args()
    harness_dir = (
        args.repo / "research/firmware/raw_frame_source/verified_yc/evidence"
        / "native-setup-20261030"
    )
    sys.path.insert(0, str(harness_dir))
    from rtos_harness import Harness, MEM

    print(json.dumps(verify(Harness(), MEM), indent=2))


if __name__ == "__main__":
    main()
