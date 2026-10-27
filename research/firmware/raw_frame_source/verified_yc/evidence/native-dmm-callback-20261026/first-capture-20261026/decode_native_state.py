from pathlib import Path
import json,struct,re,hashlib
O=Path('outputs/native-dmm-callback/deployment/live/first-capture-01');m=json.loads((O/'state-layout.json').read_text());data=(O/'module-state.bin').read_bytes();assert hashlib.md5(data).hexdigest()=='016a550630a47219a357bd44ba51c3ac'
def symbol(name):
 v,n=m['symbols'][name];offset=m['load_base']+v-m['read_start'];return data[offset:offset+n]
names=['select_function','send_function','receive_function','io_context','private_reply_queue','candidate_handle_padded','candidate_type','state','shared','opened','sequence','physical','bytes','cancel','token']
backend=dict(zip(names,struct.unpack('<15I',symbol('backend'))));listing=symbol('listing').rstrip(b'\0').replace(b'\0',b'\n').decode('ascii',errors='replace');(O/'last-native-source-listing.txt').write_text(listing)
report={'backend':backend,'target_initialized':struct.unpack('<I',symbol('initialized'))[0],'target_failed':struct.unpack('<I',symbol('failed'))[0],'worker_frames':struct.unpack('<I',symbol('frames'))[0],'worker_raw_errors':struct.unpack('<I',symbol('raw_errors'))[0],'live_source_initialized':struct.unpack_from('<I',symbol('live_source'),40)[0],'last_snapshot_bytes':len(listing),'whitelisted_types_found':[t for t in ['00240b2e','0006193f','00061940'] if t in listing]}
(O/'decoded-native-state.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));print(listing)
