from pathlib import Path
import json
from reassemble import decode,PACKET
p=Path('outputs/native-dmm-v29');raw=(p/'fixture-packets.bin').read_bytes()
complete,incomplete=decode(raw)
assert not incomplete and len(complete)==1
expected=bytes((i*31+(i>>9))&255 for i in range(2073600))
assert complete[0][1]==expected
checks=['full 2073600-byte original reconstructed exactly']
assert decode(raw[:PACKET])[0]==[];checks.append('partial snapshot never exported')
assert decode(raw+raw[:PACKET])[0][0][1]==expected;checks.append('identical retransmit accepted')
for kind in ['payload','header','truncated','wrong revision','padding']:
    bad=bytearray(raw)
    if kind=='payload':bad[64]^=1
    if kind=='header':bad[24]^=1
    if kind=='truncated':bad.pop()
    if kind=='wrong revision':bad[0]^=1
    if kind=='padding':bad[-1]=1
    try:decode(bad)
    except ValueError:pass
    else:raise AssertionError(kind)
    checks.append(kind+' rejected')
(p/'host-reassembly-verification.json').write_text(json.dumps({'camera_access':False,'passed':len(checks),'cases':checks},indent=2)+'\n')
print('\n'.join(checks))
