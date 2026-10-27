from pathlib import Path
import hashlib,json
actual=Path('outputs/uvc-startup-fix/candidate-1080p/av-cam.bin').read_bytes();base=Path(r'D:/02_Development_And_Projects/pmca-re/dumps/firmware/av-cam.bin').read_bytes();assert hashlib.md5(actual).hexdigest()=='90096db2c76148f4f9db5d104e5c608c'
BASE=0x635c6000;ranges=[('metadata_builder',0x6374cdd4,0x6374cf38),('allocator_consumer',0x6374d088,0x6374d0d2),('native_rdv_allocator',0x637545ec,0x63754694),('vef_lookup_and_selector',0x63761dcc,0x63762058),('vef_records',0x645b580c,0x645b5a74)]
checks=[]
for name,lo,hi in ranges:
 a=actual[lo-BASE:hi-BASE];b=base[lo-BASE:hi-BASE];assert a==b,name;checks.append({'region':name,'start':hex(lo),'end':hex(hi),'bytes':len(a),'sha256':hashlib.sha256(a).hexdigest(),'stock_and_installed_patch_identical':True})
Path('outputs/native-dmm-v28/provenance/installed-firmware-region-verification.json').write_text(json.dumps({'firmware_md5_matches_last_camera_readback':'90096db2c76148f4f9db5d104e5c608c','regions':checks},indent=2)+'\n')
p=Path('work/native-dmm-v28/verify_provenance.py');s=p.read_text().replace("B=(R/'dumps/firmware/av-cam.bin').read_bytes()", "B=Path('outputs/uvc-startup-fix/candidate-1080p/av-cam.bin').read_bytes()")
s=s.replace("'camera_access':False,'cases':rows", "'camera_access':False,'firmware_md5':'90096db2c76148f4f9db5d104e5c608c','cases':rows")
p.write_text(s)
print('All producer/allocator/metadata/table regions match the camera-matching firmware image')
