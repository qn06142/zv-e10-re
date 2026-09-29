"""Catalogue every ELF on the camera, then link them into a picture.

The point
---------
Three documented claims in this project turned out to be wrong because they were
inherited rather than checked: that av-cam.bin was encrypted, that
libupdatercommon.so was encrypted, and that /usr/bin was read-only squashfs.
Each was load-bearing and each was cheap to test.  So before deciding what to do
next, the honest move is to stop reasoning from notes and get an inventory that
was measured.

What this produces
------------------
1. A catalog of every ELF found in the dumps: type, machine, whether it is
   stripped, what it needs, what it exports, what it imports.
2. A dependency graph, so that "which library actually talks to which" is a
   question about data rather than about recollection.
3. A grouped view: the service-side tools, the libraries, the application-side
   binaries, and the firmware blobs -- because they are different kinds of thing
   and lumping them together is what produced the bad claims.

Deliberately not done here
-------------------------
No disassembly.  Everything below comes from ELF headers and symbol tables, which
is reading the file's own index of itself.  That is the distinction that let the
GetBody/ReleaseBody contract be found without a disassembler, and it is the line
this script stays on.
"""
import collections
import csv
import json
import pathlib
import re
import struct
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
DUMPS = [
    REPO / 'dumps' / 'camera_2025',
    REPO / 'dumps' / 'v203',
    REPO / 'dumps' / 'engine',
    REPO / 'dumps' / 'camera',
    REPO / 'dumps' / 'camtools',
    REPO / 'fw',
    REPO / 'udtrbody_extract',
    REPO / 'tools',
]

ET_EXEC, ET_DYN = 2, 3
EM_ARM = 40
NON_ELF_EXT = {'.txt', '.md', '.sh', '.xml', '.conf', '.c', '.py', '.json',
               '.tsv', '.csv', '.log', '.bin.bak'}


def elf_info(path):
    """everything we want to know, from headers and symbol tables only"""
    try:
        data = path.read_bytes()
    except Exception:
        return None
    if len(data) < 52 or data[:4] != b'\x7fELF':
        return None
    try:
        from elftools.elf.elffile import ELFFile
        import io
        f = ELFFile(io.BytesIO(data))
    except Exception as e:
        return {'error': str(e), 'size': len(data)}

    out = {'size': len(data)}
    # e_type and e_machine are read straight out of the header bytes rather than
    # through pyelftools.  The first version used the library and reported
    # "0 executables, 648 non-ARM" for a filesystem that is entirely ARM: the
    # header is fine, but pyelftools' section walk raises on 153 of these files
    # and taking the type from that path lost it.  Two fields at a fixed offset
    # do not need a section table, which is exactly what is missing.
    ei_class, ei_data = data[4], data[5]
    e = '<' if ei_data == 1 else '>'
    e_type, e_machine = struct.unpack(e + 'HH', data[16:20])
    out['class'] = {1: 'ELF32', 2: 'ELF64'}.get(ei_class, str(ei_class))
    out['type'] = {0: 'NONE', 1: 'REL', 2: 'EXEC', 3: 'DYN', 4: 'CORE'} \
        .get(e_type, str(e_type))
    out['machine'] = 'ARM' if e_machine in (40, 183) else str(e_machine)
    out['entry'] = struct.unpack(e + 'I', data[24:28])[0]

    # Not every file that begins with the ELF magic is a usable ELF.  One of the
    # dumps has a section header table pointing past EOF, and a single such file
    # aborted the whole catalog on the first run.  Anything that cannot be walked
    # is recorded with its header fields and an error, and the walk continues --
    # a malformed entry is a fact about the camera, not a reason to stop looking.
    try:
        sections = list(f.iter_sections())
    except Exception as e:
        out['stripped'] = None
        out['needed'] = []
        out['soname'] = None
        out['exp_func'] = out['exp_obj'] = out['imports'] = 0
        out['c_exports'] = []
        out['error'] = 'section table unreadable: %s' % e
        return out
    out['stripped'] = f.get_section_by_name('.symtab') is None

    byoff = {s['sh_offset']: s for s in sections}
    needed, soname = [], None
    for sec in sections:
        if sec['sh_type'] == 'SHT_DYNAMIC':
            try:
                for tag in sec.iter_tags():
                    if tag.entry.d_tag == 'DT_NEEDED':
                        needed.append(str(tag.needed))
                    elif tag.entry.d_tag == 'DT_SONAME':
                        soname = str(tag.soname)
            except Exception as e:
                out.setdefault('notes', []).append('dynamic: %s' % e)
    out['needed'] = needed
    out['soname'] = soname

    ds = f.get_section_by_name('.dynsym')
    exp_f = exp_o = imp = 0
    exports = []
    if ds:
        try:
            syms = list(ds.iter_symbols())
        except Exception as e:
            syms = []
            out.setdefault('notes', []).append('dynsym: %s' % e)
        for s in syms:
            if not s.name:
                continue
            t = s['st_info']['type']
            if s['st_shndx'] == 'SHN_UNDEF':
                imp += 1
            else:
                if t == 'STT_FUNC':
                    exp_f += 1
                elif t == 'STT_OBJECT':
                    exp_o += 1
                # an unmangled C name in a DYN is the interesting case: those are
                # the dlsym contracts, not C++ noise
                if t == 'STT_FUNC' and not s.name.startswith('_Z') \
                        and not s.name.startswith('__'):
                    exports.append(s.name)
    out['exp_func'] = exp_f
    out['exp_obj'] = exp_o
    out['imports'] = imp
    out['c_exports'] = exports
    return out


def walk():
    seen = {}
    for root in DUMPS:
        if not root.exists():
            continue
        for p in root.rglob('*'):
            if not p.is_file():
                continue
            if p.suffix.lower() in NON_ELF_EXT:
                continue
            try:
                if p.open('rb').read(4) != b'\x7fELF':
                    continue
            except Exception:
                continue
            rel = str(p.relative_to(REPO))
            if rel in seen:
                continue
            seen[rel] = p
    return seen


def main():
    files = walk()
    print('ELF files found in dumps: %d' % len(files))

    rows = []
    broken = []
    for rel, p in sorted(files.items()):
        info = elf_info(p)
        if info is None or 'error' in info and 'type' not in info:
            print('  UNREADABLE %s  %s' % (rel, info))
            continue
        if 'error' in info:
            broken.append((rel, info))
        rows.append((rel, info))

    out = REPO / 'research' / 'firmware' / 'elf_catalog.json'
    out.write_text(json.dumps({r: i for r, i in rows}, indent=1), encoding='utf-8')
    print('catalog -> %s' % out)

    execs = [(r, i) for r, i in rows if i.get('type') in ('EXEC', 'DYN')
             and pathlib.Path(r).suffix not in ('.so',)
             and '_SCN_' not in r]
    libs = [(r, i) for r, i in rows if i.get('type') == 'DYN'
            or i.get('type') == 'REL' or r.endswith('.so')]
    print()
    print('  executables: %d    libraries/objects: %d' % (len(execs), len(libs)))
    nostrip = [r for r, i in rows if not i.get('stripped')]
    print('  unstripped (have .symtab): %d of %d' % (len(nostrip), len(rows)))
    bad = [(r, i) for r, i in rows if i.get('machine') != 'ARM']
    print('  non-ARM: %d %s' % (len(bad), [r for r, _ in bad][:5]))
    ty = collections.Counter(i.get('type') for _r, i in rows)
    print('  e_type: %s' % dict(ty))
    if broken:
        print('  ELF magic but unusable section table: %d' % len(broken))
        for r, i in broken[:10]:
            print('      %-58s %s' % (r.split('dumps/')[-1],
                                      i.get('error', '?')[:60]))

    # the contract symbols: unmangled C exports are what a dlsym can ask for
    print()
    print('=== unmangled C exports (dlsym contracts) ===')
    for r, i in rows:
        if i.get('c_exports'):
            print('  %-58s %s' % (r.split('dumps/')[-1], ', '.join(i['c_exports'][:8])))

    print()
    print('=== functional clusters, by what each library exports ===')
    CLUSTERS = [
        ('UIPC / message bus', ('uipc', 'osal_snd', 'u_osal_', 'UIPC_')),
        ('USB device stack', ('Msc', 'Mtp', 'Ptp', 'Usb', 'usbcmd', 'usb_',
                              'Streaming', 'ExtCmdSvc', 'usbcmd')),
        ('network / remote / http', ('Net', 'Remote', 'Dlna', 'http', 'Wlan',
                                     'wlan', 'ipsec', 'ssh', 'Ipsec')),
        ('bluetooth', ('BTA_', 'bt_', 'Bluetooth', 'bsa_', 'GAP_', 'gap_')),
        ('firmware updater', ('udtr_', 'Dec_Scramble', 'GetBody', 'Update',
                              'Updater')),
        ('scenario plugins', ('scenario_run',)),
        ('camera application / views', ('View', 'ToInstance', 'Caution',
                                        'ModelCaution', 'mpr', 'Mpr')),
        ('sensor / lens / media', ('Lens', 'lens', 'sen_', 'SMF', 'smf_',
                                   'mcmn', 'Meta', 'Obj')),
        ('logging / diagnostics', ('ulog', 'Ulogio', 'ulogio', 'KikiLog',
                                   'AccessLog', 'blog', 'mon_', 'Mon')),
        ('settings / nvram', ('Backup_', 'IMDB_', 'CapIdSync', 'mcmn_param')),
    ]
    for title, keys in CLUSTERS:
        members = []
        for r, i in rows:
            blob = pathlib.Path(r).name + ' ' + ' '.join(i.get('c_exports', []))
            if any(k in blob for k in keys):
                members.append((r, i))
        if not members:
            continue
        print('  %-28s %3d members' % (title, len(members)))
        for r, i in sorted(members, key=lambda x: -x[1]['size'])[:6]:
            ex = [e for e in i.get('c_exports', [])
                  if not e.startswith('_')][:3]
            print('      %8d  %-42s %s' % (i['size'],
                                           pathlib.Path(r).name[:42],
                                           ', '.join(ex)[:60]))
        if len(members) > 6:
            print('      ... and %d more' % (len(members) - 6))

    print()
    print('=== who links the message bus (libosal_uipc) ===')
    for r, i in rows:
        if any('uipc' in n for n in i.get('needed', [])):
            ex = [e for e in i.get('c_exports', []) if not e.startswith('_')][:4]
            print('  %-46s %s' % (pathlib.Path(r).name[:46], ', '.join(ex)[:50]))

    print()
    print('=== most-depended-upon libraries (NEEDED hubs) ===')
    cnt = collections.Counter()
    for r, i in rows:
        for n in i.get('needed', []):
            cnt[n] += 1
    for n, c in cnt.most_common(18):
        print('  %-42s needed by %d' % (n, c))

    print()
    print('=== libraries nothing in the dumps needs ===')
    providers = set()
    for r, i in rows:
        for n in i.get('needed', []):
            providers.add(n)
    orphans = []
    for r, i in rows:
        base = pathlib.Path(r).name
        son = i.get('soname') or base
        if son not in providers and base not in providers and i.get('type') == 'DYN':
            orphans.append((r, i['size']))
    for r, s in sorted(orphans, key=lambda x: -x[1])[:20]:
        print('  %9d  %s' % (s, r.split('dumps/')[-1]))
    print('  (%d of %d shared objects are not NEEDED by anything catalogued)'
          % (len(orphans), sum(1 for _r, i in rows if i.get('type') == 'DYN')))


if __name__ == '__main__':
    main()
