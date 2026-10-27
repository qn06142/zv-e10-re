from pathlib import Path
import subprocess,hashlib,json
W=Path('work/native-dmm-v28/deployment');P=Path('outputs/native-dmm-v28/flash-package');OLD='c3aa9b92ea6c05ce78aa7894e8dfe35a';NEW='27f4f4696c724caa8348edc51c86a517';MOD='5dd449056e4da5b7bea072d9e3b65d0b';STABLE='5fde77e394572ebcf420f8941575f6c4'
subprocess.run(['C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe','-mcpu=cortex-a5','-marm','-mfloat-abi=soft','-O2','-fno-builtin','-fno-stack-protector','-nostdlib','-LD:/02_Development_And_Projects/pmca-re/build_sysroot/lib','-Wl,-rpath-link,D:/02_Development_And_Projects/pmca-re/build_sysroot/lib','-Wl,--dynamic-linker=/lib/ld-linux.so.3,-e,_start,--hash-style=sysv','-o',str(P/'space-check.elf'),str(W/'space_check.c'),'work/native-dmm-v28/recipe/arm_linux_start.S','-l:libc.so.6','-lgcc'],check=True)
oldP=Path('outputs/native-dmm-callback/flash-package');pre=(oldP/'preflight.sh').read_text().replace('v27snap','v28snap').replace(STABLE,OLD).replace('V27_','V28_')
pre=pre.replace('guard /usr/lib/yuy2_640_v24p.so', 'guard /usr/lib/yuy2_640_v27snap.so ec185c27deb53f80f6f5a40d9a8f95f1\nguard /usr/share/yuy2-recovery-v27snap/libInfraStreamingUsb.v24p.so '+STABLE+'\nguard /usr/lib/yuy2_640_v24p.so')
oldSpace=hashlib.md5((oldP/'space-check.elf').read_bytes()).hexdigest();newSpace=hashlib.md5((P/'space-check.elf').read_bytes()).hexdigest();pre=pre.replace(oldSpace,newSpace)
rollback=(oldP/'rollback.sh').read_text().replace('v27snap','v28snap').replace('V27_','V28_').replace('OLD_STREAM','OLD_STREAM')
rollback=rollback.replace(STABLE+'|'+OLD,STABLE+'|'+OLD+'|'+NEW).replace('= ec185c27deb53f80f6f5a40d9a8f95f1','= '+MOD)
# The original rollback guards its old v27 module hash; now guard v28's new hash.
rollback=rollback.replace('ec185c27deb53f80f6f5a40d9a8f95f1',MOD)
install=(oldP/'install.sh').read_text().replace('v27snap','v28snap').replace('V27_','V28_').replace('.v27snap.','.v28snap.')
# Preserve the previous installed library separately from the stable 2.4p rescue.
install=install.replace('libInfraStreamingUsb.v24p.so','libInfraStreamingUsb.previous.so').replace('libInfraStreamingUsb.v24p-inode.so','libInfraStreamingUsb.previous-inode.so')
# Substitute longest-lived hash roles without cascading the old/new roles.
install=install.replace(OLD,'@NEW@').replace(STABLE,OLD).replace('@NEW@',NEW).replace('ec185c27deb53f80f6f5a40d9a8f95f1',MOD)
oldRollback=hashlib.md5((oldP/'rollback.sh').read_bytes()).hexdigest();newRollback=hashlib.md5(rollback.encode()).hexdigest();install=install.replace(oldRollback,newRollback)
install=install.replace('BACKED=1\n',f'''BACKED=1
$BB cp /usr/share/yuy2-recovery-v27snap/libInfraStreamingUsb.v24p.so "$B/libInfraStreamingUsb.v24p.so"
[ "$(hash "$B/libInfraStreamingUsb.v24p.so")" = {STABLE} ]
''')
# Old source module stays available as an additional guard and recovery dependency.
install=install.replace('[ "$(hash /usr/lib/yuy2_640_v24p.so)', '[ "$(hash /usr/lib/yuy2_640_v27snap.so)" = ec185c27deb53f80f6f5a40d9a8f95f1 ]\n[ "$(hash /usr/lib/yuy2_640_v24p.so)')
for n,s in [('preflight.sh',pre),('rollback.sh',rollback),('install.sh',install)]:
 (W/n).write_bytes(s.encode());(P/n).write_bytes(s.encode())
for n,h in [('libInfraStreamingUsb.persistent.so',NEW),('yuy2_640_v28snap.so',MOD)]:
 b=(P.parent/'candidate'/n).read_bytes();assert hashlib.md5(b).hexdigest()==h;(P/n).write_bytes(b)
m={'revision':'2.8','state':'PACKAGED_NOT_INSTALLED','files':{}}
for n in ['preflight.sh','rollback.sh','install.sh','space-check.elf','libInfraStreamingUsb.persistent.so','yuy2_640_v28snap.so']:
 b=(P/n).read_bytes();m['files'][n]={'bytes':len(b),'md5':hashlib.md5(b).hexdigest(),'sha256':hashlib.sha256(b).hexdigest()}
(P/'package-manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps(m,indent=2))
