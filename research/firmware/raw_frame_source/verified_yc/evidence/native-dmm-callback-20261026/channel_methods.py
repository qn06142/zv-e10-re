exec(open('work/native-dmm-callback/sdk_methods.py').read().split('with p.open')[0])
with p.open('rb') as f:
 e=ELFFile(f);sy=e.get_section_by_name('.dynsym');t=e.get_section_by_name('.text');b=t.data();base=t['sh_addr'];d=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
 for s in sy.iter_symbols():
  if s['st_shndx']=='SHN_UNDEF' or 'DataflowInfraCh' not in s.name or not any(x in s.name for x in ['allocOsalId','rcvAsyncGlobalMsg']):continue
  lines.append('\n'+s.name+' '+hex(s['st_value']))
  for i in d.disasm(b[(s['st_value']&~1)-base:(s['st_value']&~1)-base+s['st_size']],s['st_value']&~1):lines.append(f'{i.address:08x}: {i.mnemonic:8} {i.op_str}')
Path('outputs/native-dmm-callback/channel-methods.txt').write_text('\n'.join(lines));print('\n'.join(lines))
