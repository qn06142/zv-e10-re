"""Verify selected ZV-E10 acquisition and capture-controller paths."""
import argparse
import hashlib
from pathlib import Path
import struct

from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_MODE_THUMB, Uc
from unicorn.arm_const import (
    UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
    UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8,
    UC_ARM_REG_SB, UC_ARM_REG_SL, UC_ARM_REG_SP,
)

from audit_dfe_fopd import IMAGE_BASE, IMAGE_SHA256

DISPATCH = 0x6379A57C
AFTER_DISPATCH = 0x6379A5BC
TABLE = 0x645BAB60
SCRATCH = 0x20000000
DESCRIPTOR = SCRATCH + 0x100
CALLBACK = SCRATCH + 0x200
VTABLE = SCRATCH + 0x300
RETURN = SCRATCH + 0x400
POWER_SAVE_CALLBACK = 0x638CF0A0
POWER_SAVE_STATE_SLOT = 0x6463E4F4


def audit(image):
    if hashlib.sha256(image).hexdigest() != IMAGE_SHA256:
        raise ValueError("Unexpected av-cam.bin identity")
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    cpu.mem_map(IMAGE_BASE, (len(image) + 0xfff) & ~0xfff)
    cpu.mem_write(IMAGE_BASE, image)
    cpu.mem_map(SCRATCH, 0x10000)

    rows = list(struct.iter_unpack("<II", cpu.mem_read(TABLE, 0xe8)))
    assert rows[-1] == (0, 0)
    assert len({mask for mask, _ in rows[:-1]}) == 28
    for mask, obj in rows[:-1]:
        assert mask.bit_count() == 1
        assert cpu.mem_read(obj, 4) == bytes(4)
        cpu.mem_write(obj, struct.pack("<I", VTABLE))
    cpu.mem_write(VTABLE + 0x10, struct.pack("<I", CALLBACK | 1))
    cpu.mem_write(CALLBACK, b"\x70\x47")  # Thumb bx lr, no hardware operation.

    calls = []

    def record_call(uc, _address, _size, _data):
        calls.append((uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)))

    cpu.hook_add(UC_HOOK_CODE, record_call, begin=CALLBACK, end=CALLBACK)
    selectors = [mask for mask, _ in rows[:-1]]
    cases = [0, *selectors, 0x60000, 0xffffffff]
    for requested in cases:
        calls.clear()
        cpu.mem_write(SCRATCH, struct.pack("<I", 0x1234))
        cpu.mem_write(SCRATCH + 0x28, struct.pack("<I", requested))
        cpu.reg_write(UC_ARM_REG_R0, SCRATCH)
        cpu.reg_write(UC_ARM_REG_R1, 0x1234)
        cpu.reg_write(UC_ARM_REG_R2, DESCRIPTOR)
        cpu.reg_write(UC_ARM_REG_SP, SCRATCH + 0x1ff0)
        cpu.emu_start(DISPATCH | 1, AFTER_DISPATCH, count=1000)
        assert cpu.reg_read(UC_ARM_REG_PC) == AFTER_DISPATCH
        assert calls == [(obj, DESCRIPTOR) for mask, obj in rows if requested & mask]
    print(f"Verified {len(cases)} selection masks across {len(selectors)} acquisition dispatch rows.")

    # A positive state bypasses the queued power transition. The supplied
    # callback can therefore execute directly without any frame or DMA event.
    state, = struct.unpack("<I", cpu.mem_read(POWER_SAVE_STATE_SLOT, 4))
    for count in (1, 2, 0x7fffffff):
        for callback in (0, CALLBACK | 1):
            calls.clear()
            cpu.mem_write(state, struct.pack("<I", count))
            cpu.reg_write(UC_ARM_REG_SP, SCRATCH + 0x1ff0)
            cpu.reg_write(UC_ARM_REG_LR, RETURN | 1)
            cpu.reg_write(UC_ARM_REG_R1, callback)
            cpu.emu_start(POWER_SAVE_CALLBACK | 1, RETURN, count=80)
            assert cpu.reg_read(UC_ARM_REG_PC) == RETURN
            assert cpu.reg_read(UC_ARM_REG_R0) == 0
            assert len(calls) == int(bool(callback))
    print("Verified 6 original-code DFE power-save fast-path cases without MMIO.")

    audit_destination(cpu)
    audit_capture_controller(cpu)
    isp_ports = audit_isp_aif_binding(cpu)
    audit_aif_programming(cpu, isp_ports)
    audit_isp0_interrupt(cpu)
    audit_sgc0_timing(cpu)


def audit_isp_aif_binding(cpu):
    controller = SCRATCH + 0x3000
    objects = SCRATCH + 0x4000
    stack = SCRATCH + 0x1ff0
    cpu.mem_write(VTABLE + 8, struct.pack("<I", CALLBACK | 1))

    def run(entry, stop):
        cpu.reg_write(UC_ARM_REG_SP, stack)
        cpu.emu_start(entry | 1, stop, count=180)
        assert cpu.reg_read(UC_ARM_REG_PC) == stop

    ports = []
    for index, constructor, end, channel, mmio in (
        (0, 0x63777f62, 0x63777f74, 3, 0xf3002380),
        (1, 0x637780bc, 0x637780cc, 9, 0xf3102380),
    ):
        cpu.reg_write(UC_ARM_REG_R4, objects)
        cpu.reg_write(UC_ARM_REG_SL, 0)
        cpu.reg_write(UC_ARM_REG_R8, 0)
        run(constructor, end)
        aif = objects + 0x754 + index * 0x860
        assert struct.unpack("<I", cpu.mem_read(aif + 0x20, 4))[0] == channel
        cpu.mem_write(aif, struct.pack("<I", VTABLE))
        cpu.mem_write(controller, bytes(0x100))
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3),
                              (controller, 1, objects, index)):
            cpu.reg_write(reg, value)
        run(0x63d076d6, 0x63d0771e)
        assert struct.unpack("<I", cpu.mem_read(controller + 0x50, 4))[0] == aif
        cpu.reg_write(UC_ARM_REG_R4, controller)
        cpu.reg_write(UC_ARM_REG_R8, 1)
        run(0x63d08466, 0x63d08482)
        assert struct.unpack("<I", cpu.mem_read(controller + 0x2c, 4))[0] == aif
        assert struct.unpack("<I", cpu.mem_read(controller + 0x7c, 4))[0] == 0x8000
        ports.append((channel, mmio, aif))

    print("Verified both ISP AIF constructor-to-controller bindings.")
    return ports


def audit_aif_programming(cpu, isp_ports):
    stack = SCRATCH + 0x1000
    aif = SCRATCH + 0x2000
    source = SCRATCH + 0x2100
    config = SCRATCH + 0x2200
    format_record = SCRATCH + 0x2300
    table = 0x63e89724
    for page in (0xf3002000, 0xf3102000, 0xf3020000):
        cpu.mem_map(page, 0x1000)

    def call(entry, *args):
        cpu.reg_write(UC_ARM_REG_SP, stack)
        cpu.reg_write(UC_ARM_REG_LR, RETURN | 1)
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            cpu.reg_write(reg, value)
        cpu.emu_start(entry | 1, RETURN, count=1000)
        assert cpu.reg_read(UC_ARM_REG_PC) == RETURN
        return cpu.reg_read(UC_ARM_REG_R0)

    fopd_ports = [(channel, 0xf3020200 + (channel - 17) * 0x80, aif) for channel in range(17, 23)]
    for channel, expected_port, aif_object in isp_ports + fopd_ports:
        global_base, port, _ = struct.unpack("<III", cpu.mem_read(table + channel * 12, 12))
        assert global_base == expected_port & ~0xfff
        assert port == expected_port
        cpu.mem_write(port, bytes(0x80))
        # Set the status bit that skips default geometry setup in this wrapper.
        cpu.mem_write(port + 4, struct.pack("<I", 0x80000000))
        if aif_object == aif:
            cpu.mem_write(aif + 0x20, struct.pack("<I", channel))
        cpu.mem_write(source, struct.pack("<4I", 1, 1, 0x22704000, 0x200000))
        cpu.mem_write(stack, struct.pack("<4I", 3840, 480, 0, config))
        assert call(0x63775acc, aif_object, source, 4096, 64) == 1
        assert struct.unpack("<5I", cpu.mem_read(config, 20)) == (1, 0x22704040, 3840, 256, 479)
        cpu.mem_write(format_record, bytes(0x14))
        assert call(0x63775bd4, aif_object, config, format_record) == 1
        assert struct.unpack("<4I", cpu.mem_read(port + 0x20, 16)) == (0x22704040, 3840, 256, 479)
        assert int.from_bytes(cpu.mem_read(port, 4), "little") & 1 == 0

    print("Verified 8 source-span to ISP/FOPD register paths without software mocks or DMA start.")

    # The stock still trace selects ISP0's write port and ISP1's read port.
    # Replay stock geometry and the standalone still-strip writer's geometry.
    aif_vtable = 0x64587278
    arm, = struct.unpack("<I", cpu.mem_read(aif_vtable + 0x10, 4))
    assert arm == 0x63D0A847
    for channel, port, is_writer, destination, rows in (
        (3, 0xf3002380, 1, 0x0b000000, 4024),
        (6, 0xf3102200, 0, 0x0b000000, 4024),
        (3, 0xf3002380, 1, 0x25200000, 360),
    ):
        global_base, bank, flags = struct.unpack("<III", cpu.mem_read(table + channel * 12, 12))
        assert (global_base, bank, flags & 1) == (port & ~0xfff, port, is_writer)
        cpu.mem_write(port, bytes(0x80))
        cpu.mem_write(config, struct.pack("<3I", 1, destination, 6048 * 2))
        call(0x639e2060, channel, config)
        cpu.mem_write(config, struct.pack("<4H4I", rows - 1, 0, 0, 0, 0, 0, 0, 0))
        call(0x639e2140, channel, config)
        assert struct.unpack("<4I", cpu.mem_read(port + 0x20, 16)) == (
            destination, 6048 * 2, 0, rows - 1,
        )
        cpu.mem_write(aif, struct.pack("<I", aif_vtable))
        cpu.mem_write(aif + 0x20, struct.pack("<I", channel))
        cpu.mem_write(port, struct.pack("<I", 2))
        assert call(arm & ~1, aif) == 0
        assert struct.unpack("<I", cpu.mem_read(port, 4))[0] == 3
        assert call(arm & ~1, aif) == 0xfffffffd
        assert struct.unpack("<I", cpu.mem_read(port, 4))[0] == 3
    print("Verified stock still and 360-row strip geometry through native AIF setters and arm guard.")

    # The still task reaches the CapController start slot through 0x63d0735e.
    # Verify the selected controller's native branch to the real AIF object.
    controller = SCRATCH + 0x3000
    isp0_writer = 0xf3002380
    assert struct.unpack("<I", cpu.mem_read(0x64586D30 + 0x0C, 4))[0] == 0x63D07DAB
    cpu.mem_write(controller + 0x2C, struct.pack("<I", aif))
    cpu.mem_write(aif + 0x20, struct.pack("<I", 3))
    for suppressed in (0, 1):
        cpu.mem_write(controller + 0x91, bytes([suppressed]))
        cpu.mem_write(isp0_writer, struct.pack("<I", 2))
        cpu.reg_write(UC_ARM_REG_SP, stack)
        cpu.reg_write(UC_ARM_REG_R4, controller)
        cpu.emu_start(0x63D07DC5, 0x63D07DD4, count=100)
        assert cpu.reg_read(UC_ARM_REG_PC) == 0x63D07DD4
        assert struct.unpack("<I", cpu.mem_read(isp0_writer, 4))[0] == 3 - suppressed
    print("Verified CapController's native ISP0 arm branch with both values of its suppression byte.")


def audit_capture_controller(cpu):
    stack = SCRATCH + 0x1000
    controller = SCRATCH + 0x2000
    for vtable, method in ((0x64586d30, 0x63d07596), (0x64587030, 0x63773d58), (0x64587160, 0x63774cf8)):
        cpu.mem_write(controller, struct.pack("<I", vtable))
        assert struct.unpack("<I", cpu.mem_read(vtable + 0x44, 4))[0] == 0x637721ed
        for wrapper, descriptor_offset in ((0x63d07822, None), (0x63d0784a, 4), (0x63d0787a, 0)):
            cpu.mem_write(stack, bytes(0x20))
            cpu.reg_write(UC_ARM_REG_SP, stack)
            cpu.reg_write(UC_ARM_REG_R0, controller)
            cpu.reg_write(UC_ARM_REG_R3, DESCRIPTOR if descriptor_offset is None else 0)
            if descriptor_offset is not None:
                cpu.mem_write(stack + descriptor_offset, struct.pack("<I", DESCRIPTOR))
            cpu.emu_start(wrapper | 1, method, count=80)
            assert cpu.reg_read(UC_ARM_REG_PC) == method
            assert cpu.reg_read(UC_ARM_REG_R0) == controller
            assert struct.unpack("<I", cpu.mem_read(cpu.reg_read(UC_ARM_REG_SP), 4))[0] == DESCRIPTOR

    for descriptor_word in (0, 1, 2, 0x22704000):
        cpu.mem_write(DESCRIPTOR + 0x34, struct.pack("<I", descriptor_word))
        cpu.reg_write(UC_ARM_REG_SB, DESCRIPTOR)
        cpu.reg_write(UC_ARM_REG_R7, 1)
        cpu.emu_start(0x637722d5, 0x637722e4, count=20)
        assert cpu.reg_read(UC_ARM_REG_PC) == 0x637722e4
        assert cpu.reg_read(UC_ARM_REG_R7) == descriptor_word
    print("Verified 9 wrapper/controller pairs and 4 descriptor-field cases.")


def audit_isp0_interrupt(cpu):
    base = 0xf3000000
    callback = SCRATCH + 0x600
    table, count = 0x64263a44, 0x64263bc4
    assert struct.unpack("<4I", cpu.mem_read(0x645926a0, 16)) == (0x63d0fe39, 2, 37, 0)
    cpu.mem_map(base, 0x1000)
    cpu.mem_write(callback, b"\x70\x47")  # bx lr
    cpu.mem_write(count, struct.pack("<I", 1))
    # A fixture subscriber for the ISP0 event tag plus the channel 3 mask.
    cpu.mem_write(table, struct.pack("<6I", 0x20008000, callback | 1, 0, 0, 0, 0))

    writes, events = [], []
    hooks = [
        cpu.hook_add(UC_HOOK_MEM_WRITE, lambda _u, _a, address, _s, value, _c:
                     writes.append((address, value)), begin=base, end=base + 0xfff),
        cpu.hook_add(UC_HOOK_CODE, lambda *_: events.append(True), begin=callback, end=callback),
    ]

    def return_from_lock(uc, _address, _size, _context):
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    for address in (0x635df208, 0x635df224):
        hooks.append(cpu.hook_add(UC_HOOK_CODE, return_from_lock, begin=address, end=address))
    try:
        for pending in (0, 0x4000, 0x8000, 0xc000):
            writes.clear()
            events.clear()
            cpu.mem_write(base + 0x48, struct.pack("<II", pending, 0))
            cpu.reg_write(UC_ARM_REG_SP, SCRATCH + 0x1ff0)
            cpu.reg_write(UC_ARM_REG_LR, RETURN | 1)
            cpu.emu_start(0x63d0fe39, RETURN, count=2000)
            assert cpu.reg_read(UC_ARM_REG_PC) == RETURN
            assert writes == ([(base + 0x48, pending), (base + 0x10, 0), (base + 0x14, 0)] if pending else [])
            assert events == ([True] if pending & 0x8000 else [])
        audit_isp0_capture_callbacks(cpu, base, table, count)
    finally:
        for hook in hooks:
            cpu.hook_del(hook)
    print("Verified IRQ 37 status acknowledgment and native mask matching with an ISP0 subscriber fixture.")


def audit_isp0_capture_callbacks(cpu, base, table, count):
    controller = SCRATCH + 0x7000
    event_object = controller + 0x100
    stack = SCRATCH + 0x1ff0

    def run(entry, end=RETURN, r0=0, r1=0, r2=0, r3=0):
        for register, value in (
            (UC_ARM_REG_SP, stack), (UC_ARM_REG_LR, RETURN | 1),
            (UC_ARM_REG_R0, r0), (UC_ARM_REG_R1, r1), (UC_ARM_REG_R2, r2), (UC_ARM_REG_R3, r3),
        ):
            cpu.reg_write(register, value)
        cpu.emu_start(entry | 1, end, count=5000)
        assert cpu.reg_read(UC_ARM_REG_PC) == end

    cpu.mem_write(controller + 0x48, struct.pack("<I", event_object))
    run(0x63777cec, r0=event_object)
    run(0x63777770, r0=event_object)
    assert struct.unpack("<I", cpu.mem_read(event_object, 4)) == (0x64587668,)
    # The still setup passes these as the secondary and primary callbacks.
    setup_callbacks = [
        struct.unpack("<I", cpu.mem_read(0x64638120 + offset, 4))[0]
        for offset in (0x1e18, 0x4668)
    ]
    assert setup_callbacks == [0x63d88f71, 0x63d88f91]
    run(0x63d08a6c, r0=controller, r1=setup_callbacks[0], r2=setup_callbacks[1])

    # Enter the native subscription block with a bound controller and empty table.
    cpu.mem_write(count, bytes(4))
    cpu.reg_write(UC_ARM_REG_R4, controller)
    cpu.reg_write(UC_ARM_REG_R5, 0x64638120)
    run(0x63773308, end=0x63773362)
    assert struct.unpack("<I", cpu.mem_read(count, 4)) == (2,)
    assert list(struct.iter_unpack("<6I", cpu.mem_read(table, 48))) == [
        (0x28000000, 0x63d07d4f, 0, 0x63d0887f, 0, controller),
        (0x24000000, 0x63d07d4f, 0, 0x63d08ea1, 0, controller),
    ]

    events, waits = [], []

    def return_from_service(uc, address, _size, _data):
        if address == 0x635df194:
            events.append((uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)))
        elif address == 0x635df1cc:
            waits.append((uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)))
            uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    hooks = [
        cpu.hook_add(UC_HOOK_CODE, return_from_service, begin=address, end=address)
        for address in (0x63d94468, 0x635df194, 0x635df1b0, 0x635df1cc)
    ]
    try:
        for pending, expected in (
            (0x8000, []), (0x04000000, [(0x16, 0x80)]),
            (0x08000000, [(0x16, 0x20000)]),
        ):
            events.clear()
            cpu.mem_write(base + 0x48, struct.pack("<II", pending, 0))
            run(0x63d0fe38)
            assert events == expected

        audit_shared_isp_irq(cpu, run, stack, table, events)

        # Masks supplied by the normal completion wait and the inter-shot wait.
        for mask in (0x82, 0x20000):
            run(0x63906dbc, r0=mask, r1=1)
        assert waits == [(0x16, 0x82), (0x16, 0x20000)]
    finally:
        for hook in hooks:
            cpu.hook_del(hook)
    print("Verified native ISP0 and shared ISP subscriptions and still-task event flags.")


def audit_shared_isp_irq(cpu, run, stack, table, events):
    # Capture the two callback records assembled by the real selector-1 case.
    capture_context = SCRATCH + 0x7000
    records = []

    def read_selector_records(uc, _address, _size, _data):
        sp = uc.reg_read(UC_ARM_REG_SP)
        for record, in struct.iter_unpack("<I", uc.mem_read(sp + 8, 8)):
            records.append(bytes(uc.mem_read(record, 20)))
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    hook = cpu.hook_add(UC_HOOK_CODE, read_selector_records, begin=0x638d146c, end=0x638d146c)
    try:
        run(0x63907474, r0=1, r1=capture_context)
    finally:
        cpu.hook_del(hook)
    assert [struct.unpack_from("<I", record, 8)[0] for record in records] == [0x63d88f55, 0x63906ed5]

    shared_base = 0xf3120000
    shared_controller = SCRATCH + 0x7900
    shared_events = SCRATCH + 0x7a00
    first_record = SCRATCH + 0x7b00
    second_record = first_record + 0x14
    cpu.mem_map(shared_base, 0x1000)
    cpu.mem_map(0xf3100000, 0x1000)
    assert struct.unpack("<4I", cpu.mem_read(0x64592690, 16)) == (0x637777c1, 2, 36, 0)
    run(0x63777d14, r0=shared_controller)
    run(0x63777d7c, r0=shared_events)
    run(0x637776a8, r0=shared_events)
    cpu.mem_write(shared_controller + 4, struct.pack("<I", shared_base))
    cpu.mem_write(shared_controller + 0x0c, struct.pack("<II", shared_events, 1))
    cpu.mem_write(shared_controller + 0x14, struct.pack("<I", 1))
    run(0x637787b8, r0=shared_controller + 0x8c, r1=0x63778339, r3=shared_controller)
    run(0x637787b8, r0=shared_controller + 0xa0, r1=0x63d10661, r3=shared_controller)
    cpu.mem_write(first_record, b"".join(records))
    cpu.mem_write(stack, struct.pack("<10I", 0, 0, 0, 0, 0, 0, 0, 0, first_record, second_record))
    # Supply nonzero timing dimensions to reach the selector-1 registration path.
    run(0x63778410, r0=shared_controller, r1=4, r2=619, r3=1940)
    assert cpu.reg_read(UC_ARM_REG_R0) == 0
    assert struct.unpack("<I", cpu.mem_read(table + 48, 4)) == (0x10000001,)
    assert struct.unpack("<II", cpu.mem_read(shared_base + 0x50, 8)) == (1, 1)

    # The normal bank advances the callback to +0x78, then the alternate
    # bank consumes it. Alternate status before the normal bank is inert.
    for normal, alternate, expected in (
        (2, 0, []), (0, 1, []), (1, 0, []), (0, 1, [(0x16, 2)]), (0, 1, []),
    ):
        events.clear()
        cpu.mem_write(shared_base + 0x48, struct.pack("<II", normal, alternate))
        run(0x637777c0)
        assert events == expected, (normal, alternate, events)


def audit_sgc0_timing(cpu):
    controller = SCRATCH + 0x7800
    vtable = controller + 0x40
    ready_callback = controller + 0x80
    stack = SCRATCH + 0x1ff0
    sgc0 = 0xfc0a1100
    cpu.mem_map(sgc0 & ~0xfff, 0x1000)

    def put(address, word):
        cpu.mem_write(address, struct.pack("<I", word))

    def read(address):
        return struct.unpack("<I", cpu.mem_read(address, 4))[0]

    def run(entry, *args):
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            cpu.reg_write(reg, value)
        cpu.reg_write(UC_ARM_REG_SP, stack)
        cpu.reg_write(UC_ARM_REG_LR, RETURN | 1)
        cpu.emu_start(entry | 1, RETURN, count=1000)
        assert cpu.reg_read(UC_ARM_REG_PC) == RETURN

    put(controller, vtable)
    put(controller + 4, 0xfc000000)
    put(vtable + 0x14, ready_callback | 1)
    cpu.mem_write(ready_callback, b"\x00\x20\x70\x47")  # Return zero from the controller busy check.
    cpu.mem_write(stack, bytes(8))  # Two ancillary timing arguments, supplied as fixture zeros.
    put(sgc0 + 0xa8, 0x026b0001)

    # Reconstruct the timing inputs from the captured idle and active register fields.
    for vertical, horizontal, extra, packed, lead, gate in (
        (840, 1430, 0, 0x03470595, 0x2e3, 0x026b0000),
        (619, 1940, 1, 0x026a0793, 0x206, 0x026b0001),
    ):
        run(0x63d26acc, controller, vertical, horizontal, extra)
        assert (read(sgc0 + 0x20), read(sgc0 + 0x24), read(sgc0 + 0xa8)) == (packed, lead, gate)

    # Use the same selector and start argument as the normal caller's zero-override branch.
    put(sgc0 + 0x08, 1)
    put(sgc0 + 0x30, 0x10000)
    writes = []
    hook = cpu.hook_add(
        UC_HOOK_MEM_WRITE,
        lambda _cpu, _access, address, _size, value, _data: writes.append((address, value)),
        begin=sgc0, end=sgc0 + 0xff,
    )
    try:
        run(0x637a4278, controller, 1, 0)
        assert writes == [
            (sgc0 + 0x2c, 0), (sgc0 + 0x30, 0), (sgc0 + 0x08, 0), (sgc0 + 0x10, 1),
        ]
    finally:
        cpu.hook_del(hook)
    run(0x637a3f60, 0xfc000000)
    assert cpu.reg_read(UC_ARM_REG_R0) == 0  # MMIO fixture has no autonomous status transition.
    put(sgc0 + 0x10, 0x10001)
    run(0x637a3f60, 0xfc000000)
    assert cpu.reg_read(UC_ARM_REG_R0) == 1
    print("Verified native SGC0 timing for both stock snapshots and the ordered start writes.")


def audit_destination(cpu):
    stack = SCRATCH + 0x1000
    context = SCRATCH + 0x2000
    request = stack + 4
    flags = context + 0x6d60

    def read_word(address):
        return struct.unpack("<I", cpu.mem_read(address, 4))[0]

    def run(entry, end):
        cpu.emu_start(entry | 1, end, count=150)
        assert cpu.reg_read(UC_ARM_REG_PC) == end

    for entry, pair_offset, handle_offset in (
        (0x63d871f2, 0x6b5c, 0x67b6),
        (0x63d87204, 0x6b3c, 0x67b0),
    ):
        for address, capacity, handle in ((0x22704000, 0x120000, 0x154), (0x23450000, 0x300000, 0x507)):
            cpu.mem_write(context + pair_offset, struct.pack("<II", address, capacity))
            cpu.mem_write(context + handle_offset, struct.pack("<H", handle))
            cpu.reg_write(UC_ARM_REG_SP, stack)
            cpu.reg_write(UC_ARM_REG_R4, context)
            run(entry, 0x63d87230)
            assert cpu.reg_read(UC_ARM_REG_R1) == request
            assert read_word(request + 8) == context + pair_offset
            assert struct.unpack("<H", cpu.mem_read(request + 0xc, 2))[0] == handle

            # The intervening setup code uses the request as its r6 record.
            # Stub only the separate selector to isolate the destination copy.
            cpu.mem_write(flags, struct.pack("<I", 0x10))
            cpu.reg_write(UC_ARM_REG_R6, request)
            cpu.reg_write(UC_ARM_REG_SB, flags)

            def return_selector(uc, _address, _size, _data):
                uc.reg_write(UC_ARM_REG_R0, 0x102)
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

            hook = cpu.hook_add(UC_HOOK_CODE, return_selector, begin=0x63906f78, end=0x63906f78)
            try:
                run(0x638f54f6, 0x638f556e)
            finally:
                cpu.hook_del(hook)
            assert read_word(stack + 0x24) == stack + 0x170
            assert read_word(stack + 0x1a0) == 1
            assert (read_word(stack + 0x1a4), read_word(stack + 0x1a8)) == (address, capacity)
            run(0x638f5748, 0x638f576c)
            assert read_word(stack) == stack + 0x170

    print("Verified 4 native destination handoffs from context pair through acquisition request.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    audit(parser.parse_args().image.read_bytes())
