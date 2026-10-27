"""Build passive observer only; performs no USB or camera operations."""
from pathlib import Path
import argparse, subprocess, hashlib, json
p=argparse.ArgumentParser()
p.add_argument('--repo',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--cc',default='C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe')
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
module=a.output/'yc_probe_v3.so'
subprocess.run([a.cc,'-mcpu=cortex-a5','-marm','-mfloat-abi=soft','-mfpu=vfpv4-d16',
 '-fno-tree-vectorize','-fno-tree-slp-vectorize','-O2','-fno-builtin','-fno-stack-protector',
 '-fPIC','-fvisibility=hidden','-shared','-nostdlib',
 '-Wl,--hash-style=sysv,-soname,yc_probe_v3.so,--no-undefined',
 f'-L{a.repo}/build_sysroot/lib',f'-Wl,-rpath-link,{a.repo}/build_sysroot/lib',
 '-o',str(module),str(Path(__file__).with_name('yc_probe_v3.c')),
 '-l:libc.so.6','-l:libdl.so.2','-lgcc'],check=True)
b=module.read_bytes();result={'bytes':len(b),'md5':hashlib.md5(b).hexdigest(),
 'sha256':hashlib.sha256(b).hexdigest(),'passive_metadata_only':True,
 'camera_access':False,'live_frame_acquisition':False}
(a.output/'observer-build.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
