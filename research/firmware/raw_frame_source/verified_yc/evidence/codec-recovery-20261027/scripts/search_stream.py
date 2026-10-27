from pathlib import Path
import struct,json
b=Path('outputs/native-dmm-v28/decoder-handoff/zve10-vef295-snapshot.bin').read_bytes()
rows=[]
for i,w in enumerate(struct.iter_unpack('<8Q',b)):
 if w[4] or w[5]:continue
 rows.append((''.join(f'{w[k]:064b}' for k in [0,2,3]),''.join(f'{w[k]:064b}'[::-1] for k in [1,7,6])))
rows=rows[::9]
def parse(s,p,n,k,kind,pol):
 for _ in range(n):
  q=0
  while p<len(s) and s[p]==pol:p+=1;q+=1
  if p==len(s):return -1
  p+=1
  suffix=k+q if kind=='eg' else k
  p+=suffix
  if p>len(s):return -1
 return p
out={}
for stream in (0,1):
 ranked=[]
 for offset in range(0,41):
  for count in [15,16,30,31,32,47,48,62,63,64]:
   for kind in ['eg','rice']:
    for k in range(3):
     for pol in ['0','1']:
      valid=exact=0;lefts=[]
      for pair in rows:
       s=pair[stream];p=parse(s,offset,count,k,kind,pol)
       if p<0:continue
       valid+=1
       if '1' not in s[p:]:exact+=1;lefts.append(p-(len(s.rstrip('0'))))
      if exact:ranked.append(dict(offset=offset,count=count,kind=kind,k=k,polarity=pol,valid=valid,exact_zero_tail=exact,mean_trailing_zero_consumed=sum(lefts)/len(lefts)))
 ranked.sort(key=lambda x:(-x['exact_zero_tail'],x['mean_trailing_zero_consumed']))
 out[str(stream)]=ranked[:40]
 print('stream',stream,'fixtures',len(rows));print(json.dumps(ranked[:12],indent=2))
Path('outputs/yc-codec-recovery/stream-search.json').write_text(json.dumps(out,indent=2)+'\n')
