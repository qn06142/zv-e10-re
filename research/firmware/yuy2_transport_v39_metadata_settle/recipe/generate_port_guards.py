from pathlib import Path
import json,hashlib
from elftools.elf.elffile import ELFFile
METHODS={'SENDER_CTOR':'_ZN19DataflowInfraSenderC1Ev','PIN_CTOR':'_ZN16DataflowInfraPinC1EPN19DefDataflowInfraPin12PIN_PROPERTYEP19DataflowInfraSender','RECEIVER_CTOR':'_ZN21DataflowInfraReceiverC1Ev','MSG_CTOR':'_ZN16DataflowInfraMsgC1Ev','MSG_DTOR':'_ZN16DataflowInfraMsgD1Ev','RECEIVE':'_ZN21DataflowInfraReceiver12ReceiveASyncEjP16DataflowInfraMsgm','MSG_SIZE':'_ZN16DataflowInfraMsg13GetTopMsgSizeEv','MSG_COPY':'_ZN16DataflowInfraMsg6GetMsgEPvt','CONNECT':'_ZN16DataflowInfraPin7ConnectEPK16_MSG_PIN_CONNECT','DISCONNECT':'_ZN16DataflowInfraPin10DisconnectEPK19_MSG_PIN_DISCONNECT','SEND_COMP':'_ZN16DataflowInfraPin8SendCompEl'}
def build(repo,output):
 p=repo/'.local/dumps/camera_2025/usr/usr/lib/dataflowInfraFramework.so';assert hashlib.md5(p.read_bytes()).hexdigest()=='f70f50f931e9c2cf415cc2728e324f60'
 guards=[];report={}
 with p.open('rb') as f:
  e=ELFFile(f);sy={s.name:s for s in e.get_section_by_name('.dynsym').iter_symbols()}
  for k,n in METHODS.items():
   a=sy[n]['st_value']&~1;s=next(s for s in e.iter_segments() if s['p_type']=='PT_LOAD' and s['p_vaddr']<=a and a+16<=s['p_vaddr']+s['p_filesz']);g=s.data()[a-s['p_vaddr']:a-s['p_vaddr']+16];guards.append(g);report[k]=dict(symbol=n,address=hex(a),guard=g.hex())
 rows=['/* Generated original framework guards. */','enum {'+','.join('YP_'+k for k in METHODS)+',YP_COUNT};','static const char *const yp_names[]={'+','.join(json.dumps(n) for n in METHODS.values())+'};','static const unsigned char yp_guards[][16]={'+','.join('{'+','.join(hex(x) for x in g)+'}' for g in guards)+'};']
 output.write_text('\n'.join(rows)+'\n');output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
