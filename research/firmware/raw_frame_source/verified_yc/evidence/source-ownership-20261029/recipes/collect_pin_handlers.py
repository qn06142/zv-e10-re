"""Static (no emulation) extraction: VDF pin-command vtables and McPinMain handler locations. Offline, read-only."""
import json,hashlib
from own import *
from xref_strings import xrefs
out={'mocked':False,'limitations':'static disassembly/xref only; no execution; function roles inferred from RTTI/log strings','firmware_md5':hashlib.md5(DATA).hexdigest(),'vdf_vtables':{}}
for n in ['SystemCmdPinConnect','SystemCmdPinRequestConnect','SystemCmdPinDisconnect','SystemCmdPinRequestDisconnect','SystemCmdPinSend','SystemCmdPinConnectComp','SystemCmdPinGet']:
    m=('N3VDF%d%sE'%(len(n),n)).encode()
    out['vdf_vtables'][n]=[dict(typeinfo=hex(t),vtable=hex(v),slots=[hex(x) for x in s]) for t,v,s in rtti_vtables(m)]
S={'McPinMain::ExecDisconnectComp':0x63f2d921,'McPinMain::ExecRequestConnect':0x63f2d96a,'McPinMain::ExecRequestDisconnect':0x63f2d9e1,'McPinMain::ExecConnectComp':0x63f2da30,'McPinMain::ExecConnect':0x63f2da73,'McPinMain::ExecDisconnect':0x63f2daad,'CdYCPinSender::SendYCPin':0x63f16829,'CdSeqCtrlEnc::SendYCPinConnect':0x63f14265,'CdSeqCtrlEncIf::ExecYCPinConnectComp':0x63f15a92}
x=xrefs(list(S.values()))
out['string_xrefs']={k:x[v] for k,v in S.items()}
json.dump(out,open('../pin-handlers-static.json','w'),indent=1)
print(json.dumps(out['string_xrefs'],indent=1))
