from pathlib import Path
import math,json,struct,collections
b=Path('outputs/native-dmm-v28/decoder-handoff/zve10-vef295-snapshot.bin').read_bytes()
def corr(x,s):
 a=x[:-s];c=x[s:];ma=sum(a)/len(a);mc=sum(c)/len(c)
 den=sum((v-ma)**2 for v in a)*sum((v-mc)**2 for v in c)
 return sum((v-ma)*(w-mc) for v,w in zip(a,c))/math.sqrt(den) if den else 0
features={'byte5':[b[i+5] for i in range(0,len(b),64)],'byte9':[b[i+9] for i in range(0,len(b),64)]}
result={}
for name,f in features.items():
 scores={s:corr(f,s) for s in range(1,121)}
 result[name]={'top_lags':sorted(scores.items(),key=lambda x:-x[1])[:8],'lags_10_20_29_30_31_60':{s:scores[s] for s in [10,20,29,30,31,60]}}
packets=list(struct.iter_unpack('<8Q',b))
result['zero_W4_W5_packets']=sum(w[4]==w[5]==0 for w in packets)
result['W0_header_counts']=dict(collections.Counter(hex(w[0]>>48) for w in packets).most_common())
result['limits']='Statistics support 64-byte periodic structure and 30-block row hypothesis; do not prove bitstream semantics, 64 horizontal pixels per block, active live geometry or tear-free capture.'
Path('outputs/yc-codec-audit/packet-structure-verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
