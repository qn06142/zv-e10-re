import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent.parent)]
from research.device.zve10_retry import run

def push_chunked(local_path: str, remote_path: str):
    data = Path(local_path).read_bytes()
    want_md5 = hashlib.md5(data).hexdigest()
    hex_str = data.hex()
    
    # 128 bytes = 256 hex chars per line. Extremely safe for serial line buffers.
    chunk_size = 256
    chunks = [hex_str[i:i+chunk_size] for i in range(0, len(hex_str), chunk_size)]
    
    print(f"[*] Staging {local_path} ({len(data)} bytes, {len(chunks)} chunks, MD5: {want_md5})...")
    
    cmds = [f"rm -f {remote_path} {remote_path}.hex"]
    for c in chunks:
        cmds.append(f"echo -n {c} >> {remote_path}.hex")
    
    cmds.append(f"busybox xxd -r -p {remote_path}.hex > {remote_path}")
    cmds.append(f"chmod 755 {remote_path}")
    cmds.append(f"rm -f {remote_path}.hex")
    cmds.append(f"busybox md5sum {remote_path}")
    
    out, tries = run(cmds)
    print(out)
    if want_md5 in out:
        print(f"[+] SUCCESS: {remote_path} MD5 matches ({want_md5})!")
        return True
    else:
        print(f"[-] FAILED: MD5 did not match {want_md5}")
        return False

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "research/device/sidecar_demo.elf"
    dst = sys.argv[2] if len(sys.argv) > 2 else "/tmp/sidecar_demo.elf"
    push_chunked(src, dst)
