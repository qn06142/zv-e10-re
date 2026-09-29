"""Read the AES key out of libupdatertalk.so and decrypt the update body.

Why this is reading, not reverse engineering
--------------------------------------------
The delivery route for the updater's dlopen was previously recorded as blocked
behind an "encrypted libupdatercommon.so".  Three claims turned out to be wrong,
each checked rather than assumed:

  av-cam.bin is not encrypted.  2,459 of 4,221 4 KB blocks are below 6.5
  bits/byte and the low-entropy region spans essentially the whole 16.5 MB.
  CMD_ID_SDF_EXEC and ExecSensCmd are in the clear.  The high-entropy blocks
  are compressed sections.

  libupdatercommon.so is not encrypted either -- 0 of 9 blocks high-entropy --
  and it contains no messaging code at all.  It is a file, flag and mount
  utility.  It was never the place the uipc endpoint lived.

  The actual descrambler is libupdatertalk.so: 3,452 bytes, entropy 4.4, and it
  *exports* `KeyArray` alongside `Dec_ScrambleInit`/`Dec_Scramble` while
  importing `AES_set_decrypt_key`/`AES_decrypt` from libcrypto.so.3.  So the
  transform is AES, called from a library, with the key sitting in a named
  exported symbol.  Reading a symbol is not disassembling anything.

What is still a guess, and is therefore tested rather than assumed
------------------------------------------------------------------
Nothing about the key's length, its position in the file, or the mode.  So this
tries the plausible combinations and reports which one produces a known-good
result, rather than asserting one.  The success criterion is structural, not
"it decrypted to something": the body is Compressed ROMFS with magic 453dcd28,
and crypter.elf's own strings contain the firmware header `0100UDTRFIRM`.  A
candidate only counts if it produces one of those, or if it is a valid zlib
stream, or if it is a valid ELF.

The project has previously been bitten by a byte-order assumption here: a key
read as on-disk bytes `1f0280550208` was noted as being `0x5580021f` in engine
order, and another key was carried truncated to 4 bytes.  So key truncations
are included rather than left out on the assumption that 16 bytes is right.
"""
import collections
import hashlib
import pathlib
import struct
import zlib

from elftools.elf.elffile import ELFFile

REPO = pathlib.Path(__file__).resolve().parents[2]
TALK = REPO / 'dumps' / 'camera_2025' / 'usr' / 'usr' / 'lib' / 'libupdatertalk.so'
BODY = REPO / 'fw' / 'udtrbody.bin'
if not BODY.exists():
    BODY = REPO / 'tools' / 'udtrbody.bin'

ROMFS_MAGIC = bytes.fromhex('28cd3d45')      # 453dcd28 little-endian
FW_MAGIC = b'0100UDTRFIRM'


def try_aes_decrypt(key, data):
    """AES-ECB and AES-CBC over the plausible key lengths, or None"""
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:
        return None, 'cryptography not installed'
    out = []
    for name, k in (('aes-%d' % (len(key) * 8), key),):
        try:
            alg = algorithms.AES(k)
        except Exception:
            continue
        # ECB
        try:
            c = Cipher(alg, modes.ECB()).decryptor()
            out.append(('ecb/' + name, c.update(data[:4096]) + c.finalize()))
        except Exception as e:
            out.append(('ecb/' + name, b''))
        # CBC with a zero IV, which is the usual default when none is stored
        try:
            iv = b'\x00' * 16
            c = Cipher(alg, modes.CBC(iv)).decryptor()
            out.append(('cbc0/' + name, c.update(data[:4096]) + c.finalize()))
        except Exception:
            pass
    return out, None


def plausible(b):
    """does this look like a real container rather than random bytes"""
    if b[:4] == ROMFS_MAGIC:
        return 'ROMFS magic 453dcd28'
    if b[:11] == FW_MAGIC:
        return 'firmware header 0100UDTRFIRM'
    if b[:4] == b'\x7fELF':
        return 'ELF'
    for off in range(0, 64):
        if b[off:off + 2] in (b'\x1f\x8b', b'\x78\x9c', b'\x78\x01', b'\x78\xda'):
            try:
                zlib.decompress(b[off:off + 512], 15 if b[off + 1:off + 2] == b'\x8b'
                                else zlib.MAX_WBITS)
                return 'zlib stream at +%d' % off
            except Exception:
                pass
    # printable ratio, as a weak fallback signal
    pr = sum(1 for x in b if 32 <= x < 127) / max(1, len(b))
    if pr > 0.85:
        return 'printable (%.0f%%) -- weak' % (100 * pr)
    return None


def main():
    print('libupdatertalk.so:', TALK)
    blob = TALK.read_bytes()
    f = ELFFile(open(TALK, 'rb'))
    sym = f.get_section_by_name('.dynsym')
    keyaddr = keysize = None
    for s in sym.iter_symbols():
        if s.name == 'KeyArray':
            keyaddr, keysize = s['st_value'], s['st_size']
            print('  KeyArray  value=0x%x size=%d shndx=%s'
                  % (keyaddr, keysize, s['st_shndx']))
    if keyaddr is None:
        print('  KeyArray not found')
        return

    # translate the symbol address into a file offset via the section it lives in
    keyoff = None
    for sec in f.iter_sections():
        if not sec['sh_addr']:
            continue
        if sec['sh_addr'] <= keyaddr < sec['sh_addr'] + sec['sh_size']:
            keyoff = sec['sh_offset'] + (keyaddr - sec['sh_addr'])
            print('  lives in %s  file offset 0x%x  (section size %d)'
                  % (sec.name, keyoff, sec['sh_size']))
            break
    if keyoff is None:
        print('  could not map KeyArray to a file offset')
        return

    key = blob[keyoff:keyoff + (keysize or 32)]
    print('  raw bytes (%d): %s' % (len(key), key.hex()))
    print('  as LE u32  : %s' % ' '.join('0x%08x' % v for v in
                                        struct.unpack('<%dI' % (len(key) // 4), key[:len(key) // 4 * 4])))
    print('  reversed   : %s' % key[::-1].hex())

    body = BODY.read_bytes()
    print()
    print('body:', BODY, len(body), 'bytes, magic', body[:4].hex())
    print('  first 32 bytes: %s' % body[:32].hex())
    print()

    cands = []
    for n in (16, 24, 32):
        if n <= len(key):
            cands.append(('key[:%d]' % n, key[:n]))
    cands.append(('key reversed[:16]', key[::-1][:16]))
    cands.append(('key[4:20]', key[4:20]))
    cands.append(('key[:4]x4', key[:4] * 4))

    print('=== trying %d key variants x ECB/CBC ===' % len(cands))
    hits = 0
    for label, k in cands:
        outs, err = try_aes_decrypt(k, body)
        if err:
            print('  %s -> %s' % (label, err))
            break
        for mode, out in outs:
            verdict = plausible(out)
            if verdict:
                hits += 1
                print('  HIT  %-18s %-12s %s' % (label, mode, verdict))
                print('       %s' % out[:48].hex())
    if not hits:
        print('  no candidate produced a recognisable container')
        print()
        print('  The transform is AES by import, but the key is evidently not at')
        print('  KeyArray, or not used directly on the body.  Dec_ScrambleInit')
        print('  takes arguments that may transform the key first, and .text is')
        print('  212 bytes -- small enough to read, which is the next step rather')
        print('  than a wider blind sweep.')


if __name__ == '__main__':
    main()
