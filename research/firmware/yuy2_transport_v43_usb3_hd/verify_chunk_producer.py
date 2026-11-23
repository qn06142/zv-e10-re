"""Execute real ARM chunk producer, with camera/USB services mocked."""
from pathlib import Path
import json,struct
from verify_frontend import Case,m
from unicorn.arm_const import *
class Chunk(Case):
 def __init__(self):
  self.pending=False;self.busy=False;self.submit_busy=False;self.submit_error=0;self.sequence_override=0;self.stage_bytes=1843200;self.sent=[];self.completed=0;self.events=[];self.yields=0
  super().__init__();self.u.mem_map(0x41000000,0x10000)
  for k,v in [('ready',1),('pixels',0x41000000),('manager',0x1234),('physical',0x15b00000),('capacity',0x320000),('handle',9)]:self.set(k,v)
  for k,n in [('wait_video','chunk_wait'),('submit_video','chunk_submit'),('judge','chunk_judge'),('send_event','chunk_event')]:self.set(k,self.imp(n))
 def ret(self,r):self.u.reg_write(UC_ARM_REG_R0,r&0xffffffff);self.u.reg_write(UC_ARM_REG_PC,self.u.reg_read(UC_ARM_REG_LR))
 def hook(self,u,a,n,d):
  v=[u.reg_read(r) for r in m.R];sp=u.reg_read(UC_ARM_REG_SP)
  if a==self.s.get('staging_size'):
   m.put(u,v[0],self.stage_bytes);m.put(u,v[1],0x11000000);self.ret(0);return
  if a==self.s.get('vga_resize_copy_chunk'):
   # ARM arguments5..9: stage address,size,handle,offset,chunk bytes.
   off=m.word(u,sp+12);count=m.word(u,sp+16)
   assert off==self.get('frame_offset') and count==min(614400,4147200-off)
   assert v[1]==0x320000
   m.put(u,v[2],self.sequence_override or self.completed+1);self.ret(1 if self.pending else 0);return
  if a==self.s.get('vga_resize_frame_done'):
   assert v[0]==self.completed+1 and len(self.sent)==7*(self.completed+1);self.completed+=1;self.ret(0);return
  if a in self.handlers:
   name=self.handlers[a]
   if name=='malloc':self.ret(0x41006000);return
   if name in ['free','strchr','chunk_judge']:self.ret(0);return
   if name=='open' and m.cstr(u,v[0])=='/proc/udm/dmm_units':self.ret(11);return
   if name=='read' and v[0]==11:u.mem_write(v[1],b'row');self.ret(3);return
   if name=='sscanf':
    ptrs=v[2:]+[m.word(u,sp+4*i) for i in range(8)]
    for ptr,value in zip(ptrs,[10,0x50e,0,0,0,0,0,0,0x11000000,self.stage_bytes]):m.put(u,ptr,value)
    self.ret(10);return
   if name=='syscall':u.mem_write(v[2],struct.pack('<II',1,0));self.ret(0);return
   if name=='sched_yield':self.yields+=1;self.ret(0);return
   if name=='__errno_location':self.ret(0x41003000);return
   if name=='chunk_wait':m.put(u,0x41003000,16 if self.busy else 0);self.ret(int(self.busy));return
   if name=='chunk_submit':
    m.put(u,0x41003000,16 if self.submit_busy else self.submit_error)
    if self.submit_busy or self.submit_error:self.ret(1);return
    assert v[1]==0x15b00000;self.sent.append(v[0]);self.ret(0);return
   if name=='chunk_event':self.events.append(v[0]);self.ret(0);return
  super().hook(u,a,n,d)
 def produce(self):self.u.reg_write(UC_ARM_REG_R1,0x41001000);return self.run('produce')
rows=[]
c=Chunk()
for frame in range(2):
 for k in range(7):
  assert c.produce()==0
  word=c.sent[-1];assert word&0x20000000
  assert word&0x1fffffff==(614400 if k<6 else 460800)
  assert (word>>30)&1==(frame+1)&1
  assert bool(word&0x80000000)==(k<6)
  assert c.completed==frame+(k==6)
 assert c.get('frame_offset')==0
assert c.completed==2;rows.append('two_full_HD_frames_each_seven_chunks_stable_FID_final_EOF_only')
c=Chunk();c.pending=True
for i in range(100):assert c.produce()==4
assert not c.sent and not c.completed and not c.get('frame_offset');rows.append('pending_source_no_partial_submission')
c=Chunk();assert c.produce()==0;c.submit_busy=True
for i in range(100):assert c.produce()==4
assert len(c.sent)==1 and c.get('frame_offset')==614400 and not c.completed;rows.append('EBUSY_retries_same_chunk_without_advancing_frame')
c=Chunk();assert c.produce()==0;c.sequence_override=99;assert c.produce()==4 and len(c.sent)==1 and c.events==[10];rows.append('changed_frame_sequence_refused_mid_frame')
c=Chunk();c.stage_bytes=2*(614400+12)-1;assert c.produce()==4 and not c.sent and c.events==[10];rows.append('undersized_chunk_staging_refused')
c=Chunk();c.submit_error=110;assert c.produce()==4 and c.get('dma_quarantined')==1 and not c.completed;rows.append('uncertain_DMA_pins_source_and_retains_publication')
Path('.local/outputs/hd-v43/chunk-producer-verification.json').write_text(json.dumps({'compiled_ARM_executed':True,'hardware_mocked':True,'passed':rows},indent=2));print(json.dumps(rows,indent=2))

