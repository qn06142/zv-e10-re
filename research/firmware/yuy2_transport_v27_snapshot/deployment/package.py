"""Repackage the verified snapshot candidate and guarded deployment scripts."""
from pathlib import Path
import argparse,subprocess,re,hashlib,json,shutil
ap=argparse.ArgumentParser();ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--repo',type=Path,default=Path(r'D:/02_Development_And_Projects/pmca-re'));a=ap.parse_args()
W=Path(__file__).resolve().parent;P=a.output.resolve();assert not P.exists(),'Use a fresh package directory';P.mkdir(parents=True)
subprocess.run(['C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe','-mcpu=cortex-a5','-marm','-mfloat-abi=soft','-O2','-fno-builtin','-fno-stack-protector','-nostdlib','-L'+str(a.repo/'build_sysroot/lib'),'-Wl,-rpath-link,'+str(a.repo/'build_sysroot/lib'),'-Wl,--dynamic-linker=/lib/ld-linux.so.3,-e,_start,--hash-style=sysv','-o',str(P/'space-check.elf'),str(W/'space_check.c'),str(a.repo/'research/firmware/yuy2_transport_v27_snapshot/arm_linux_start.S'),'-l:libc.so.6','-lgcc'],check=True)
h=hashlib.md5((P/'space-check.elf').read_bytes()).hexdigest();s=(W/'preflight.sh').read_text();s,n=re.subn(r'(guard "\$SPACE" )[0-9a-f]{32}',lambda m:m[1]+h,s);assert n==1;(P/'preflight.sh').write_bytes(s.encode())
for name in ['install.sh','rollback.sh']:shutil.copy2(W/name,P/name)
for name,md5 in [('libInfraStreamingUsb.persistent.so','c3aa9b92ea6c05ce78aa7894e8dfe35a'),('yuy2_640_v27snap.so','ec185c27deb53f80f6f5a40d9a8f95f1')]:
 data=(a.candidate/name).read_bytes();assert hashlib.md5(data).hexdigest()==md5;(P/name).write_bytes(data)
assert hashlib.md5((P/'rollback.sh').read_bytes()).hexdigest() in (P/'install.sh').read_text()
manifest={'revision':'2.7','state':'PACKAGED_NOT_INSTALLED','remote_stage':'/log/yuy2_640_v27snap','recovery':'/usr/share/yuy2-recovery-v27snap/rollback.sh','recovery_restores':'working permanent 2.4p','auto_reboot':False,'files':{}}
for p in sorted(P.iterdir()):
 b=p.read_bytes();manifest['files'][p.name]={'bytes':len(b),'md5':hashlib.md5(b).hexdigest(),'sha256':hashlib.sha256(b).hexdigest()}
(P/'package-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for name in ['README.md','run_job.py','package.py','space_check.c']:shutil.copy2(W/name,P/name)
print(json.dumps(manifest,indent=2))
