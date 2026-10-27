from pathlib import Path
import argparse,hashlib,json
from elftools.elf.elffile import ELFFile

SDK={
 'DMM_CTOR':'_ZN17OBJAVBBCBASECLASS5DmmChC1Et',
 'SDF_CTOR':'_ZN17OBJAVBBCBASECLASS5SdfChC1Et',
 'SHARE':'_ZN17OBJAVBBCBASECLASS5DmmCh10allocShareEP17dmm_comp_alc_unitjtt',
 'OPEN':'_ZN17OBJAVBBCBASECLASS5DmmCh4openEP18dmm_comp_open_unitttj',
 'CLOSE':'_ZN17OBJAVBBCBASECLASS5DmmCh5closeEP19dmm_comp_close_unitt',
 'FREE':'_ZN17OBJAVBBCBASECLASS5DmmCh4freeEP18dmm_comp_free_unittt',
 'RESIZE':'_ZN17OBJAVBBCBASECLASS5SdfCh12resizeRotateEPN3SDF18SDF_BASE_CMP_PARAMEPNS1_18SDF_BASE_ACK_PARAMEPNS1_27RESIZE_ROTATE_COMMAND_PARAME',
 'ALLOC_NEW':'_ZN17OBJAVBBCBASECLASS5DmmCh8allocNewEP17dmm_comp_alc_unitjtj',
}
OBJ={'ALLOC_CTOR':0x206ac4,'ALLOC_PAIR':0x206c56,'YC_CTOR':0xe490a4,
     'GEOMETRY':0xe48a10,'STORE':0xe49160,'YC_DTOR':0xe486ec}
HASH={'libObj.so':'0b4be3fb599b539c69c782bd400dd8e9',
      'libBizFw.so':'6416a5a6780bbe829eb30d85fc8e8dad'}

def build(repo,output):
 rows=['/* Generated from exact inspected Sony files; do not hand edit. */'];report={'input_md5':HASH,'sdk':{},'obj':{}}
 def process(filename,config,prefix,by_symbol):
  path=repo/'dumps/camera_2025/usr/usr/lib'/filename
  assert hashlib.md5(path.read_bytes()).hexdigest()==HASH[filename],filename
  guards=[];addresses=[]
  with path.open('rb') as f:
   e=ELFFile(f);symbols={s.name:s for s in e.get_section_by_name('.dynsym').iter_symbols()}
   for key,value in config.items():
    address=(symbols[value]['st_value']&~1) if by_symbol else value
    seg=next(s for s in e.iter_segments() if s['p_type']=='PT_LOAD' and s['p_vaddr']<=address and address+16<=s['p_vaddr']+s['p_filesz'])
    guard=seg.data()[address-seg['p_vaddr']:address-seg['p_vaddr']+16];guards.append(guard);addresses.append(address)
    report[prefix][key]={'address':hex(address),'guard':guard.hex(),'symbol':value if by_symbol else None}
  rows.append('enum {'+','.join('VG_'+k for k in config)+',VG_'+prefix.upper()+'_COUNT};')
  if by_symbol:rows.append('static const char *const vg_sdk_names[]={'+','.join(json.dumps(n) for n in config.values())+'};')
  else:rows.append('static const unsigned vg_obj_offsets[]={'+','.join(hex(n) for n in addresses)+'};')
  rows.append('static const unsigned char vg_'+prefix+'_guards[][16]={'+','.join('{'+','.join(hex(n) for n in b)+'}' for b in guards)+'};')
 process('libBizFw.so',SDK,'sdk',True);process('libObj.so',OBJ,'obj',False)
 output.write_text('\n'.join(rows)+'\n');output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.repo,a.output)
