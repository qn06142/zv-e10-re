"""Read-only FAT12 reachability analysis of the backed-up camera /tmp volume."""
from pathlib import Path
import struct,hashlib,json,argparse
ap=argparse.ArgumentParser();ap.add_argument('--stem',default='tmp-volume-preflash');a=ap.parse_args()
O=Path('.local/outputs/vga-v37/deployment');p=O/(a.stem+'.bin');b=p.read_bytes()
expected=(O/(a.stem+'.md5')).read_text().split()[0];assert hashlib.md5(b).hexdigest()==expected
u16=lambda a:struct.unpack_from('<H',b,a)[0]
bps=u16(11);spc=b[13];res=u16(14);fats=b[16];roots=u16(17);sectors=u16(19);spf=u16(22)
assert bps==512 and spc==32 and fats==1 and sectors==24576 and len(b)==sectors*bps
rootstart=(res+fats*spf)*bps;rootbytes=roots*32;data=rootstart+rootbytes;cb=bps*spc;clusters=(len(b)-data)//cb
fat=b[res*bps:(res+spf)*bps]
def nextc(n):
 x=int.from_bytes(fat[n+n//2:n+n//2+2],'little');return (x>>4 if n&1 else x)&0xfff
owners={};errors=[];files=[]
def chain(n,path):
 out=[]
 while 2<=n<clusters+2:
  if n in out:errors.append('cycle:'+path);break
  if n in owners:errors.append('crosslink:'+path+':'+owners[n]);break
  owners[n]=path;out.append(n);n=nextc(n)
 if out and n<0xff8:errors.append('invalid_chain_terminal:'+path+':'+hex(n))
 return out
def walk(buf,parent):
 for i in range(0,len(buf),32):
  e=buf[i:i+32]
  if not e[0]:break
  if e[0]==0xe5 or e[11]==0xf or e[11]&8:continue
  name=e[:8].decode('ascii',errors='replace').rstrip();ext=e[8:11].decode('ascii',errors='replace').rstrip()
  if name in ['.','..']:continue
  if ext:name+='.'+ext
  path=parent+'/'+name;n=struct.unpack_from('<H',e,26)[0];size=struct.unpack_from('<I',e,28)[0];c=chain(n,path)
  files.append(dict(path=path,bytes=size,clusters=len(c),first_cluster=n,attributes=hex(e[11])))
  if e[11]&16:walk(b''.join(b[data+(x-2)*cb:data+(x-1)*cb] for x in c),path)
  elif len(c)*cb<size:errors.append('chain_shorter_than_file:'+path)
walk(b[rootstart:rootstart+rootbytes],'')
allocated={n for n in range(2,clusters+2) if nextc(n)!=0};free=set(range(2,clusters+2))-allocated
orphan=allocated-set(owners);bad={n for n in orphan if nextc(n)==0xff7}
report=dict(read_only_analysis=True,volume_md5=expected,volume_bytes=len(b),cluster_bytes=cb,total_clusters=clusters,
 free_clusters=len(free),reachable_clusters=len(owners),unreachable_allocated_clusters=len(orphan),
 unreachable_allocated_bytes=len(orphan)*cb,bad_or_reserved_unreachable_clusters=sorted(bad),errors=errors,
 files=files,unreachable_cluster_indices=sorted(orphan),
 limitations=['No filesystem repair or raw write performed.','Unreachable allocation is not itself proof of why it occurred or which camera crashes it explains.','No pre-cleanup raw FAT image exists; timing of orphan allocation cannot be assigned.','The live mounted volume was read without freezing its writers.'])
(O/('fat-reachability-analysis.json' if a.stem=='tmp-volume-preflash' else a.stem+'-analysis.json')).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ['files','unreachable_cluster_indices']},indent=2))
