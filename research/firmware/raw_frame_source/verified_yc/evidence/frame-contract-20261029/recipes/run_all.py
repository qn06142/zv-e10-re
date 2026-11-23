"""Run offline frame-contract checks from the workspace holding local fixtures."""
from pathlib import Path
import subprocess,sys,json,hashlib
here=Path(__file__).resolve().parent;out=Path('.local/outputs/yc-frame-contract-20261029');out.mkdir(parents=True,exist_ok=True)
checks=['verify_pin_initialization','verify_producer_send','verify_encoder_io','verify_vdf_completion','verify_sdf_forwarding','verify_sdf_short_parse','verify_sdf_build_parameters','verify_sdf_ack_cmp','verify_usb_lifetime','collect_evidence','inspect_usb']
results=[]
for name in checks:
 p=subprocess.run([sys.executable,'-B',str(here/(name+'.py'))],capture_output=True,text=True)
 log=p.stdout+p.stderr;(out/(name+'.log')).write_text(log)
 results.append(dict(check=name,exit_code=p.returncode,log_sha256=hashlib.sha256(log.encode()).hexdigest()))
 print(name+(': PASS' if p.returncode==0 else ': FAIL'),flush=True)
 if p.returncode:print(log);raise SystemExit(p.returncode)
(out/'verification-summary.json').write_text(json.dumps(dict(camera_access=False,checks=results,meaning='Original-code software contract checks only; hardware services are mocked and no live frame is acquired.'),indent=2)+'\n')
