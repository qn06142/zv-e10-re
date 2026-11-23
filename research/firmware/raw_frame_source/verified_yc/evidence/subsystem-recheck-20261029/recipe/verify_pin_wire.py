"""Original pin constructors/Connect/Send/SendComp executed; send transport intercepted."""
from pathlib import Path
import runpy,struct,json
c=runpy.run_path(str(Path(__file__).parent/'verify_category2_and_pin.py'));u=c['u'];names=c['names'];run=c['run'];word=c['word'];put=c['put'];MEM=c['MEM']
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *
records=[];ignored=[]
log_entries={v&~1:k for k,v in names.items() if k.startswith('_ZN16DataflowInfraLog')}
send_entries={v&~1:k for k,v in names.items() if k in ['_ZN19DataflowInfraSender9SendASyncEjP16DataflowInfraMsg','_ZN19DataflowInfraSender22SendASyncWithTransDataEjP16DataflowInfraMsgt']}
def capture(u,pc,size,data):
 if pc in log_entries:
  ignored.append(log_entries[pc]);u.reg_write(UC_ARM_REG_R0,0);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR));return
 if pc not in send_entries:return
 queue=u.reg_read(UC_ARM_REG_R1);msg=u.reg_read(UC_ARM_REG_R2);ptr=msg+0x24;n=struct.unpack('<H',u.mem_read(ptr+4,2))[0];assert 8<=n<=255
 raw=bytes(u.mem_read(ptr,n));records.append(dict(sender_method=send_entries[pc],destination_fixture=hex(queue),source_id_fixture=hex(word(msg+12)),packet_bytes=n,opcode=hex(struct.unpack_from('<H',raw,2)[0]),raw_hex=raw.hex(),self_properties=list(struct.unpack_from('<4I',raw,8)),peer_properties=list(struct.unpack_from('<4I',raw,24))))
 u.reg_write(UC_ARM_REG_R0,0);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
u.hook_add(UC_HOOK_CODE,capture)
def sym(fragment):return names[next(n for n in names if fragment in n)]
pin=MEM+0x3000;prop=MEM+0x3100;connect=MEM+0x3200;sender=MEM+0x3400
own=[1,3,1,0x0080003b];peer=[1,3,1,0x0059000e]
u.mem_write(prop,struct.pack('<4I',*own));run(sym('DataflowInfraPinC1EPN'),pin,prop,sender)
initial=word(pin+0x28)
rc=run(sym('DataflowInfraPin4SendE'),pin,0xa1b2c3d4,0x1357,0x11223344);assert rc==0xffffffe6 and not records
run(sym('_MSG_PIN_CONNECTC1Ev'),connect);u.mem_write(connect+8,struct.pack('<4I',*peer));u.mem_write(connect+24,struct.pack('<4I',*own))
assert run(sym('DataflowInfraPin7ConnectEPK'),pin,connect)==0
assert word(pin+0x28)==0
assert run(sym('DataflowInfraPin4SendE'),pin,0xa1b2c3d4,0x1357,0x11223344)==0
assert run(sym('DataflowInfraPin8SendCompE'),pin,0)==0
send=next(r for r in records if r['opcode']=='0x102');b=bytes.fromhex(send['raw_hex']);assert len(b)==52
assert struct.unpack_from('<I',b,40)[0]==0xa1b2c3d4 and struct.unpack_from('<H',b,44)[0]==0x1357 and struct.unpack_from('<I',b,48)[0]==0x11223344
comp=next(r for r in records if r['opcode']=='0x8102');assert comp['packet_bytes']==44 and struct.unpack_from('<i',bytes.fromhex(comp['raw_hex']),40)[0]==0
out=dict(camera_access=False,original_pin_and_message_code_executed=True,transport_mocked=True,property_words_are_fixture_inputs=True,initial_pin_state=initial,connected_pin_state=word(pin+0x28),send_before_connect_rc=hex(rc),records=records,conclusions=['Connect validates compatible property words and installs peer routing.','Send packs a32-bit first argument at+0x28,a16-bit second at+0x2c,and32-bit third at+0x30.','SendComp packs status and route properties, not an echoed pixel/SDS handle.','No DMM Share/Open/Free was executed by these generic pin methods.'],limitations=['Fixture connection is not a real subscription or ownership lease.','Which argument is an SDS handle in a particular producer must be traced at its caller.','Actual producer registration, receive-dispatch path and buffer ownership remain unimplemented.'])
Path('.local/outputs/yc-subsystem-offline-20261029/pin-wire-original-execution.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
