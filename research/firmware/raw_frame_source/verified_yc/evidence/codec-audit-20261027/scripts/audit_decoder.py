from pathlib import Path
import json,collections,hashlib
from audit_decoder_functions import decode_block_luma64,decode_block_chroma64
b=Path('outputs/native-dmm-v28/decoder-handoff/zve10-vef295-snapshot.bin').read_bytes()
y=collections.Counter();c=collections.Counter();cbr=[];crr=[]
for off in range(0,len(b),64):
 _,ym=decode_block_luma64(b[off:off+64]);_,_,cm=decode_block_chroma64(b[off:off+64])
 y[ym['tokens']]+=1;c[cm['tokens']]+=1;cbr.append(cm['cb_base']);crr.append(cm['cr_base'])
r={'snapshot_sha256':hashlib.sha256(b).hexdigest(),'blocks':len(b)//64,'luma_residual_token_histogram':dict(sorted(y.items())),'chroma_token_histogram':dict(sorted(c.items())),'luma_blocks_with_fewer_than_56_tokens':sum(n for k,n in y.items() if k<56),'chroma_blocks_with_fewer_than_64_tokens':sum(n for k,n in c.items() if k<64),'chroma_base_model_ranges':{'Cb':[min(cbr),max(cbr)],'Cr':[min(crr),max(crr)]},'note':'Instrumented supplied decoder functions only; no output reconstruction regenerated; no camera access'}
Path('outputs/yc-codec-audit/decoder-audit.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
