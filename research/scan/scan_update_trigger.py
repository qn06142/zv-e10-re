import os, re

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
ROOT = (ROOT_REPO / 'fw').as_posix()
data = open(os.path.join(ROOT, "av-cam.bin"), "rb").read()
strs = [s.decode("latin1","replace") for s in re.findall(rb"[ -~]{4,}", data)]
uniq = sorted(set(strs))

# update-mode SD trigger: filenames / patterns the updater looks for on removable media
pat = re.compile(r"\.bin|\.dat|\.exe|\.upd|\.fup|UPDATE|update|firmware|FIRMWARE|"
                 r"sony|SONY|PMCA|pmca|/tmp/sd|/mnt/sd|mmc|MMC|sdcard|SDCARD|"
                 r"root|ROOT|/setting|/system|version|VERSION|body|Body|BODY|"
                 r"udtr|UDTR|load.*bin|firm.*bin|upd.*bin", re.I)
print("=== SD/file-update trigger filename candidates ===")
seen = set()
for s in uniq:
    if pat.search(s) and ("/" in s or s.lower().endswith(".bin") or s.lower().endswith(".dat")
                          or "update" in s.lower() or "firm" in s.lower()
                          or "udtr" in s.lower() or "body" in s.lower()):
        if s not in seen:
            seen.add(s)
            print("  " + s)

# specifically: any string ending in .bin or .dat that is NOT a lensfile/sabin/psd
print("\n=== *.bin / *.dat filenames (update-relevant filter) ===")
for s in uniq:
    mm = re.search(r"[\w/.-]+\.(bin|dat|exe|upd|fup)\b", s)
    if mm and not re.search(r"lensfile|sabin|psd|BNB_|FILE_BNB|vcd_firmware|"
                            r"dfe\.bin|udrt_dic", s):
        print("  " + s)

# update-mode entry strings
print("\n=== update-mode / recovery-mode entry ===")
for s in uniq:
    if re.search(r"update[_]?mode|recovery|Recovery|boot[_]?mode|service[_]?mode|"
                 r"force[_]?update|mass[_]?storage|MSC|enter.*update|start.*update", s, re.I):
        if s not in seen:
            print("  " + s)
