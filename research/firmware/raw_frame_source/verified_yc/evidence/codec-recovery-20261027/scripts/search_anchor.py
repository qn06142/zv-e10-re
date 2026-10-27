from pathlib import Path
import struct,math,json
b=Path('outputs/native-dmm-v28/decoder-handoff/zve10-vef295-snapshot.bin').read_bytes()
words=[w[0] for w in struct.iter_unpack('<8Q',b)]
# Sample every third row to reduce search cost; score neighboring row pairs.
idx=[i for i in range(0,len(words)-30) if (i//30)%3==0]
def parse(w,start,k,kind,pol):
 p=start;q=0
 while p<63 and ((w>>(63-p))&1)==pol:q+=1;p+=1
 if p==63:return None
 p+=1;n=k+q if kind=='eg' else k
 if p+n>64 or q>20:return None
 r=(w>>(64-p-n))&((1<<n)-1) if n else 0
 return (((1<<q)-1)<<k)+r if kind=='eg' else (q<<k)+r
results=[]
for start in range(8,25):
 for kind in ['eg','rice','raw']:
  for k in (range(0,8) if kind!='raw' else range(7,13)):
   for pol in ([0,1] if kind!='raw' else [0]):
    vals=[];bad=False
    for w in words:
     v=parse(w,start,k,kind,pol) if kind!='raw' else ((w>>(64-start-k))&((1<<k)-1))
     if v is None:bad=True;break
     vals.append(v)
    if bad or max(vals)>4095:continue
    for signed in [False,True]:
     v=[((n+1)//2 if n&1 else -(n//2)) for n in vals] if signed else vals
     mean=sum(v)/len(v);std=math.sqrt(sum((n-mean)**2 for n in v)/len(v))
     if std<3 or len(set(v))<24:continue
     # Differences across pixels represented at same block position on adjacent rows.
     diffs=[abs(v[i]-v[i+30]) for i in idx]
     score=sum(diffs)/len(diffs)/std
     results.append(dict(start=start,kind=kind,k=k,polarity=pol,signed=signed,score=score,range=[min(v),max(v)],mean=mean,std=std,distinct=len(set(v))))
results.sort(key=lambda r:r['score'])
Path('outputs/yc-codec-recovery/anchor-search.json').write_text(json.dumps(results[:100],indent=2)+'\n')
print(json.dumps(results[:16],indent=2))
