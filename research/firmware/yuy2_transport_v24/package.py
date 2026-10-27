"""Package paired offline artifacts; does not generate an unverified installer."""
from pathlib import Path
import argparse,hashlib,json,struct
from kernel_patch import transform,FRAME_BYTES,PAYLOAD_BYTES,INTERVAL

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
args=ap.parse_args();out=args.output;repo=args.repo
m=json.loads((out/'manifest.json').read_text());assert m['revision']=='2.4'
producer=json.loads((out/'verification.json').read_text())
bootstrap=json.loads((out/'bootstrap-verification.json').read_text())
kernel=json.loads((out/'kernel-verification.json').read_text())
assert producer['passed']==50 and len(bootstrap)==4 and kernel['passed']==14
stock=(repo/'dumps/camera_2025/usr/usr/kmod/usbg_video.ko').read_bytes()
assert transform(stock)[0]==(out/'usbg_video.ko').read_bytes()
descriptors=(out/'descriptors.bin').read_bytes();assert len(descriptors)==154
for offset in (0,77):
 d=descriptors[offset:offset+77];frame=d[41:71]
 assert d[19:35]==bytes.fromhex('5955593200001000800000aa00389b71')
 assert struct.unpack_from('<HH',frame,5)==(640,480)
 assert struct.unpack_from('<II',frame,17)==(FRAME_BYTES,INTERVAL)
 assert struct.unpack_from('<I',frame,26)[0]==INTERVAL
for name in list(m['files']):
 data=(out/name).read_bytes();assert hashlib.sha256(data).hexdigest()==m['files'][name]['sha256']
m.update(status='OFFLINE_VERIFIED_PAIRED_CANDIDATE_NOT_INSTALLED',not_installed=True,
         verification={'producer':producer,'bootstrap_cases':len(bootstrap),'kernel':kernel},
         kernel_contract={'frame_bytes':FRAME_BYTES,'payload_bytes':PAYLOAD_BYTES,'interval_100ns':INTERVAL},
         required_firmware_md5={
          'av-cam.bin':'90096db2c76148f4f9db5d104e5c608c',
          'libInfraStreamingUsb.so':'19461091c07aa6900829defb0060fcd6',
          'libInfraUsbCmn.so':'31308976206a837f6f5c571992d2b499',
          'stock_usbg_video.ko':hashlib.md5(stock).hexdigest()},
         config_md5=hashlib.md5((repo/'dumps/camera_2025/usr/setting/DmmConfig.bin').read_bytes()).hexdigest(),
         activation_requirements=[
          'Use loaded kernel version yuy2_640_v23 with MD5 c1cad400372e26eca729e4b9bc47a237; do not replace the tested kernel for this lifecycle-only revision.',
          'Clear existing RAM hooks with a genuine reboot; never hot-swap active hooks.',
          'Both candidate components are required; kernel candidate must not be used with stock MJPEG producer.',
          'Verify the patched module is actually loaded, not merely present as a file.',
          'Choose and review kernel activation and rollback using actual camera state before any deployment.',
          'Rebuild bootstrap for fresh process mappings; saved stream base is historical and not an installation assumption.'],
         limitations=[
          'Offline verification uses simulated services; no hardware frames are demonstrated.',
          'Windows acceptance of a 614412-byte payload maximum requires a hardware test.',
          'Original kernel queue/DMA completion error propagation is unchanged.',
          'Original zero-valued PTS/SCR header fields remain; clock behavior has not been validated.',
          'This remains a synthetic colour-bar producer, not live sensor footage.',
          'No automatic kernel activation or installer is included in this offline package.'])
for name in ['usbg_video.ko','usbg_video.patch.json','kernel-verification.json','yuy2_640.c']:
 data=(out/name).read_bytes();m['files'][name]={'bytes':len(data),'md5':hashlib.md5(data).hexdigest(),'sha256':hashlib.sha256(data).hexdigest()}
(out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
print('Revision 2.4 packaged: 50 producer + 4 bootstrap + 14 kernel checks.')
