"""Refresh offline package from current binaries and guarded script templates."""
from pathlib import Path
import hashlib,json,shutil
W=Path(__file__).resolve().parent
P=Path('outputs/native-dmm-v29/flash-package');P.mkdir(parents=True,exist_ok=True)
C=P.parent/'candidate'
def md5(p):return hashlib.md5(p.read_bytes()).hexdigest()
replacements={'b4c6012cd876210fcfd0cf4b0d6f67e0':md5(C/'yuy2_640_v29full.so'),
              '32a2d064d25720c17dd9a43927d4a835':md5(C/'libInfraStreamingUsb.persistent.so')}
scripts={n:(W/n).read_text() for n in ['install.sh','rollback.sh','preflight.sh']}
for n,s in scripts.items():
    for a,b in replacements.items():s=s.replace(a,b)
    scripts[n]=s
scripts['install.sh']=scripts['install.sh'].replace(md5(W/'rollback.sh'),hashlib.md5(scripts['rollback.sh'].encode()).hexdigest())
for n,s in scripts.items():(P/n).write_bytes(s.encode())
for n in ['yuy2_640_v29full.so','libInfraStreamingUsb.persistent.so']:shutil.copy2(C/n,P/n)
# The existing verified ARM space helper is copied unchanged, not rebuilt.
assert md5(P/'space-check.elf')=='c2c8b809405bf52e3a7fa8df88aa95eb'
m={'revision':'2.9','state':'PACKAGED_NOT_INSTALLED','files':{}}
for n in ['install.sh','preflight.sh','rollback.sh','space-check.elf','yuy2_640_v29full.so','libInfraStreamingUsb.persistent.so']:
    p=P/n;b=p.read_bytes();m['files'][n]={'bytes':len(b),'md5':md5(p),'sha256':hashlib.sha256(b).hexdigest()}
(P/'package-manifest.json').write_text(json.dumps(m,indent=2)+'\n')
