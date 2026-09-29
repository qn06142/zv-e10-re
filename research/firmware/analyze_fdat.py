import os, sys
sys.path.insert(0, (ROOT_REPO / 'fwtool_ma1co_repo').as_posix())
from fwtool.sony import dat as D
from fwtool.io import FilePart

DAT = (ROOT_REPO / 'fw_update/FirmwareData_ZVE10V203.dat').as_posix()
import io
with open(DAT, "rb") as f:
    df = D.readDat(f)
    # copy FDAT out before f closes
    fd = df.firmwareData
    fd.seek(0, 2); sz = fd.tell(); fd.seek(0)
    blob = fd.read()
print("isLens:", df.isLens)
print("normalUsbDescriptors (vid,pid):", df.normalUsbDescriptors)
print("updaterUsbDescriptors (vid,pid):", df.updaterUsbDescriptors)
print("FDAT firmwareData size:", sz)
head = blob[:64]
print("FDAT first 64 bytes:", head.hex())
print("FDAT ascii head:", head)
# is it the ash CX0900AP body? try fwtool decoders
from fwtool.sony import ash as A
print("isAsh(CX0900AP body)?", A.isAsh(io.BytesIO(blob)))
from fwtool.sony import msfirm as M
print("isMsFirm(old memstick)?", M.isMsFirm(io.BytesIO(blob)))
print("contains av-cam LIRO 0a0000ea:", blob.find(b"\x0a\x00\x00\xea")>=0)
print("contains udtrbody magic 453dcd28:", blob.find(b"\x45\x3d\xcd\x28")>=0)
print("contains CX0900AP:", b"CX0900AP" in blob)
print("contains FirmwareBody / BodyUdtr / av_udtr:",
      b"BodyUdtr" in blob, b"av_udtr" in blob, b"FirmwareBody" in blob)
# entropy of FDAT head vs tail to see if encrypted
import math
from collections import Counter

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]
def ent(b):
    if not b: return 0
    c=Counter(b); n=len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values())
print("FDAT entropy head 4KB: %.3f  tail 4KB: %.3f" % (ent(blob[:4096]), ent(blob[-4096:])))
