from pathlib import Path
import subprocess,tempfile,hashlib,json
W=Path('.local/work/vga-v37');O=Path('.local/outputs/vga-v37/deployment');BASH='C:/msys64/usr/bin/bash.exe'
md=lambda p:hashlib.md5(p.read_bytes()).hexdigest()
results=[]
for mode in ['success','copy-failure','ro-failure']:
 root=Path(tempfile.mkdtemp(prefix='temp-log-fixture-',dir='.local/outputs/vga-v37')).resolve();r=root.as_posix()
 for p in ['usr/kmod','usr/lib','usr/share','log/yuy2_640_v37vga']:(root/p).mkdir(parents=True,exist_ok=True)
 (root/'usr/kmod/kikilog.ko').write_bytes((O/'kikilog.original.readback.ko').read_bytes())
 (root/'usr/lib/libInfraStreamingUsb.so').write_text('886445056d2eba99ef62df3a9def5e0f')
 (root/'usr/kmod/usbg_video.ko').write_text('c1cad400372e26eca729e4b9bc47a237')
 (root/'log/yuy2_640_v37vga/kikilog.tmpnofile.ko').write_bytes((O/'kikilog.tmpnofile.ko').read_bytes())
 fake=root/'bb';fake.write_text("""#!/usr/bin/bash
set -eu
PATH=/usr/bin:/bin
ROOT=ROOT_PATH
MODE=MODE_TEXT
cmd=$1;shift
case "$cmd" in
 mount) if [ "$MODE" = ro-failure ] && [ "$2" = remount,ro ]; then exit 1; fi;;
 sync) :;;
 md5sum) for f in "$@"; do if [ "$(wc -c < "$f")" = 32 ]; then printf '%s  %s\\n' "$(cat "$f")" "$f"; else md5sum "$f"; fi; done;;
 cp) if [ "$MODE" = copy-failure ] && [ "$2" = "$ROOT/usr/kmod/.kikilog.tmpnofile.new" ]; then exit 1; fi; cp "$@";;
 *) "$cmd" "$@";;
esac
""".replace('ROOT_PATH',r).replace('MODE_TEXT',mode))
 s=(W/'install_temp_log_driver.sh').read_text().replace('/bin/busybox',fake.as_posix())
 for pre in ['/usr','/log']:s=s.replace(pre,r+pre)
 script=root/'install.sh';script.write_bytes(s.encode());q=subprocess.run([BASH,str(script)],capture_output=True,text=True,timeout=30)
 current=md(root/'usr/kmod/kikilog.ko')
 if mode=='success':assert q.returncode==0 and current=='8af7cfd952dbdd47b4f468de6c7d385e',(q.returncode,q.stdout,q.stderr)
 else:assert q.returncode!=0 and current=='51337167a2ab42d53557c2cce210c987',(mode,q.returncode,q.stdout,q.stderr)
 results.append(mode)
(O/'temp-log-installer-verification.json').write_text(json.dumps(dict(camera_access=False,passed=results),indent=2)+'\n');print(results)
