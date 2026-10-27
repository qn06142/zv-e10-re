from pathlib import Path
import struct,json,collections
from instrumented_candidate import decode_block_luma64,decode_block_chroma64
result=[]
for path in sorted(Path('outputs/native-dmm-v28/capture-first-01').glob('frame-*.bin')):
 counts=collections.Counter();examples=[]
 b=path.read_bytes()
 for index in range(len(b)//64):
  block=b[index*64:index*64+64];w=struct.unpack('<8Q',block)
  if w[4] or w[5]:continue
  counts['isolated_blocks']+=1
  _,y=decode_block_luma64(block);_,_,c=decode_block_chroma64(block)
  if y['ones_left']:counts['luma_nonzero_bits_unparsed']+=1
  if c['ones_left']:counts['chroma_nonzero_bits_unparsed']+=1
  if y['consumed']+c['consumed']>512:counts['candidate_streams_overlap_by_bit_budget']+=1
  if not y['ones_left'] and y['tokens']==56:counts['luma_56_tokens_and_zero_tail']+=1
  if not c['ones_left'] and c['tokens']==64:counts['chroma_64_tokens_and_zero_tail']+=1
  if len(examples)<3 and y['ones_left'] and c['ones_left']:examples.append({'block':index,'luma':y,'chroma':c})
 result.append({'file':path.name,'counts':dict(counts),'examples':examples})
 print(path.name,dict(counts))
Path('outputs/yc-codec-recovery/bit-accounting.json').write_text(json.dumps(result,indent=2)+'\n')
