from pathlib import Path
import hashlib,json,io,struct
from elftools.elf.elffile import ELFFile
from rtos import DATA,BASE,disasm
from elf_calls import disassemble,plt_names
R=Path('D:/02_Development_And_Projects/pmca-re');O=Path('.local/outputs/yc-frame-contract-20261029');O.mkdir(parents=True,exist_ok=True)
ranges={
 'vdf-initialize':(0x63744f2c,0x63744fa8),'encoder-pin-constructor':(0x6364e6c8,0x6364e7e8),
 'vdf-producer-allocation-share-send-close':(0x6374c450,0x6374c668),
 'encoder-yc-access':(0x63691dec,0x636922e0),'encoder-input-handler':(0x63692368,0x63692920),
 'vdf-sendcomp-selector-and-execute':(0x63cfa9f4,0x63cfaa1a),'vdf-release-selector':(0x63ce9daa,0x63ce9dc8),
 'vdf-release-execute':(0x6372808c,0x637288a0),'sdf-internal-forwarder':(0x636bdf10,0x636be040),
 'sdf-command-parser':(0x63cade3a,0x63cae67c),'sdf-api-builder':(0x636c5e44,0x636c6420),
 'sdf-cmp-builder':(0x63cadbe4,0x63cadc84),'sdf-cmp-send':(0x636bf6e8,0x636bf92c),
 'sdf-nomem-module':(0x636e5b20,0x636e5e00),'srotate-wrapper-start':(0x636ef294,0x636ef350),
 'srotate-converters':(0x63cc8970,0x63cc8b58)}
for name,(a,b) in ranges.items():(O/(name+'.txt')).write_text(disasm(a,b))
paths=[R/'.local/dumps/firmware/av-cam.bin',R/'.local/dumps/camera_2025/usr/usr/lib/libObj.so',R/'.local/dumps/camera_2025/usr/usr/lib/libBizFw.so',R/'.local/dumps/camera_2025/usr/usr/lib/libInfraUsbCmn.so',R/'.local/dumps/camera_2025/usr/usr/kmod/usbg_video.ko',Path('.local/outputs/uvc-startup-fix/candidate-1080p/av-cam.bin'),Path('.local/outputs/yuy2-640-v24p/candidate/usbg_video.ko')]
hashes=[]
for p in paths:
 d=p.read_bytes();hashes.append(dict(path=str(p),bytes=len(d),md5=hashlib.md5(d).hexdigest(),sha256=hashlib.sha256(d).hexdigest()))
modified=paths[-2].read_bytes();assert len(modified)==len(DATA);diffs=[]
for i,(a,b) in enumerate(zip(DATA,modified)):
 if a!=b:
  if diffs and diffs[-1][1]==i:diffs[-1][1]=i+1
  else:diffs.append([i,i+1])
checks=[]
for name,(a,b) in ranges.items():
 same=DATA[a-BASE:b-BASE]==modified[a-BASE:b-BASE];assert same,name
 checks.append(dict(name=name,start=hex(a),end_exclusive=hex(b),same_in_deployed_rtos_candidate=same))
usb=paths[4].read_bytes();patched=paths[-1].read_bytes();ea=ELFFile(io.BytesIO(usb));eb=ELFFile(io.BytesIO(patched));a=ea.get_section_by_name('.text').data();b=eb.get_section_by_name('.text').data()
usbchecks=[]
for name,start,end in [('dma-callback',0x6a0,0x6ec),('stop',0x744,0x8c8),('submit-except-header-bit',0xd00,0x10f0),('ioctl',0x1e10,0x23c0)]:
 changes=[hex(i) for i in range(start,end) if a[i]!=b[i]]
 assert changes==(['0xf44'] if start==0xd00 else []),(name,changes)
 usbchecks.append(dict(name=name,start=hex(start),end_exclusive=hex(end),different_byte_offsets=changes))
for needle in ['WaitVideoReadCmp','UpdateVideoBufEvt']:(O/('usb-'+needle+'.txt')).write_text(disassemble(paths[3],needle))
with paths[3].open('rb') as f:
 e=ELFFile(f);t=e.get_section_by_name('.text');opcode=struct.unpack_from('<I',t.data(),0x11ea4-t['sh_addr'])[0];assert plt_names(e)[0x8bb0]=='ioctl';p=e.get_section_by_name('.plt');assert p.data()[0x8bac-p['sh_addr']:0x8bb0-p['sh_addr']]==bytes.fromhex('7847c046')
 assert opcode==0x4008f003,hex(opcode)
out=dict(camera_access=False,inputs=hashes,rtos_differing_intervals=[dict(start=hex(BASE+a),end_exclusive=hex(BASE+b)) for a,b in diffs],rtos_compared_ranges=checks,usb_compared_ranges=usbchecks,usb_submit_ioctl=hex(opcode),usb_wait_ioctl='0xf002',usb_plt_8bac='ioctl',limitations=['Historical local candidates match recorded deployed hashes; no current camera readback performed.','Disassembly excerpts include literal pools; linear decoding alone is not control-flow proof.'])
(O/'input-hashes-and-applicability.json').write_text(json.dumps(out,indent=2)+'\n');print('Compared',len(checks),'RTOS ranges and',len(usbchecks),'USB kernel ranges; input hashes saved.')

