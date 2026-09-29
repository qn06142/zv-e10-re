import os, sys, io, struct, random
sys.path.insert(0, (ROOT_REPO / 'fwtool_ma1co_repo').as_posix())
from fwtool.sony import dat as D
from fwtool.io import FilePart, ChunkedFile

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]

ROOT = ROOT_REPO.as_posix()
REAL = os.path.join(ROOT, "fw_update", "FirmwareData_ZVE10V203.dat")
OUTDIR = os.path.join(ROOT, "fuzz_dat")
os.makedirs(OUTDIR, exist_ok=True)

# Parse the real .dat to get its descriptors + firmwareData, so our forgeries are structurally valid
with open(REAL,"rb") as f:
    df = D.readDat(f)
    fw = df.firmwareData
    fw.seek(0,2); fwsize = fw.tell(); fw.seek(0)
    fwblob = fw.read()
print("real FDAT size", fwsize, "isLens", df.isLens)
print("normal descs", df.normalUsbDescriptors[:3], "... updater", df.updaterUsbDescriptors)

def build_dat(firmwareDataBlob, isLens=None,
              normalDesc=None, updaterDesc=None,
              tamper=None):
    """Build a .dat container from a firmwareData blob, optionally tampering chunk layout."""
    normalDesc = normalDesc or df.normalUsbDescriptors
    updaterDesc = updaterDesc or df.updaterUsbDescriptors
    if isLens is None:
        isLens = df.isLens
    dat = D.DatFile(
        normalUsbDescriptors=normalDesc,
        updaterUsbDescriptors=updaterDesc,
        isLens=isLens,
        firmwareData=io.BytesIO(firmwareDataBlob),
    )
    buf = io.BytesIO()
    D.writeDat(dat, buf)
    data = bytearray(buf.getvalue())
    if tamper:
        tamper(data)
    return bytes(data)

# chunk layout constants from dat.py
DATV, PROV, UDID, FDAT, DEND = b"DATV", b"PROV", b"UDID", b"FDAT", b"DEND"
def find_chunk(data, magic):
    i = data.find(magic)
    return i

# --- baseline valid forgery (re-pack real FDAT; should be accepted if CRC ok) ---
baseline = build_dat(fwblob)
open(os.path.join(OUTDIR, "00_baseline.dat"),"wb").write(baseline)
print("baseline built", len(baseline))

# --- mutants ---
random.seed(0x5A1E10)
mutants = []
def mut_fdat_oversize(data):
    # claim FDAT is 4GB (length field after FDAT magic)
    i = find_chunk(data, FDAT)
    if i>=0:
        # dat.py: u32 size follows the 4-byte magic
        struct.pack_into("<I", data, i+4, 0xFFFFFFFF)
mutants.append(("01_fdat_oversize", mut_fdat_oversize))

def mut_fdat_trunc(data):
    i = find_chunk(data, FDAT)
    if i>=0:
        struct.pack_into("<I", data, i+4, 16)  # claim tiny
mutants.append(("02_fdat_trunc", mut_fdat_trunc))

def mut_no_dend(data):
    # remove DEND (CRC) chunk entirely
    i = find_chunk(data, DEND)
    if i>=0:
        # find next chunk boundary: DEND is [magic][u32 size=12][crc]; delete 4+4+? bytes
        # dat.py DEND chunk size = 12 (header) + crc? just delete 20 bytes
        del data[i:i+20]
mutants.append(("03_no_dend", mut_no_dend))

def mut_dend_zero_crc(data):
    # DEND CRC is the last 4 bytes of the container (writeDat back-patches it there)
    data[-4:] = b"\xde\xad\xbe\xef"
mutants.append(("04_dend_bad_crc", mut_dend_zero_crc))

def mut_udid_zero(data):
    i = find_chunk(data, UDID)
    if i>=0:
        struct.pack_into("<I", data, i+4, 0)  # zero the UDID data size
mutants.append(("05_udid_zero", mut_udid_zero))

def mut_datv_bad(data):
    i = find_chunk(data, DATV)
    if i>=0:
        struct.pack_into("<I", data, i+4, 0x7FFFFFFF)  # huge DATV size
mutants.append(("06_datv_oversize", mut_datv_bad))

def mut_fdat_garbage(data):
    i = find_chunk(data, FDAT)
    if i>=0:
        sz = struct.unpack_from("<I", data, i+4)[0]
        if i+8+sz <= len(data):
            # flip every 256th byte of the (encrypted) FDAT payload
            for off in range(i+8, i+8+sz, 256):
                data[off] ^= 0xFF
mutants.append(("07_fdat_flipped", mut_fdat_garbage))

def mut_fdat_len_mismatch(data):
    i = find_chunk(data, FDAT)
    if i>=0:
        real = struct.unpack_from("<I", data, i+4)[0]
        struct.pack_into("<I", data, i+4, real + 4096)  # length says 4KB more than present
mutants.append(("08_fdat_len_plus4k", mut_fdat_len_mismatch))

for name, fn in mutants:
    try:
        blob = build_dat(fwblob, tamper=fn)
        open(os.path.join(OUTDIR, name+".dat"),"wb").write(blob)
        print("built", name, len(blob))
    except Exception as e:
        print("FAIL", name, e)

print("\nFuzz corpus in", OUTDIR)
print("To run: copy one next to FirmwareUpdaterEg.exe as 'FirmwareData_ZVE10V203.dat', launch exe, observe cam.")
