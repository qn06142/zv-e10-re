"""Extract and dump the complete recovered MWF message vocabulary.

Uncovered from libMWF.so, libNetContUtil.so, and dumps/engine/libObj.so.
Solves Open Item 1 (Plugin Message Vocabulary) and Open Item 3 (Category 0x2000).
"""
import pathlib
import struct
import sys
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from annotate import load, load_segs, v2o, plt_map
from cpp_demangle import demangle
from mwf_ids import const_reg

def dump_mwf_core_tables():
    p = REPO / 'dumps' / 'camera_2025' / 'usr' / 'usr' / 'lib' / 'libMWF.so'
    data, f = load(p)
    segs = load_segs(f)

    tables = [
        ('m_baseMsgTbl (Base Object Lifecycle)', 0x428b8, 12, 'MWF::MwfTbl::m_baseMsgTbl'),
        ('m_pinMsgTbl (Pin IPC Messages)', 0x42918, 11, 'MWF::MwfTbl::m_pinMsgTbl'),
        ('m_pinParamTbl (Pin Parameters)', 0x42970, 4, 'MWF::MwfTbl::m_pinParamTbl'),
        ('m_pinDirTbl (Pin Directions)', 0x42990, 3, 'MWF::MwfTbl::m_pinDirTbl'),
    ]

    print("=" * 80)
    print("1. CORE MWF TABLES (libMWF.so)")
    print("=" * 80)
    for title, vaddr, count, sym in tables:
        off = v2o(segs, vaddr)
        print(f"\n--- {title} [{sym}] ({count} records) ---")
        for i in range(count):
            rec = data[off + i*8 : off + (i+1)*8]
            mid = int.from_bytes(rec[:4], 'little')
            saddr = int.from_bytes(rec[4:], 'little')
            soff = v2o(segs, saddr)
            sname = '?'
            if soff is not None:
                zero = data.find(b'\x00', soff)
                sname = data[soff:zero].decode('ascii', 'replace')
            print(f"  0x{mid:08x}  {sname}")

def dump_database_api_methods():
    p = REPO / 'dumps' / 'camera_2025' / 'usr' / 'usr' / 'lib' / 'libNetContUtil.so'
    data, f = load(p)
    segs = load_segs(f)
    plt = plt_map(f, data, segs)
    ds = f.get_section_by_name('.dynsym')
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

    print("\n" + "=" * 80)
    print("2. DATABASE CATEGORY (0x6000) CLIENT API (libNetContUtil.so)")
    print("=" * 80)

    rows = []
    for s in ds.iter_symbols() if ds else []:
        if s['st_info']['type'] != 'STT_FUNC' or not s['st_size']:
            continue
        v = s['st_value'] & ~1
        off = v2o(segs, v)
        if off is None:
            continue
        insns = list(md.disasm(data[off:off + s['st_size']], v))
        for i, ins in enumerate(insns):
            if ins.mnemonic in ('bl', 'blx') and ins.op_str.startswith('#'):
                tgt = int(ins.op_str[1:], 0) & ~1
                if tgt in plt and 'SetCateIdMsgId' in plt[tgt]:
                    r1, r2 = const_reg(insns, i, segs, data)
                    name = demangle(s.name)
                    short_name = name.split('NetDbIf::')[-1] if 'NetDbIf::' in name else name
                    rows.append((r1, r2, short_name))

    # Deduplicate and sort by message id
    rows = sorted(set(rows), key=lambda r: (r[0] or 0, r[1] or 0, r[2]))
    for cat, msg, fn in rows:
        c_str = f"0x{cat:04x}" if cat is not None else "?????"
        m_str = f"0x{msg:x}" if msg is not None else "?????"
        print(f"  cat={c_str}  msg={m_str:<8}  {fn}")

def dump_apicd_database_table():
    p = REPO / 'dumps' / 'engine' / 'libObj.so'
    data = p.read_bytes()

    print("\n" + "=" * 80)
    print("3. DATABASE DISPATCH TABLE (libObj.so APICD_* at 0x13ec720, stride 72)")
    print("=" * 80)

    records = []
    pos = 0x13ec720
    while pos < 0x13ed800:
        mid = int.from_bytes(data[pos:pos+4], 'little')
        saddr = int.from_bytes(data[pos+4:pos+8], 'little')
        if not (0x1000000 <= saddr <= 0x1200000):
            break
        zero = data.find(b'\x00', saddr)
        name = data[saddr:zero].decode('ascii', 'replace')
        if not name.startswith('APICD_'):
            break
        records.append((pos, mid, name))
        pos += 0x48

    print(f"Total APICD records: {len(records)}")
    for off, mid, name in records:
        print(f"  0x{mid:08x}  {name:<46} (0x{off:x})")

def dump_obj_cnt_mgr_table():
    p = REPO / 'dumps' / 'engine' / 'libObj.so'
    data = p.read_bytes()

    print("\n" + "=" * 80)
    print("4. OBJ_CNT_MGR (0x3700) MESSAGES (libObj.so ParseObjCommand)")
    print("=" * 80)

    seen = set()
    matches = []
    for s_off in range(0x104a2b0, 0x104a780):
        z = data.find(b'\x00', s_off)
        s = data[s_off:z]
        if s.startswith(b'ParseObjCommand( [') and s not in seen:
            seen.add(s)
            text = s.decode('ascii', 'replace')
            matches.append(text)

    for m in matches:
        print(f"  {m}")

def dump_obj_player_table():
    p = REPO / 'dumps' / 'engine' / 'libObj.so'
    data = p.read_bytes()

    print("\n" + "=" * 80)
    print("5. OBJ_PLAYER (0x3600) MESSAGES (libObj.so DefObjPlayer at 0x1365b00)")
    print("=" * 80)

    pos = 0x1365b08
    records = []
    while pos < 0x1365d30:
        mid = int.from_bytes(data[pos:pos+4], 'little')
        saddr = int.from_bytes(data[pos+4:pos+8], 'little')
        if not (0xe00000 <= saddr <= 0x1200000):
            break
        zero = data.find(b'\x00', saddr)
        name = data[saddr:zero].decode('ascii', 'replace')
        if not name.startswith('DefObjPlayer'):
            break
        records.append((mid, name.replace('DefObjPlayer::', '')))
        pos += 8

    # Deduplicate keeping order
    seen = set()
    for mid, name in records:
        if (mid, name) not in seen:
            seen.add((mid, name))
            print(f"  0x{mid:08x}  {name}")

def dump_obj_face_recorder_table():
    p = REPO / 'dumps' / 'engine' / 'libObj.so'
    data = p.read_bytes()

    print("\n" + "=" * 80)
    print("6. OBJ_FACE_RECORDER (0x3a44) DISPATCH TABLE (libObj.so at 0x13dc504, stride 24)")
    print("=" * 80)

    pos = 0x13dc504
    for _ in range(29):
        mid = int.from_bytes(data[pos:pos+4], 'little')
        reply_id = int.from_bytes(data[pos+4:pos+8], 'little')
        saddr = int.from_bytes(data[pos+12:pos+16], 'little')
        zero = data.find(b'\x00', saddr)
        name = data[saddr:zero].decode('ascii', 'replace')
        rep_str = f"-> reply 0x{reply_id:x}" if reply_id and reply_id != 0x750e else ""
        print(f"  0x{mid:08x}  {name:<40} {rep_str}")
        pos += 24

def main():
    dump_mwf_core_tables()
    dump_database_api_methods()
    dump_apicd_database_table()
    dump_obj_cnt_mgr_table()
    dump_obj_player_table()
    dump_obj_face_recorder_table()
    return 0

if __name__ == '__main__':
    sys.exit(main())
