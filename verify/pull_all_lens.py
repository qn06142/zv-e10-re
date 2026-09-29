import subprocess, glob, os

# Build the full /lens path list (57 VX files from the earlier listing)
vx = []
for a in ["8900","8901","8902","8903","8904","8905","8906","8913","8915","8916",
          "8922","8923","8928","8932","8935","8936","8937","8938","8942","8943",
          "8944","8945","8946","8948","8949",
          "9101","9102","9103","9104","9105","9106","9107","9108","9109","9110",
          "9111","9113","9114","9115","9116","9123","9124","9129",
          "9200","9201","9202"]:
    vx.append("VX%s_lensfile.bin" % a)
# add the composite ones seen in listing
for a in ["89058924","89138924","89138925","89438924","89438925","92018924",
          "92018925","92028924","92028925","89168924","89168925"]:
    vx.append("VX%s_lensfile.bin" % a)
paths = ["/lens/"+v for v in vx]
print("total lensfiles to pull:", len(paths))
# pull in one zve10_pull invocation
cmd = ["./.venv/Scripts/python.exe","zve10_pull.py"] + paths
r = subprocess.run(cmd, capture_output=True, text=True, timeout=590)
out = (r.stdout+r.stderr).splitlines()
# count ok lines
ok = sum(1 for l in out if "ok," in l)
print("pulled ok:", ok, "of", len(paths))
print("last lines:")
for l in out[-6:]: print("  ", l)
