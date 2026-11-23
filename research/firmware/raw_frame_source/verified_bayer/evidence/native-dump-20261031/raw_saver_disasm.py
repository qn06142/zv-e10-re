from pathlib import Path
import sys,contextlib
from elftools.elf.elffile import ELFFile
sys.path.insert(0,'D:/02_Development_And_Projects/pmca-re')
from research.firmware.annotate import annotate
p=Path('D:/02_Development_And_Projects/pmca-re/.local/dumps/camera_2025/usr/usr/lib/CameraOnDemandSaver.so');o=Path('.local/outputs/sensor-bayer-20261031/ondemand-saver-disassembly.txt')
with p.open('rb') as f:
 e=ELFFile(f);names=[s.name for s in e.get_section_by_name('.dynsym').iter_symbols() if s['st_size'] and s['st_value'] and ('threadE' in s.name or any(k in s.name for k in ['linux_write','file_write_exe','fsys_write','snd_msg','set_mmap']))]
with o.open('w') as f,contextlib.redirect_stdout(f):
 for n in names:annotate(p,n)
print(o)
