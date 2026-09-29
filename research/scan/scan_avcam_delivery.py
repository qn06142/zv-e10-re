import os, re

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
ROOT = (ROOT_REPO / 'fw').as_posix()
data = open(os.path.join(ROOT, "av-cam.bin"), "rb").read()
strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
print("av-cam.bin strings:", len(strs))

# Delivery-mechanism keywords
kw = re.compile(r"updat|Updat|UPDAT|firm|Firm|FIRM|udtr|Udtr|UDTR|body|Body|BODY|"
                r"startupdate|endupdate|/tmp_updater|bodyimg|bodylib|"
                r"UPDDAT|upd_dat|SD_UPD|sd.?upd|copy.*bin|\.bin|"
                r"service|Service|recover|Recover|RECOVER|firmup|FirmUp|"
                r"load.*firm|write.*firm|exec.*firm|flash|Flash|FLASH|"
                r"mmc|MMC|sdcard|SDCARD|/tmp/sd|/log|partition|Partition", re.I)
hits = sorted(set(s for s in strs if kw.search(s)))
print("\n=== delivery-related strings in av-cam.bin (%d) ===" % len(hits))
for h in hits[:120]:
    print("  " + h)

# Any SDF command name that's about firmware/update/body
print("\n=== SDF_* command names ===")
for s in sorted(set(strs)):
    if re.match(r"SDF_[A-Z_]+$", s):
        print("  " + s)
