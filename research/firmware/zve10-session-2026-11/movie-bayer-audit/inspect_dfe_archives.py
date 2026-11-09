"""Read-only inventory of archived DFE files, including ext2 directory walks."""
import argparse, hashlib, json, struct, tarfile
from pathlib import Path

def u16(b, o): return struct.unpack_from('<H', b, o)[0]
def u32(b, o): return struct.unpack_from('<I', b, o)[0]

class Ext2:
    def __init__(self, path):
        self.f = path.open('rb')
        s = self.read(1024, 1024)
        assert u16(s, 56) == 0xef53
        self.bs = 1024 << u32(s, 24)
        self.ipg = u32(s, 40)
        self.isize = u16(s, 88) if u32(s, 76) else 128
        self.gdt = (u32(s, 20) + 1) * self.bs
        assert not u32(s, 96) & (0x40 | 0x80), '64-bit or extents unsupported'

    def read(self, offset, size):
        self.f.seek(offset)
        b = self.f.read(size)
        assert len(b) == size
        return b

    def inode(self, n):
        g, i = divmod(n - 1, self.ipg)
        table = u32(self.read(self.gdt + g * 32, 32), 8)
        return self.read(table * self.bs + i * self.isize, self.isize)

    def blocks(self, ino):
        p = struct.unpack_from('<15I', ino, 40)
        yield from p[:12]
        def indirect(n, depth):
            if not n:
                yield from [0] * ((self.bs // 4) ** depth)
                return
            for v in struct.unpack('<%dI' % (self.bs // 4), self.read(n * self.bs, self.bs)):
                if depth == 1: yield v
                else: yield from indirect(v, depth - 1)
        for depth, n in enumerate(p[12:], 1): yield from indirect(n, depth)

    def contents(self, ino):
        size = u32(ino, 4)
        out = bytearray()
        for n in self.blocks(ino):
            if len(out) >= size: break
            out.extend(self.read(n * self.bs, self.bs) if n else bytes(self.bs))
        return bytes(out[:size])

    def directory(self, n):
        ino = self.inode(n)
        assert u16(ino, 0) & 0xf000 == 0x4000
        d = self.contents(ino)
        out = []
        offset = 0
        while offset < len(d):
            child, size, length = u32(d, offset), u16(d, offset + 4), d[offset + 6]
            assert size >= 8 and size % 4 == 0 and offset + size <= len(d)
            if child: out.append((d[offset+8:offset+8+length].decode('utf-8', 'replace'), child))
            offset += size
        return out

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('repo', type=Path)
    args = p.parse_args()
    root = args.repo / 'dumps'
    result = {'archives': [], 'filesystems': []}
    for path in sorted((root / 'trees').glob('*.tgz')):
        with tarfile.open(path) as t:
            for m in t.getmembers():
                if 'dfe' in m.name.lower():
                    row = dict(archive=str(path), member=m.name, size=m.size)
                    if m.isfile(): row['sha256'] = hashlib.sha256(t.extractfile(m).read()).hexdigest()
                    result['archives'].append(row)
    for path in [root/'nflasha15.img', root/'card/nflasha15.img', root/'nflasha7.img']:
        fs = Ext2(path)
        entries = fs.directory(2)
        row = dict(image=str(path), block_size=fs.bs, root=entries, dfe_entries=[])
        # /usr is a separate mount: its image root is the directory to inspect.
        for name, ino in entries:
            if 'dfe' in name.lower():
                child = fs.inode(ino)
                record = dict(name=name, inode=ino, mode=oct(u16(child, 0)), size=u32(child,4))
                if u16(child,0) & 0xf000 == 0x4000: record['children'] = fs.directory(ino)
                elif u16(child,0) & 0xf000 == 0x8000: record['sha256'] = hashlib.sha256(fs.contents(child)).hexdigest()
                row['dfe_entries'].append(record)
        result['filesystems'].append(row)
        fs.f.close()
    print(json.dumps(result, indent=2))

if __name__ == '__main__': main()
