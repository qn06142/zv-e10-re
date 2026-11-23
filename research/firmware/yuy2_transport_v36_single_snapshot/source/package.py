"""Create revision 3.6 artifacts and guarded scripts offline; never install."""
from pathlib import Path
import re,json,hashlib,shutil,subprocess,sys,zipfile
W=Path(__file__).resolve().parent;root=W.parent.parent;O=root/'.local/outputs/vga-v36';P=O/'flash-package';P.mkdir(parents=True,exist_ok=True);(W/'deployment').mkdir(exist_ok=True)
m=json.loads((O/'build/manifest.json').read_text());newmod=m['files']['yuy2_640_v36vga.so']['md5'];newwrap=m['files']['libInfraStreamingUsb.so']['md5']
replacements={'v35':'v36','V35':'V36','v34':'v35','V34':'V35','ca3cbbc5947caf3373ebe451343fb926':'c16af3a036529b89d23fa4ccfd059ec3','ac565b4060a7062745d3bd22037d5410':'e6b9fa6947a21e5a6a1603e070a1d00f','c16af3a036529b89d23fa4ccfd059ec3':newwrap,'e6b9fa6947a21e5a6a1603e070a1d00f':newmod,'909c4ffadc9e5972b25101529d5f8773':'ca3cbbc5947caf3373ebe451343fb926','previous 3.4':'previous 3.5'}
pattern=re.compile('|'.join(re.escape(x) for x in sorted(replacements,key=len,reverse=True)))
for n in ['generate_scripts.py','verify_installer.py']:
 s=(root/'.local/work/vga-v35/deployment'/n).read_text();s=pattern.sub(lambda x:replacements[x[0]],s);(W/'deployment'/n).write_text(s)
subprocess.run([sys.executable,'-B',str(W/'deployment/generate_scripts.py')],check=True)
for src,name in [(O/'build/yuy2_640_v36vga.so','yuy2_640_v36vga.so'),(O/'build/libInfraStreamingUsb.so','libInfraStreamingUsb.persistent.so'),(root/'.local/outputs/vga-v35/flash-package/space-check.elf','space-check.elf')]:shutil.copyfile(src,P/name)
subprocess.run([sys.executable,'-B',str(W/'deployment/verify_installer.py')],cwd=root,check=True)
m['files']['libInfraStreamingUsb.persistent.so']=m['files'].pop('libInfraStreamingUsb.so')
m.update(installed_baseline=dict(revision='3.5',module_md5='e6b9fa6947a21e5a6a1603e070a1d00f',wrapper_md5='c16af3a036529b89d23fa4ccfd059ec3'),crash_fixed=False,packing_corrected=False,event_driven_subscription=False,discovery='DMM_POOL_SCAN_FIRST_SNAPSHOT_ONLY',rollback='Restore installed 3.5 wrapper; stable 2.4p rescue copy retained separately',limitations=['One frozen native snapshot, not continuous video','Existing first-acquisition/resize and stop races remain unproven','No hardware test or firmware installation performed'],source_changes=['one successful native resize per cold boot','publish only after known-reference cleanup','no USB source rewrite after first copy','native snapshot file after cleanup','ACK/CMP payload status diagnostics','source search bounded to 30 unsuccessful polls'])
for name in ['preflight.sh','install.sh','rollback.sh','space-check.elf']:
 d=(P/name).read_bytes();m['files'][name]=dict(bytes=len(d),md5=hashlib.md5(d).hexdigest(),sha256=hashlib.sha256(d).hexdigest())
(P/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
(P/'README.md').write_text('''# ZV-E10 revision 3.6: single-snapshot diagnostic

BUILT OFFLINE / NOT INSTALLED / NOT HARDWARE VERIFIED.

This patch acquires and resizes ONE native 640x480 image, releases its known
borrowed references, then repeats that frozen image over the existing 10-fps
advertised YUY2 transport. It is not continuous live video. Colors and native
packing remain uncorrected. The reported camera crash is NOT proved fixed.

The USB source is copied once and never rewritten by later polling calls;
an F002 staging-availability result is not treated as permission to overwrite
it. The source stays retained during stop, as in the preceding implementation.
No further pool scanning, native resize or worker restart follows capture.
Ambiguous ownership/completion still quarantines; a stuck native call may
still require a cold boot. Source acquisition still uses pool scanning.

The worker saves /log/yuy2_640_v36vga/native-vga-snapshot.bin (614400 native
bytes) from its own RAM AFTER borrowed-reference cleanup. This is for later
format analysis, not proof of YUY2 ordering. Input and destination SSYC plus
ACK/CMP result diagnostics are retained in the same bounded log directory.

Install only through the included scripts, after archiving existing evidence,
normal log/tmp hygiene and a cold boot with USB Streaming unopened. Preflight
requires the exact installed 3.5 module/wrapper hashes in manifest.json and
unchanged subsystem hashes. Never mix this wrapper with another producer.
Installation is dependency-first, creates /usr/share/yuy2-recovery-v36vga/,
verifies copies and returns /usr to read-only. Activation reboot is a separate
step. This package does not execute any of those steps by being built.

rollback.sh restores the previous 3.5 wrapper; it does NOT make 3.5 stable.
A 2.4p rescue wrapper is also retained. Earlier recovery chains are preserved.
One streaming session per cold boot. Do not repeatedly toggle after a failure.
Offline evidence uses mocked hardware services; see evidence/ and manifest.json.
''')
(P/'evidence').mkdir(exist_ok=True)
for f in [O/'worker-verification.json',O/'arm-snapshot-verification.json',O/'build/persistent-verification.json',O/'build/isa-verification.json']:
 shutil.copyfile(f,P/'evidence'/f.name)
sums=[]
for f in sorted(P.rglob('*')):
 if f.is_file() and f.name!='SHA256SUMS':sums.append(hashlib.sha256(f.read_bytes()).hexdigest()+'  '+f.relative_to(P).as_posix())
(P/'SHA256SUMS').write_text('\n'.join(sums)+'\n')
archive=O/'zve10-v36-single-snapshot.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for f in sorted(P.rglob('*')):
  if f.is_file():z.write(f,f.relative_to(P).as_posix())
with zipfile.ZipFile(archive) as z:
 for f in P.rglob('*'):
  if f.is_file():assert z.read(f.relative_to(P).as_posix())==f.read_bytes()
print(json.dumps(dict(package=str(archive),bytes=archive.stat().st_size,module_md5=newmod,wrapper_md5=newwrap,camera_access=False),indent=2))
