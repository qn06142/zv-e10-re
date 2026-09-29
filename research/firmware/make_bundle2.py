"""Package the uxc resources and the small relevant binaries for a second pass.

The user wants to hand this to another agent, so the bundle has to be
self-contained and immediately usable.  Two things matter for that:

  * the raw bytes, unmodified, so conclusions can be checked from scratch
  * a short findings file, because two of my own earlier conclusions here were
    wrong and the reader should not have to rediscover which parts to trust

What goes in, and why:

  color_cmn.uxc        312 B    DECODED AND VERIFIED ON HARDWARE.  The one
                               confirmed-editable file.  Ships with both the
                               stock file and the magenta build, so the proven
                               edit is visible as a diff.
  style_cmn.uxc      1,888 B    Record layout solved this session: stride 36,
                               index u8 at +0, RGBA at +12, alpha always ff,
                               17 distinct quads, 26 records in 5 sections.
  view*.uxc         ~290 files  Record NOT solved.  Different record type from
                               style_cmn; a0 07 26 08 appears in 1 of 299.
  global.xdb       12,252 B    Resource directory, absolute /usr/share/app
                               paths, _43/_169 model pairings.
  lang.uxb, style.uxb         Directory tables, u32 offsets, 0 printable runs.
  logo.bin          8,532 B    Plain JFIF JPEG, the startup logo.  Needs no
                               format knowledge; the cheapest target left.
  fontlist.dat        360 B    Plain text, FONT_<name><9>/path.

Binaries -- the ones that plausibly contain the uxc parser, small enough to
include whole:

  im.elf            23,240     the imaging daemon, pid 157, holds 417 of the
                               857 uipc message queues.  Imports the osal msg
                               API and IMDB_find_entry.
  libIMDB.so        37,044     turns out to be a kernel module loader, not a
                               command-id table.  Names 16 .ko paths.
  libtestcmd.so     10,128     Sony's testcmd/uipc message interface, decoded
                               in docs/TESTCMD_INTERFACE.md.
  sndcmd.elf / rcvcmd.elf / testcmd.elf   the uipc CLI tools
  ko_stream.ko       3,384     stream_mmap, stream_ioctl (not a display surface)
  ko_stream2.ko      4,144     same, larger ioctl
  ko_dmm.ko         85,588     198 functions, no ldec symbols

Excluded deliberately: the multi-hundred-megabyte flash images and the decrypted
firmware.  If the second agent needs those they are on the SD card and in
dumps/ -- listed in the README rather than duplicated here.

The findings file states what is proven, what is unsolved, and which of my own
earlier claims were wrong, so the work starts from the current state rather than
from the record of the mistakes.
"""
import base64
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

REPO = Path(r'D:\02_Development_And_Projects\pmca-re')
OUT = REPO / 'out' / 'zv_e10_uxc_research.zip'
STAGE = REPO / 'out' / 'stage'

UXC = REPO / 'dumps' / 'camera_2025' / 'usr_share_app.tgz'
CAM = REPO / 'dumps' / 'camera'

# proven-edit files, shipped with provenance
PALETTE_FILES = [
    (CAM / 'app' / 'color_cmn.uxc', 'color_cmn.STOCK.uxc',
     'pristine, md5 f468bd3e72ca4e5b948a1c9f1f35c0a1'),
    (CAM / 'app' / 'color_cmn.restore.uxc', 'color_cmn.STOCK.restore.uxc',
     'byte-identical copy of the above, kept as the rollback artifact'),
    (CAM / 'app' / 'color_cmn.out.uxc', 'color_cmn.BLUE_BUILD.uxc',
     'id 0x4009 -> 00ffff, id 0x400c -> 0000dd @80. Guides went BLUE.'),
    (CAM / 'app' / 'color_cmn.magenta.uxc', 'color_cmn.MAGENTA_BUILD.uxc',
     'id 0x400c -> ff00ff @80. Guides went MAGENTA. Control test.'),
]

BINARIES = [
    (CAM / 'im.elf', 'im.elf', 'imaging daemon, pid 157, 417 of 857 uipc queues'),
    (CAM / 'libIMDB.so', 'libIMDB.so', 'kernel module loader, not a cmd-id table'),
    (CAM / 'libtestcmd.so', 'libtestcmd.so', 'Sony testcmd/uipc interface'),
    (CAM / 'bin_sndcmd.elf', 'sndcmd.elf', 'uipc send tool'),
    (CAM / 'bin_rcvcmd.elf', 'rcvcmd.elf', 'uipc receive tool'),
    (CAM / 'bin_testcmd.elf', 'testcmd.elf', 'uipc test tool'),
    (CAM / 'ko_stream.ko', 'stream.ko', 'stream_mmap + stream_ioctl'),
    (CAM / 'ko_stream2.ko', 'stream2.ko', 'stream2, larger ioctl'),
    (CAM / 'ko_dmm.ko', 'dmm.ko', '198 functions, no ldec symbols'),
]

SMALL_UXC = ['style_cmn.uxc', 'lang_cmn.uxc', 'global.xdb', 'lang.uxb',
             'style.uxb', 'fontlist.dat']


def md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def add(z, arc, data, note=None):
    z.writestr(arc, data)
    if note:
        z.writestr(arc + '.README', note)


def main():
    import tarfile
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)

    t = tarfile.open(UXC)
    have = {m.name.split('/')[-1]: m for m in t.getmembers() if m.isfile()}

    n_uxc = 0
    with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        # 1. the proven palette files, with provenance
        for src, arc, note in PALETTE_FILES:
            if src.exists():
                add(z, 'palette/' + arc, src.read_bytes(),
                    '%s\nmd5 %s\n' % (note, md5(src)))
        # 2. style_cmn is solved; include it standalone
        for name in SMALL_UXC:
            m = have.get(name)
            if m:
                b = t.extractfile(m).read()
                add(z, 'resources/' + name, b, 'md5 %s\n' % hashlib.md5(b).hexdigest())
        # 3. all view files, and the image sets
        for name, m in sorted(have.items()):
            if name.startswith('view') or name.startswith('image') or \
               name.startswith('master') or name.startswith('IRShooting') or \
               name.startswith('LayoutMaster'):
                z.writestr('uxc/' + name, t.extractfile(m).read())
                n_uxc += 1
        # 4. logo
        logo = REPO / 'dumps' / 'card' / 'logo.bin'
        if logo.exists():
            add(z, 'resources/logo.bin', logo.read_bytes(),
                'startup logo, plain JFIF JPEG\nmd5 %s\n' % md5(logo))
        # 5. binaries
        for src, arc, note in BINARIES:
            if src.exists():
                add(z, 'bin/' + arc, src.read_bytes(),
                    '%s\nmd5 %s\n' % (note, md5(src)))
        # 6. the scripts that produced the findings
        fdir = REPO / 'research' / 'firmware'
        for s in ('uxc_color.py', 'uxc_tlv.py', 'uxc_style_field.py',
                  'uxc_views.py', 'uxc_view_rec.py', 'uxc_inline.py',
                  'uxc_xref_full.py', 'uxc_loader_hunt.py', 'uxc_shift.py',
                  'uxc_widget_rec.py', 'uxc_style_derive.py',
                  'uxc_style_rec.py', 'uxc_recheck.py', 'uxc_format.py',
                  'uxc_style.py', 'uxc_xref.py'):
            p = fdir / s
            if p.exists():
                z.writestr('scripts/' + s, p.read_bytes())
        # 7. docs
        for d in ('RESULT_PALETTE.md', 'PALETTE_CONFIRMED.md',
                  'UXC_STYLE_STATUS.md', 'UI_RESOURCES.md',
                  'ROOT_FS_WRITABLE.md', 'TESTCMD_INTERFACE.md',
                  'DISPLAY_SURFACES.md', 'VDF_FINDINGS.md'):
            p = REPO / 'docs' / d
            if p.exists():
                z.writestr('docs/' + d, p.read_bytes())
        # 8. the handoff README, at the zip root
        rd = REPO / 'out' / 'README_HANDOFF.md'
        if rd.exists():
            z.writestr('README.md', rd.read_bytes())
        # 9. a manifest so the second agent can verify what they got
        z.writestr('MANIFEST.json', json.dumps({
            'palette_files_verified_on_hardware': [
                {'arc': a, 'md5': md5(s), 'note': n} for s, a, n in PALETTE_FILES],
            'style_cmn_layout': {
                'stride': 36, 'index_offset': 0, 'rgba_offset': 12,
                'marker': 'a0072608', 'records': 26, 'sections': 5,
                'alpha': 'always 0xff', 'distinct_quads': 17,
            },
            'view_layout': 'UNSOLVED - different record type from style_cmn',
            'binaries': [{'arc': a, 'note': n} for _s, a, n in BINARIES],
            'not_included': 'flash images and decrypted firmware; see README',
        }, indent=2))

    size = OUT.stat().st_size
    print('=== %s' % OUT)
    print('  %.2f MB' % (size / 1048576))
    with zipfile.ZipFile(OUT) as z:
        names = z.namelist()
        print('  %d entries' % len(names))
        cats = {}
        for nm in names:
            c = nm.split('/')[0] if '/' in nm else '(root)'
            cats[c] = cats.get(c, 0) + 1
        for c, n in sorted(cats.items()):
            print('    %-12s %4d' % (c, n))
        print()
        print('  uxc view/image files: %d' % n_uxc)
        for nm in sorted(names):
            if not nm.endswith('/README') and 'uxc/' not in nm and \
               'docs/' not in nm and 'scripts/' not in nm:
                print('    %s' % nm)


if __name__ == '__main__':
    main()
