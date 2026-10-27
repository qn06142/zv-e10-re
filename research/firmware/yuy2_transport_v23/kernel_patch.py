"""Build/revert the exact inspected Sony UVC kernel candidate; never install it."""
from pathlib import Path
import argparse, hashlib, io, json, struct
from elftools.elf.elffile import ELFFile

STOCK_MD5='5b59c2e62c80683d754955ab5de0467d'
FRAME_BYTES=640*480*2
PAYLOAD_BYTES=FRAME_BYTES+12
INTERVAL=1000000
MODULE_VERSION='yuy2_640_v23'

def digest(data):
 return {'bytes':len(data),'md5':hashlib.md5(data).hexdigest(),
         'sha256':hashlib.sha256(data).hexdigest()}

def edits(data):
 e=ELFFile(io.BytesIO(data))
 assert e['e_machine']=='EM_ARM' and e['e_type']=='ET_REL' and e.little_endian
 text=e.get_section_by_name('.text'); ro=e.get_section_by_name('.rodata')
 # All offsets are section-relative, never guessed file/loaded addresses.
 specs=[
  ('.text',0x11ec,bytes.fromhex('a83090e5'),bytes.fromhex('110000ea'),
   'Skip PAL/NTSC interval override; use the fixed probe interval (B 0x1238)'),
  ('.text',0xf44,bytes.fromhex('748048e2'),bytes.fromhex('728048e2'),
   'Set EOF on the one payload constituting this complete frame'),
  ('.rodata',0x7e,struct.pack('<I',333333),struct.pack('<I',INTERVAL),'Probe frame interval: 10 fps'),
  ('.rodata',0x8c,struct.pack('<I',14745600),struct.pack('<I',FRAME_BYTES),'Probe maximum pixel frame size'),
  ('.rodata',0x90,struct.pack('<I',300000),struct.pack('<I',PAYLOAD_BYTES),'Probe maximum one-header payload size'),
 ]
 # Reuse optional modinfo documentation storage without resizing ELF sections.
 # Runtime startup_mode parameter registration lives in __param, untouched.
 info=e.get_section_by_name('.modinfo').data();old=b'parmtype=startup_mode:uint\0'
 new=('version='+MODULE_VERSION).encode()+b'\0';assert len(new)<=len(old)
 assert info.count(old)==1 or info.count(new)==1
 offset=info.index(old) if old in info else info.index(new)
 specs.append(('.modinfo',offset,old,new.ljust(len(old),b'\0'),
               'Expose a loaded-module sysfs version marker; runtime parameters unchanged'))
 records=[]
 for section,offset,before,after,reason in specs:
  sec=e.get_section_by_name(section);file_offset=sec['sh_offset']+offset
  assert offset+len(before)<=sec['sh_size']
  # A loader relocation must never overwrite a patched instruction/constant.
  index=next(i for i,s in enumerate(e.iter_sections()) if s.name==section)
  for rel in e.iter_sections():
   if rel['sh_type']=='SHT_REL' and rel['sh_info']==index:
    assert not any(offset<=r['r_offset']<offset+len(before) for r in rel.iter_relocations())
  records.append(dict(section=section,offset=offset,file_offset=file_offset,
                      before=before.hex(),after=after.hex(),reason=reason))
 return records

def transform(data,reverse=False):
 records=edits(data);result=bytearray(data)
 for r in records:
  before=bytes.fromhex(r['after' if reverse else 'before'])
  after=bytes.fromhex(r['before' if reverse else 'after']);a=r['file_offset']
  if data[a:a+len(before)]!=before:raise ValueError(f'Guard mismatch: {r["section"]}+{r["offset"]:x}')
  result[a:a+len(after)]=after
 result=bytes(result)
 if hashlib.md5(result if reverse else data).hexdigest()!=STOCK_MD5:
  raise ValueError('Whole-module stock fingerprint mismatch')
 return result,records

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--input',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
 ap.add_argument('--reverse',action='store_true');args=ap.parse_args()
 if args.output.exists():raise SystemExit('Refusing to overwrite an existing artifact')
 data=args.input.read_bytes();result,records=transform(data,args.reverse)
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(result)
 report=dict(revision='2.3',status='BUILT_NOT_HARDWARE_TESTED',input=digest(data),output=digest(result),
             reverse=args.reverse,frame_bytes=FRAME_BYTES,payload_bytes=PAYLOAD_BYTES,
             interval_100ns=INTERVAL,edits=records)
 args.output.with_suffix('.patch.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
