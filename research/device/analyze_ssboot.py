import tarfile, io, re

with tarfile.open('F:/RE_DUMP/TREES/system.tgz') as t:
    for name in ['system/sabin/ssboot.bin', 'system/sabin/ssboot_any.bin', 'system/sabin/idt_cam.bin']:
        data = t.extractfile(name).read()
        print(f'=== {name} (size {len(data)}) ===')
        print('Magic / first 32 bytes:', data[:32].hex())
        strs = re.findall(rb'[\x20-\x7e]{4,}', data)
        for s in strs[:25]:
            print(' ', s.decode('ascii', errors='replace'))
