"""Extract complete native allocations from revision 2.9 FFmpeg rawvideo output."""
import argparse, hashlib, json, struct, zlib
from pathlib import Path
PACKET=614400
HEADER=64
def decode(data):
    if len(data)%PACKET: raise ValueError('Truncated USB packet')
    groups={}
    for start in range(0,len(data),PACKET):
        p=data[start:start+PACKET]
        if p[:8]!=b'ZVYC0029': raise ValueError('Wrong patch/protocol')
        version,header,ident,seq,total,offset,n,crc,physical,flags,hcrc=struct.unpack_from('<11I',p,8)
        if version!=1 or header!=HEADER or not ident or not 0<total<=4*1024*1024 or flags!=1:
            raise ValueError('Invalid header')
        if zlib.crc32(p[:48])!=hcrc or any(p[52:64]): raise ValueError('Header checksum/reserved bytes')
        if offset>=total or offset%(PACKET-HEADER) or n!=min(PACKET-HEADER,total-offset):
            raise ValueError('Invalid chunk range')
        payload=p[HEADER:HEADER+n]
        if zlib.crc32(payload)!=crc or any(p[HEADER+n:]): raise ValueError('Payload checksum/padding')
        key=ident
        meta=(seq,total,physical)
        oldmeta,chunks=groups.setdefault(key,(meta,{}))
        if oldmeta!=meta: raise ValueError('Conflicting snapshot identity; do not concatenate camera sessions')
        if offset in chunks and chunks[offset]!=payload: raise ValueError('Conflicting duplicate')
        chunks[offset]=payload
    complete=[];incomplete=[]
    for ident,(meta,chunks) in groups.items():
        seq,total,physical=meta
        if sum(map(len,chunks.values()))!=total:
            incomplete.append(ident);continue
        raw=b''.join(chunks[o] for o in sorted(chunks))
        complete.append((ident,raw,dict(sequence=seq,bytes=total,physical=hex(physical),sha256=hashlib.sha256(raw).hexdigest(),completed_frame_guaranteed=False)))
    return complete,incomplete
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('input',type=Path);ap.add_argument('output',type=Path);a=ap.parse_args()
    complete,incomplete=decode(a.input.read_bytes());a.output.mkdir(parents=True,exist_ok=False)
    report={'complete':{},'incomplete_snapshot_ids':incomplete}
    for ident,raw,meta in complete:
        name=f'snapshot-{ident:08d}.bin';(a.output/name).write_bytes(raw);report['complete'][name]=meta
    (a.output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
