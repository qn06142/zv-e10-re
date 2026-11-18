"""Build an offline UVC teardown candidate from the exact stock common library."""
import argparse
import hashlib
import io
from pathlib import Path

from elftools.elf.elffile import ELFFile
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB

ENTRY = 0x11a94
END = 0x11ad2
STOCK_MD5 = '31308976206a837f6f5c571992d2b499'
ASSEMBLY = """
    push {r4, r5, r6, lr}
    mov r4, r0
    movs r5, #0
    ldr.w r6, [r4, #0xd0]
    mov r0, r6
    movw r1, #0xe001
    blx #0x8bb0
    orrs r5, r0
    ldr.w r0, [r4, #0x8c]
    movw r1, #0xe001
    blx #0x8bb0
    orrs r5, r0
    cmp r6, #0
    ble done
    mov r0, r6
    blx #0x8e54
    orrs r5, r0
done:
    cmp r5, #0
    ite lt
    movlt r0, #9
    movge r0, #0
    pop {r4, r5, r6, pc}
"""


def build(stock):
    if hashlib.md5(stock).hexdigest() != STOCK_MD5:
        raise ValueError('unexpected stock library')
    elf = ELFFile(io.BytesIO(stock))
    offset = next(elf.address_offsets(ENTRY, END - ENTRY))
    assembled, _ = Ks(KS_ARCH_ARM, KS_MODE_THUMB).asm(ASSEMBLY, ENTRY)
    patch = bytes(assembled)
    if len(patch) > END - ENTRY:
        raise ValueError(f'patch exceeds function: {len(patch)} > {END - ENTRY}')
    return stock[:offset] + patch + stock[offset + len(patch):]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stock', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    with args.output.open('xb') as out:
        out.write(build(args.stock.read_bytes()))
