from pathlib import Path
import sys,json
sys.path.insert(0,'.local/work/yc-frame-contract-20261029');import rtos
sys.path.insert(0,'.local/work/yc-subsystem-offline-20261029');from thumb_xrefs import direct_calls
out=[];texts=[]
for pc,target in direct_calls(rtos.DATA,rtos.BASE):
 if target==0x637cd6b0:
  out.append(hex(pc));texts.append(rtos.disasm(pc-48,pc+64))
p=Path('.local/outputs/yc-native-setup-20261030');p.joinpath('depth-getter-callers.json').write_text(json.dumps(out,indent=2));p.joinpath('depth-getter-callers.txt').write_text('\n'.join(texts));print(out)
