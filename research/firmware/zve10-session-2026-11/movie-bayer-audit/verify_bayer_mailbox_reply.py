"""Trace native completion-message serialization from five MMIO mailbox banks.

Register values and prior routing state are explicit fixtures, not a hardware
model. This verifies where response words come from, not that DMA completed.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('repo', type=Path)
a = p.parse_args()
sys.path.insert(0, str(a.repo / 'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness, MEM
from rtos import DATA

h = Harness()
h.u.mem_map(0xf3400000, 0x200000)
for pc in [0x63dd352e, 0x63aa76f0, 0x63dd407c]:
    h.callbacks[pc] = lambda args: h.ret(0)
messages = []
def route(args):
    n = h.u.mem_read(args[1], 1)[0]
    messages.append(dict(route_hex=bytes(h.u.mem_read(args[0], 8)).hex(),
                         message_hex=bytes(h.u.mem_read(args[1], n)).hex()))
    h.ret(0)
h.callbacks[0x63aa3d68] = route
config = h.run(0x63aa4a00)
# ADD PC at 0x63aa916c uses PC=0x63aa9170, not the instruction address.
routing = 0x63aa9170 + 0x00979700
bases = [0xf34a0100, 0xf34b0100, 0xf34c0100, 0xf35c0100, 0xf35d0100]
rows = []
for bank, base in enumerate(bases):
    for status_byte in [0, 1, 2, 0xff]:
        h.u.mem_write(config, bytes(sum(([0x30+i, 0, 0x60+i] for i in range(5)), [])))
        for i in range(5):
            h.u.mem_write(routing + i*8, bytes([0, 0x78, 0, 0]) + struct.pack('<I', 0x123+i))
        event = bytearray(16)
        event[2] = bank*3
        event[4] = status_byte
        h.u.mem_write(MEM, bytes(event))
        words = [0x12340000 + bank*16 + i for i in range(4)]
        for i, value in enumerate(words):
            h.put(base + 0x20 + 4*i, value)
        messages.clear()
        h.run(0x63aa90c4, MEM)
        assert len(messages) == 1
        msg = bytes.fromhex(messages[0]['message_hex'])
        assert len(msg) == 0x1c and msg[1] == 0x41
        assert msg[5] == 0x30+bank and msg[6:8] == b'\0\0'
        assert msg[8] == 0 and msg[9] == 0x78 and msg[10] == status_byte
        assert list(struct.unpack_from('<4I', msg, 12)) == words
        rows.append(dict(bank=bank, event_selector=bank*3, mailbox_base=hex(base),
                         status_byte=status_byte, words=words, **messages[0]))
print(json.dumps(dict(firmware_md5=hashlib.md5(DATA).hexdigest(), cases=len(rows),
    native_handler='0x63aa90c4', native_mailbox_read='0x63aa0e74',
    native_mapping='0x63aa8bf4', config_address=hex(config), routing_address=hex(routing),
    mocked_boundaries=['reply router 0x63aa3d68', 'trace 0x63dd352e', 'trace 0x63aa76f0', 'scheduler 0x63dd407c', 'harness memory helpers'],
    fixtures=['prior job routing state', 'MMIO register contents', 'caller event bytes'],
    pixel_or_dma_emulation=False, rows=rows), indent=2))
