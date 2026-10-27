from pathlib import Path
import struct
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
b=Path(r'D:/02_Development_And_Projects/pmca-re/dumps/firmware/av-cam.bin').read_bytes();base=0x635c6000
ranges=[('vdf-dmm-share-before-send',0x63748700,0x63748c10),('vdf-pin-dmm-destruct',0x6371f300,0x6371f6c0),('sdf-pixel-format-low',0x63cc3900,0x63cc3e80),('sdf-yc-config',0x636e9b00,0x636eb980),('vdf-native-yuv-info',0x63ce2480,0x63ce26c0),('vdf-adf-yc-native',0x63cfb0b4,0x63cfb210),('vdf-black-frame',0x6372758c,0x63727800),('vdf-black-creator',0x63ce6870,0x63ce6960),('vdf-rgba-yuv-execute',0x63ce7d40,0x63ce7f80),('vdf-rgba-yuv-process-method',0x63ce6b3a,0x63ce6e00),('vdf-rgba-yuv-processor',0x637205e0,0x63720960),('vdf-adf-yc-send',0x63748c00,0x63749080),('vdf-adf-yc-send-method',0x63cfb000,0x63cfb160),('vdf-preview-metadata-builder',0x6374ae88,0x6374b000),('vdf-yc-send-producer',0x6374b000,0x6374ca80),('rtos-dataflow-pin',0x63ac1a20,0x63ac2060),('codec-yc-config-builder',0x63688d00,0x63689700),('codec-frame-format',0x63c83b00,0x63c84600),('encoder-pixel-config',0x63c86600,0x63c86d00),('fc-monitoring-real',0x63b42800,0x63b44200),('fc-monitoring-consumer',0x63b41d98,0x63b42800),('vdf-yuv-buffer-format',0x6372e400,0x6372f000),('mc-yc-core',0x63c60980,0x63c62000),('mc-yc-data',0x63665c00,0x63666c00),('encoder-yc-ownership',0x63691d80,0x63692400),('encoder-yc-layout',0x63692b00,0x63692f80),('vdf-update-yuv-pin',0x6372f300,0x6372f800)]
decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB);decoder.skipdata=True
for name,start,end in ranges:
 literals={};lines=[]
 for i in decoder.disasm(b[start-base:end-base],start):
  a,mn,op=i.address,i.mnemonic,i.op_str;note=''
  if mn.startswith('ldr') and ', [pc, #' in op and op.endswith(']'):
   reg,disp=op.split(', [pc, #');at=((a+4)&~3)+int(disp[:-1],0)
   if base<=at<base+len(b)-3:literals[reg]=struct.unpack_from('<I',b,at-base)[0]
  if mn=='add' and op.endswith(', pc'):
   reg=op.split(',')[0]
   if reg in literals:
    adr=(literals[reg]+a+4)&0xffffffff
    if base<=adr<base+len(b)-120:
     text=b[adr-base:adr-base+180].split(b'\0')[0]
     if len(text)>3 and all(x in [9,10,13] or 32<=x<127 for x in text):note=repr(text.decode('ascii'))
  lines.append(f'{a:08x}: {mn:8} {op} {note}')
 Path('outputs/yc-source-re-20261025/'+name+'.txt').write_text('\n'.join(lines));print(name,len(lines),'instructions')
