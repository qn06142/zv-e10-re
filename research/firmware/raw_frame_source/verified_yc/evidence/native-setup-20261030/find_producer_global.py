from pathlib import Path
import struct,json,array,sys
sys.path.insert(0,'.local/work/yc-frame-contract-20261029');import rtos
b=rtos.DATA;base=rtos.BASE;h=array.array('H',b);target=0x64277f68;found=[]
for k,w in enumerate(h):
 if w&0xff00!=0x4400 or (w>>3)&15!=15:continue
 off=k*2;reg=(w&7)|((w>>4)&8);address=base+off
 for prev in range(max(0,off-40),off,2):
  a=h[prev//2];literal=None
  if a&0xf800==0x4800 and (a>>8)&7==reg:literal=((base+prev+4)&~3)+(a&255)*4
  elif a==0xf8df and h[prev//2+1]>>12==reg:literal=((base+prev+4)&~3)+(h[prev//2+1]&4095)
  if literal is None or not base<=literal<base+len(b)-3:continue
  dest=(rtos.word(literal)+address+4)&0xffffffff
  if target<=dest<target+0x40:found.append({'load':hex(base+prev),'add':hex(address),'literal':hex(literal),'target':hex(dest)})
p=Path('.local/outputs/yc-native-setup-20261030');p.joinpath('producer-global-pic-xrefs.json').write_text(json.dumps(found,indent=2));p.joinpath('producer-global-pic-contexts.txt').write_text('\n'.join(rtos.disasm(int(x['load'],16)-12,int(x['add'],16)+70) for x in found))
print(json.dumps(found,indent=2))
