from pathlib import Path
import struct,json,array
b=Path('outputs/uvc-startup-fix/candidate-1080p/av-cam.bin').read_bytes();base=0x635c6000
leads=json.loads(Path('outputs/yc-vga-test/resize-strings.json').read_text());targets={int(r['address'],16):r['text'] for r in leads};h=array.array('H',b);found=[]
for off in range(0,len(b)-2,2):
 word=h[off//2]
 if word&0xff00!=0x4400 or (word>>3)&15!=15:continue
 reg=(word&7)|((word>>4)&8);address=base+off
 for prev in range(max(0,off-48),off,2):
  w=h[prev//2];literal=None
  if w&0xf800==0x4800 and (w>>8)&7==reg:literal=((base+prev+4)&~3)+(w&255)*4
  elif w==0xf8df and prev+4<=off and h[prev//2+1]>>12==reg:literal=((base+prev+4)&~3)+(h[prev//2+1]&4095)
  if literal is None or not base<=literal<base+len(b)-3:continue
  value=struct.unpack_from('<I',b,literal-base)[0];dest=(value+address+4)&0xffffffff
  if dest in targets:found.append({'load':hex(base+prev),'add':hex(address),'literal':hex(literal),'target':hex(dest),'string':targets[dest]})
Path('outputs/yc-vga-test/resize-xrefs.json').write_text(json.dumps(found,indent=2));print('relative string refs',len(found))
for r in found:print(r['add'],r['string'][:130])
