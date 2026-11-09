"""Adversarial execution of original Bayer job wait instructions.

Queue receive/free and logging are fixtures. No DSP, DMA, pixels or hardware
completion is modeled. Success here describes protocol acceptance only.
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
queue, ids, output, flags, message = [MEM + x for x in (0, 0x100, 0x200, 0x300, 0x1000)]
h.put(queue, 0x123)
h.callbacks[0x6396f8c4] = lambda args: h.ret(0)
pending = []
received = []
freed = []

def receive(args):
    assert args[0] == 0x123 and args[2] == 0xffffffff
    if not pending:
        h.ret(1)
        return
    item = pending.pop(0)
    raw = bytearray(0x1c)
    raw[0] = len(raw)
    raw[1] = item.get('command', 0x41)
    raw[5] = item['id']
    struct.pack_into('<H', raw, 6, item.get('error', 0))
    raw[10] = item.get('flag', 0x56)
    struct.pack_into('<4I', raw, 12, *item.get('words', [1, 2, 3, 4]))
    if 'native_message_hex' in item:
        raw = bytes.fromhex(item['native_message_hex'])
    h.u.mem_write(message, bytes(raw))
    h.put(args[1], message)
    received.append(dict(item))
    h.ret(0)

def free(args):
    assert args[:2] == [0x123, message]
    freed.append(message)
    h.ret(0)

h.callbacks[0x635df6a0] = receive
h.callbacks[0x635df72c] = free

def run(expected, replies):
    pending[:] = replies
    received.clear()
    freed.clear()
    h.u.mem_write(ids, bytes(expected))
    h.u.mem_write(output, bytes([0xa5]) * 48)
    h.u.mem_write(flags, bytes([0xa5]) * 3)
    status = h.run(0x63b318ec, queue, ids, output, flags, len(expected))
    assert len(freed) == len(received)
    slots = [list(struct.unpack('<4I', h.u.mem_read(output + i * 16, 16))) for i in range(len(expected))]
    return dict(expected=expected, replies=replies, status=status, output_slots=slots,
                flags=list(h.u.mem_read(flags, len(expected))), received=len(received), freed=len(freed))

rows = []
sentinel = [0xa5a5a5a5] * 4
for response_id in range(256):
    row = run([4], [dict(id=response_id)])
    assert row['status'] == 0
    assert row['output_slots'][0] == ([1, 2, 3, 4] if response_id == 4 else sentinel)
    rows.append(row)
for expected, replies, result in [
    ([4, 7], [dict(id=7), dict(id=4)], [[1, 2, 3, 4], [1, 2, 3, 4]]),
    ([4, 7], [dict(id=4), dict(id=4)], [[1, 2, 3, 4], sentinel]),
    ([4, 7], [dict(id=99), dict(id=98)], [sentinel, sentinel]),
    ([4, 7, 9], [dict(id=4), dict(id=4), dict(id=4)], [[1, 2, 3, 4], sentinel, sentinel]),
]:
    row = run(expected, replies)
    assert row['status'] == 0 and row['output_slots'] == result
    rows.append(row)
for reply in [dict(id=4, command=0x40), dict(id=4, error=1), dict(id=4, error=0x100)]:
    row = run([4], [reply])
    assert row['status'] == 1 and row['output_slots'] == [sentinel]
    rows.append(row)
row = run([4], [])
assert row['status'] == 1 and row['received'] == 0
rows.append(row)
native_messages = []
def route(args):
    native_messages.append(bytes(h.u.mem_read(args[1], h.u.mem_read(args[1], 1)[0])))
    h.ret(0)
h.callbacks[0x63aa3d68] = route
request = MEM + 0x2000
for job_id in range(256):
    raw = bytearray(0x1c)
    raw[0] = len(raw)
    raw[1] = 0x41
    raw[9] = job_id
    raw[12] = 0x78
    h.u.mem_write(request, bytes(raw))
    native_messages.clear()
    h.run(0x63dd3e46, request)
    assert len(native_messages) == 1
    msg = native_messages[0]
    assert msg[1] == 0x41 and msg[5] == job_id and msg[6:8] == b'\0\0'
    assert msg[8] == 1 and msg[9] == 0x78
    row = run([job_id], [dict(id=job_id, native_message_hex=msg.hex())])
    assert row['status'] == 0 and row['output_slots'] == [[0, 0, 0, 0]] and row['flags'] == [0]
    row['producer'] = '0x63dd3e46 cancellation reply; no job or DMA execution'
    rows.append(row)
print(json.dumps(dict(firmware_md5=hashlib.md5(DATA).hexdigest(), cases=len(rows),
    native_wait='0x63b318ec', native_receive='0x63b31828', native_validate='0x63b31428',
    mocked_boundaries=['OS queue receive 0x635df6a0', 'OS message free 0x635df72c', 'logger 0x6396f8c4', 'reply routing 0x63aa3d68 (producer cases only)', 'harness memory helpers'],
    finding='Wait counts responses, not unique matching IDs; success does not independently prove all jobs completed.',
    dma_or_pixels_emulated=False, rows=rows), indent=2))
