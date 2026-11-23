"""Decode the bounded YC38RJ01 rejection record. Never contacts a camera."""
from pathlib import Path
import argparse,hashlib,json,struct
REASONS={1:'metadata_size_outside_32_to_65536',2:'two_reads_differ',4:'image_category_parse_failed',
 8:'state_category_parse_failed',16:'multi_segment_present_or_malformed',32:'pixel_type_is_not_0x295',
 64:'pixel_handle_is_zero',128:'pixel_handle_aliases_metadata_handle'}
def categories(b):
 if len(b)<32:return dict(error='short_header')
 word=lambda off:struct.unpack_from('<I',b,off)[0]
 magic,version,count,off=word(0),word(8),word(12),word(16)
 out=dict(magic_hex=f'{magic:08x}',version=version,count=count,entries=[])
 if magic!=0x43595353 or version!=1:out['error']='unexpected_header';return out
 if count>64:out['error']='excessive_category_count';return out
 seen=set()
 for i in range(count):
  if off in seen or off<32 or off+32>len(b):out['error']='invalid_entry_link';return out
  seen.add(off);mark,cate,_,data,n,nxt=struct.unpack_from('<6I',b,off)
  if mark!=0x59525445 or data<32 or data>len(b) or n>len(b)-data:out['error']='invalid_entry';return out
  out['entries'].append(dict(category=cate,offset=data,bytes=n,prefix_hex=b[data:data+min(n,64)].hex()))
  off=nxt
 return out
def decode(raw):
 if len(raw)<80 or raw[:8]!=b'YC38RJ01':raise ValueError('Not a complete YC38RJ01 header')
 values=struct.unpack_from('<18I',raw,8)
 version,header,n,declared,mask,sds,unit,physical,ir,sr,mr,pixel_type,pixel_handle,pixel_offset,attach,compress,changed,total=values
 if version!=1 or header!=80 or not mask or mask&~255:raise ValueError('Unsupported header or rejection mask')
 if n!=min(declared,65536) or total!=80+2*n or len(raw)!=total:raise ValueError('Truncated or inconsistent capture length')
 signed=lambda v:v if v<0x80000000 else v-0x100000000
 first,second=raw[80:80+n],raw[80+n:];diff=[i for i,(a,b) in enumerate(zip(first,second)) if a!=b]
 if bool(diff)!=bool(changed) or bool(mask&2)!=bool(changed):raise ValueError('Inconsistent stability fields')
 return dict(format='YC38RJ01',record_sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),declared_sds_bytes=declared,
  copied_sds_bytes=n,rejection_mask=mask,reasons=[s for bit,s in REASONS.items() if mask&bit],
  decoder_results=dict(image=signed(ir),state=signed(sr),multi_segment=signed(mr)),
  metadata=dict(handle=sds,unit_type=unit,physical_hex=f'{physical:08x}'),
  reported_image=dict(unit_type=pixel_type,handle=pixel_handle,data_offset=pixel_offset,image_attach=attach,yc_compress=compress),
  changed_byte_count=len(diff),first_changed_offsets=diff[:256],
  snapshots=[dict(sha256=hashlib.sha256(x).hexdigest(),sds=categories(x)) for x in [first,second]],
  limitations=['Historical identities only: never replay handles or physical addresses.','A valid record does not prove fsync succeeded; check EVENT_REJECTION_SAVED in the camera log.','No pixel data or hardware-completion proof is contained in this record.'])
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('record',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
 out=decode(a.record.read_bytes());text=json.dumps(out,indent=2)+'\n'
 if a.output:
  with a.output.open('x',encoding='utf-8') as f:f.write(text)
 else:print(text,end='')
if __name__=='__main__':main()
