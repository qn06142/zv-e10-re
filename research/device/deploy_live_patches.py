import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent.parent)]
from research.device.push_opengate import push_file_b64
from research.device.zve10_retry import run

def main():
    script_path = HERE / "apply_opengate_live.sh"
    remote_path = "/tmp/apply_opengate.sh"
    
    print("[*] Uploading live patch script to camera...")
    ok = push_file_b64(str(script_path), remote_path, chunk_size=380)
    if not ok:
        print("[-] Upload failed!")
        return 1
        
    print("[*] Executing live patch on camera...")
    cmds = [
        "chmod +x /tmp/apply_opengate.sh",
        "/tmp/apply_opengate.sh",
    ]
    out, tries = run(cmds)
    print(out)
    return 0

if __name__ == "__main__":
    sys.exit(main())
