# Sony DSC W830 — PTP/MTP Reverse-Engineering Notes

> Scripts mentioned below by bare filename now live under `research/`;
> see `research/README.md` for the index.

Captured: 2026-08-01. Camera in PTP/MTP mode (USB). Windows 11, pmca via
**libusb/WinUSB** driver (Zadig-bound "Sony Digital Still Camera" -> WinUSB).
WPD (native) driver wedges the device; use -d libusb for repeatable sessions.

## CRITICAL device quirk (learned empirically)
- The W830's MTP session state is FRAGILE. A clean plug gives ONE good session.
  Repeated OpenSession / mixed native+libusb probing / killed processes wedge
  it (next OpenSession returns a DATA packet instead of RESPONSE, or COM errors).
- Recovery = physically unplug + replug the camera. No software reset works.
- To avoid wedging: one probe process per plug, never send CloseSession, let
  the process exit normally (pmca's libusb context does NOT send CloseSession
  on exit, so the camera stays usable until next plug).
- WPD (native) is WORSE: it owns its own session and fights our ops, and a
  CloseSession permanently wedges until replug.

## Device identification (GetDeviceInfo, 283 bytes, saved: di_dump.bin)
- manufacturer : Sony Corporation
- model        : Sony Digital Still Camera
- serial       : 00000000000000008081537008252880
- vendor_ext   : 'FUJITSU PTP Extensions'   <-- W830 uses Fujitsu/FinePix PTP exts
- Supported operations (verified, 17 total):
  0x1001 GetDeviceInfo   0x1002 OpenSession   0x1003 CloseSession
  0x1004 GetStorageIDs   0x1005 GetStorageInfo 0x1006 GetNumObjects
  0x1007 GetObjectHandles 0x1008 GetObjectInfo 0x1009 GetObject 0x100a GetThumb
  0x1014 GetDevicePropDesc 0x1015 GetDevicePropValue 0x101b GetDevicePropList
  0x9801 0x9802 0x9803 0x9805   (vendor, see below)

## Storage
- One volume, handle 0x00020001, ~47.7 MB total, ~34.4 MB free, FAT fs.
- GetNumObjects => 0 ; GetObjectHandles (any storage/parent) => 0 objects.
  Standard PTP object enumeration is NOT exposed. Transfer goes through the
  Fujitsu PTP extensions / vendor ops instead.

## Vendor opcode behavior (0x98xx) — FULLY CHARACTERIZED (WinUSB, clean runs)
All probed with tolerant read (captures DATA+RESPONSE, never crashes on type).

- 0x9801 : RESP 0x2001 (OK), NO data phase. -> status/ack vendor op.
- 0x9802 : RESP 0xA80A on EVERY arg (0, 1, 2, 0x100, 0x9805...). 0xA80A is a
           vendor-defined response code (not in std PTP table). Looks like a
           mode-gated / "not applicable in this mode" rejection. Possibly the
           Fujitsu "GetObject" path that needs a valid object handle as arg.
- 0x9803 : RESP 0x2001 (OK), NO data phase. -> status/ack vendor op.
- 0x9805 : DATA (uint32 LE) + RESP 0x2001.
           arg = 0      -> 0x00000000
           arg = nonzero -> 0x00000001   (tested arg in {1..20}, opcodes,
                           powers of 2, 2-arg (idx,len) forms -> ALL return 1)
           => BOOLEAN ACCESSOR: returns 1 iff arg != 0. Not an index/count map,
              not object enumeration. Likely an enable/query flag.

DECODED: the 4 vendor ops are NOT a hidden object table. 0x9801/0x9803 are
status acks, 0x9805 is a boolean flag, 0x9802 is a vendor rejection code.
Real image/file transfer is via the Fujitsu PTP extensions (vendor string),
which likely means 0x9802 takes a valid object HANDLE as arg and returns the
object through GetObject (0x1009) — but we have no handle source from standard
enumeration, so that path is gated behind something we haven't unlocked.

## Unlock-sequence probe (2026-08-01, fresh plug, -d libusb)
Tested: does a vendor handshake unlock 0x9806..0x981F? Variants:
  A: 0x9801([1]) + 0x9805([1])  then rescan
  B: 0x9805([1]) + 0x9803([1])  then rescan
  C: 0x9802([0x20000001])        then rescan
Findings:
- Most "flips" are just error-code churn (0x2005/0x200b/0xa80a are all
  REJECTIONS; the response code changes but the op still returns nothing).
- REAL behavioral change: after variant A, 0x9808/0x9809 become responsive
  (were 0x2005-rejected at baseline).
    - 0x9808 -> RESP 0x2001, no data (ACK)
    - 0x9809 -> RESP 0x2005 + DATA '01000000' (uint32 = 1)
  So 0x9808/0x9809 are STATE-GATED vendor flag/status ops, not object
  enumerators. They return a single uint32, not a handle list.
- NO op in 0x9806..0x981F returned a handle list or object bytes.
CONCLUSION: the file/image transfer path is NOT reachable by opcode scanning
+ a simple flag handshake. The Fujitsu PTP extension needs either (a) a longer
specific unlock sequence, (b) the camera in a particular USB mode (PC Remote /
Mass Storage / MTP — check the on-screen menu), or (c) a different entry point
(e.g. a vendor "GetObject" that needs a handle sourced outside standard PTP).

## Deep3: 16-cycle handshake BURST (2026-08-01)
Ran 16 cycles of (0x9801,0x9805,0x9803,0x9805) = 64 handshake cmds, then FULL
rescan 0x9801..0x981f, then arg-probe every awake op.

RESULT (surprising): FEWER ops awake than deep2:
  awake: 0x9801, 0x9803, 0x9806 ONLY. 0x9805 dead this run (was alive before).
  still-dead: 0x9804,0x9805,0x9807..0x981f (uniform 0x2005).
CONCLUSION: unlock is NOT "more cycles = more awake". Overshooting the
handshake (64 cmds) drives the device to a LESS-unlocked / possibly wedged
state. The sequence is a sensitive SWEET-SPOT, not a volume knob. deep2's
moderate handshake (~10 steps) gave the BEST wake (0x9806/7/8 + 0x980b/c/d/f).

## Consolidated unlock finding
- The handshake is CUMULATIVE-per-session and sequence-sensitive.
- Best observed wake state (deep2): 0x9806,0x9807,0x9808,0x980b,0x980c,0x980d,
  0x980f respond (0x2001); 0x980b/0x980d return DATA uint32=1.
- Brute-forcing burst length plateaus: NO vendor op in 0x9801..0x981f ever
  returned a handle list or object bytes -- only uint32 flags (=1).
- 2-arg forms (storage,parent) on awake ops: 0x200b (InvalidParameter) vs 0x2005
  for 1-arg -- arg count changes parsing but still no data.
- 0x9805([handle-like]) as GetObject: 0x2005 (locked).

## Mass Storage (VID_054C/PID_08B3) SCSI probe (2026-08-01, fresh plug)
Bound MSC interface to WinUSB via Zadig; raw SCSI/MSC CBW/CSW probe.

Endpoint layout (msc_diag.py): interface 0 = MSC(0x08)/SCSI(0x06)/BOT(0x50):
  ep 0x81 IN  BULK   (data/CSW -- USE THIS)
  ep 0x02 OUT BULK   (CBW -- USE THIS)
  ep 0x83 IN  INTR   (do NOT use for bulk transport)
KEY BUG: naive "first IN/OUT wins" endpoint scan grabbed 0x83 (interrupt) as the
IN endpoint -> every CSW read hit intr_read and TIMED OUT. FIX: select by TYPE
(bulk), not just direction. After fix: transport works.

RESULTS:
  INQUIRY  -> Sony / DSC / 1.00 (peripheral 0, direct-access) OK
  READ_CAPACITY(10) -> 0xDE00 blocks *512 = 29,098,496 B (== msc_dump.bin size) OK
  REQUEST_SENSE -> clean OK
  Vendor sweep 0xE0..0xFF -> ALL return Pipe error (STALL). Camera rejects every
    vendor SCSI CDB on the bulk interface. NO firmware/service-mode reachable
    via SCSI vendor commands here.

CONCLUSION: Both USB attack surfaces (MTP vendor ops 0x9801..0x981f, and MSC
SCSI vendor CDBs 0xE0..0xFF) are locked down -- they only return flags/stalls.
The bootloader/firmware is NOT exposed over either interface in normal Mass
Storage mode. Remaining paths:
  1. Analyze msc_dump.bin (29MB user partition) for service-mode strings,
     model IDs, or a hidden firmware blob in non-FAT regions (pure RE).
  2. Try the INTERRUPT endpoint (0x83) for vendor control messages.
  3. A specific file written to the MSC volume (e.g. the *.IND control files
     like BLTINMEM.IND) may trigger a mode / service entry.
  4. Camera USB-mode menu (PC Remote / Mass Storage / MTP) -- user to check.
  5. Sony service-mode is often a button combo / specific USB sequence at boot,
     not an opcode -- out of scope for USB RE alone.

## Workflow tooling (added)
- nag_reboot.py / run_after_reboot.py : replug gate (nag -> wait_for_device -> run).
  Use for ANY probe needing a fresh session: python run_after_reboot.py <probe>.py
- msc_dump.py : admin raw-disk dump of \\.\PhysicalDriveN (skill: windows-raw-disk-dump).
- msc_diag.py : dumps all interfaces/endpoints of the MSC device.
- msc_scsi_probe.py : CBW/CSW SCSI probe (INQUIRY + READ_CAPACITY + REQUEST_SENSE
  + vendor sweep 0xE0..0xFF). NOTE: select BULK endpoints by type, not direction.
- ptp_*.py, ptp_unlock*.py, ptp_deep*.py : MTP-side vendor-op probes (done).
1. CAMERA USB MODE MENU (PC Remote / Mass Storage / MTP). This is a device
   setting the agent cannot change programmatically -- needs the user to check
   the on-screen menu. The Fujitsu file path may only unlock in one mode. This
   is the highest-value untested variable.
2. Exact handshake SWEET-SPOT (deep2's ~10-step sequence) + immediate rescan
   before any other op, to capture the peak-wake moment cleanly.
3. Decode 0x2005/0x200b/0xA80A against FinePix/Fujitsu PTP extension docs.
The simple 0x9801+0x9805 handshake only woke 0x9808/0x9809 (flag ops). Longer
ordered sequences progressively unlock MORE ops:

After LONG  (0x9801,0x9805,0x9803,0x9805): 0x9806/0x9807/0x9808 -> RESP 0x2001;
  0x9807/0x9808 return DATA '01000000' (uint32=1). 0x980a -> 0x200b.
After ALT   (0x9805,0x9801,0x9805,0x9803,0x9805): 0x9806/0x9807/0x9808 -> 0x2001;
  0x9806/0x9808 return DATA '01000000'.

KEY FINDING: the unlock handshake is CUMULATIVE — each step wakes more vendor
ops, and the woken ops return a single uint32 (=1), not handle lists yet. The
Fujitsu enumerator is likely reached by (a) a still-longer sequence, or (b)
the now-responsive ops (0x9806/0x9807/0x9808) being entry points that need a
real object HANDLE/index as arg (e.g. 0x9808([handle]) returns the object, not
0x9808([1])). Next: probe 0x9806/0x9807/0x9808 with varied args now that awake.

## Verified vendor-op map (updated)
0x9801/0x9803 : status/ack (0x2001). Gate-enablers for other ops.
0x9802 : vendor reject (0xA80A) on all args.
0x9805 : boolean flag (DATA uint32; arg 0 -> 0, else -> 1).
0x9806 : gated; after handshake -> 0x2001, DATA uint32=1 (with some sequences).
0x9807 : gated; after handshake -> 0x2001, DATA uint32=1.
0x9808 : gated; after handshake -> 0x2001, DATA uint32=1.
0x9809 : gated; after 0x9801+0x9805 -> 0x2005 + DATA uint32=1.
0x980a : gated; after handshake -> 0x200b (invalid param; needs correct arg).
0x980b..0x981f : still rejected (0x2005) after the sequences tried so far.

## Workflow tooling (added)
- nag_reboot.py        : always-on-top "OK, I rebooted it" window; blocks until
                         clicked. Importable nag_reboot.nag_reboot().
- run_after_reboot.py  : GATE wrapper -> nags, waits for libusb device to
                         enumerate (wait_for_device, 20s), THEN runs a probe.
                         Usage: python run_after_reboot.py <probe>.py -d libusb
                         This makes "user rebooted" a hard gate before probing.
- ptp_unlock2.py       : longer/alt unlock handshake scan (results: ptp_unlock2_results.json)

## Tooling (pmca-re/)
- venv (Python 3.12), libusb1 DLL in .venv/Scripts. Run with -d libusb.
- re_probe.py        : DeviceInfo + storage + (empty) object walk.
- ptp_probe.py       : broad PTP extension sweep, watchdog+incremental JSON.
- ptp_probe2.py      : focused sweep (GetDevicePropList + 0x9805 arg sweep).
- ptp_raw.py         : raw pyusb capture (needs device free; releases on exit).
- ptp_trace.py       : monkeypatched MtpDriver tracer (captures every packet).
- ptp_9805_sweep.py  : 0x9805 arg 0..20 + 2-arg variants  -> ptp_9805_sweep.json
- ptp_deep.py        : opcodes/wide/2-arg probe of 0x9805 + tolerant 0x9801/2/3
                        -> ptp_deep_results.json
- di_dump.bin        : raw 283-byte GetDeviceInfo payload (parses via pmca).
- ptp_probe_results.json, ptp_probe2_results.json, ptp_trace_results.json,
  ptp_9805_sweep.json, ptp_deep_results.json : captured runs.

## How to run cleanly
1. Plug camera (PTP/MTP mode). One plug = one session.
2. cd /d/02_Development_And_Projects/pmca-re && . .venv-re/bin/activate
3. python <script>.py -d libusb      (libusb only; native wedges)
4. Read the matching *.json. Do NOT re-run without replugging.

## Service manual lead (2026-08-01, from Sony DSC-W830 / DSC-WX50 service manual)
User provided a Sony service manual excerpt (full DESTINATION DATA / RESTORE
DATA / Adjust Station section). USB-RELEVANT facts only; hardware steps (330V
cap, SY-1035/SW-1002 board) are OUT OF SCOPE (user is USB-only).

CONFIRMED:
- "Adjust Station" is Sony PC software; it launches the model "Adjust Manual"
  and performs "Destination Data Write" / "RESTORE DATA" / "PRODUCT ID &
  USB SERIAL No. INPUT". These write: Product ID, USB Serial No., Hash data,
  AWB standard data -- all stored on the BOARD's flash/NVRAM.
- For this model the DSC-WX50-series Adjust Manual must be pre-installed.
- USB Serial No. is "unique to each unit"; Product ID "unique to each model".
  A new service board has NEITHER written -> Adjust Station enters them.

KEY READ vs WRITE: a working camera ALREADY has USB Serial No. + Product ID
written. Adjust Station WRITES them to blank boards. So they should be READABLE
over USB without service mode:
  - USB Serial No. == likely the USB iSerialNumber string descriptor.
  - Product ID == possibly an MTP Device Property / object, or in DeviceInfo.
Reading these is pure USB, non-destructive, no Adjust Station needed.

HARD LIMIT (honest): the firmware/binary itself is on the board flash and is
NOT exposed by Mass Storage (user partition only), MTP vendor ops (flags
only), or MSC SCSI vendor CDBs (all STALL). Adjust Station is the documented
way to talk to the service channel, but its wire protocol is proprietary and
unavailable to us. So over the two reachable USB modes we CANNOT dump the
firmware binary. Best USB-only outcome: read the service identifiers
(USB Serial / Product ID) and probe the MSC interrupt endpoint (0x83).

## USB string descriptors read (2026-08-01, usb_ids.py)
Non-destructive read of iManufacturer/iProduct/iSerialNumber on PID_08B3
(Mass Storage mode). Result:
  iManufacturer = Sony
  iProduct      = DSC-W830
  iSerialNumber = C710A07DEDD0   <-- this IS the per-unit "USB Serial No." the
                                     service manual says Adjust Station writes.
                                     Readable over plain USB, no service mode.
  bcdDevice     = 0x0100 (fw/device v1.00, matches INQUIRY revision 1.00)
  bDeviceClass  = 0x00 (per-interface)
Only ONE Sony PID present in Mass Storage mode: 0x08B3. (0x094B MTP not
attached because camera is in MSC mode.)

CONCLUSION: the readable service identifiers (USB Serial No = iSerial) are
accessible over normal USB. The writable/config ones (Hash, AWB, re-write
Serial/Product, "Destination Data") require Adjust Station (proprietary, we
don't have it). So USB-only RE can READ these IDs but cannot dump the firmware
binary or enter the service WRITE channel without Adjust Station.

## MSC interrupt endpoint 0x83 probe (2026-08-01, msc_intr_probe.py, live)
Ran via nag gate (fresh plug). Result: claimed iface 0, found intr IN ep 0x83,
read 0 -> [Errno 10060] Operation timed out. No data ever arrives on the
interrupt endpoint in normal Mass Storage mode. => DEAD END.

## Online RE search findings (2026-08-01)
Goal: find a USB-only / software-only way to get the W830 firmware, since direct
device RE is exhausted.

FINDINGS:
1. ma1co/Sony-PMCA-RE (the repo our `pmca` package is from) can "dump firmware"
   + install Android apps -- BUT only on ANDROID-based Sonys via `serviceshell`
   over MTP. The W830 (2013 budget point-and-shoot) is almost certainly NOT
   Android/PMCA-capable. => that door is CLOSED for this model.
   Also: our installed `pmca` is a submodule (pmca/usb/sony.py etc.), NOT the
   `pmca-console` app, so even the Android path isn't wired up here.
2. Sony distributes firmware as DOWNLOADABLE updater packages
   (.exe/.app -> FirmwareData_*.dat or 0xNNNNNNNN.zip). The firmware BINARY
   ships inside the updater. => If a W830 updater exists, we can extract the
   firmware from it -- pure software, no device, no board. THIS matches the
   user's goal ("dump the firmware").
3. XDA "Unpack any Sony firmware file" tool confirms Sony firmware blobs unpack
   to ARM ELF (ELF32, Machine: ARM, entry 0x8000). So once we have the updater,
   known unpack path to the actual firmware image exists (binwalk + ELF parse).
4. elektrotanya.com has "SONY DSC-WX50 ADJUST SM" PDF -- the Adjust service
   manual referenced by the user's manual (Destination Data Write). May document
   the service USB mode entry.
5. W830's own Sony support page shows only DRIVERS, no firmware updater listed
   (query for "Update_W830"/"DSCW830 updater.exe" returned nothing). Likely the
   W830 firmware is NOT updatable via USB / no public updater. Need to confirm.

CONCLUSION: direct-device USB RE is exhausted. The realistic firmware-acquisition
path is: obtain a Sony firmware UPDATER package for the W830 (or a close sibling
like WX50/W800) and unpack it -> ARM ELF firmware. This is software-only, within
the user's USB-only/no-board constraint (it's a download, not hardware).

NEXT (software-only):
  - Confirm whether ANY W830/WX50/W800 firmware updater is downloadable. Check
    Sony JP/region pages + the XDA unpacker; siblings share SoC/fw often.
  - If found: download updater, extract the .dat/zip, run binwalk, parse ARM ELF.
  - If no updater exists: the firmware binary is not publicly available; USB RE
    + download RE both exhausted. Document as complete.
  - Fetch the DSC-WX50 ADJUST SM PDF from elektrotanya for the service-mode doc.
All reachable USB surfaces probed, every one a dead end at the firmware/service
level (normal Mass Storage + PTP/MTP modes, no button combo tried):

  Surface                          | Result
  ---------------------------------|---------------------------------------
  MTP vendor ops 0x9801-0x981f     | only uint32 flags; no handle/obj data
  MSC bulk SCSI vendor CDBs 0xE0-FF| all STALL (Pipe error)
  MSC raw disk (29MB)              | user partition only; no firmware
  USB string descriptors           | READABLE: iSerial=C710A07DEDD0 (USB
                                   |   Serial No.), iProduct=DSC-W830. No fw.
  MSC interrupt endpoint 0x83      | idle/timeout, no data

CONCLUSION (honest): the firmware BINARY is NOT obtainable over USB on this
camera in normal modes. The only documented service channel is "Adjust Station"
(Sony proprietary PC software + DSC-WX50 Adjust Manual), whose wire protocol we
do not have. USB-only RE cannot dump the firmware or enter the service WRITE
channel.

Only remaining USB-only possibility NOT yet tried:
  - Hold a button combo (Menu/Play/Zoom etc.) at USB-plug to see if a 3rd PID
    or service mode appears. User states only Mass Storage + PTP/MTP exist, but
    a combo can still change the exposed PID/extension set. Low confidence.

If Adjust Station / DSC-WX50 Adjust Manual can be obtained, that is the real
key to the service channel (writes USB Serial, Product ID, Hash, AWB).
Otherwise USB RE is complete at the firmware-dump level.
The bulk endpoints (0x81/0x02) gave standard MSC + STALL on vendor CDBs. The
interrupt IN endpoint 0x83 is unused by our probes and may carry vendor/service
control messages. Plan: msc_intr_probe.py reads 0x83 (claimed iface) looking
for any data; run via nag gate (fresh plug, may wedge handle). If it also
stalls/times out -> USB surface fully exhausted.
1. usb_ids.py: read iManufacturer/iProduct/iSerialNumber for PID_094B +
   PID_08B3; enumerate ALL Sony PIDs currently present. (iSerial == USB
   Serial No.)
2. Probe MSC interrupt endpoint 0x83 (untried; may carry service control msgs).
3. (user) Hold a button combo at plug to see if a 3rd PID/service mode appears
   (manual hints at hidden functions; user says only Mass Storage + PTP/MTP
   exist, but a combo may still change PID/extension set).
4. (user) Obtain Adjust Station + DSC-WX50 Adjust Manual if service-channel
   access is required -- that is the real key, and we don't have it.
User provided a Sony service manual excerpt. USB-RELEVANT facts only (hardware
sections -- 330V cap discharge, SY-1035/SW-1002 board replacement -- are OUT OF
SCOPE; user is USB-only, will NOT touch the board):

- "Adjust Station" PC software does "Destination Data Write" + "RESTORE DATA",
  transferring Product ID, USB Serial No., Hash data, AWB standard data.
  => USB Serial No. among restorable fields => the service channel is USB.
- Adjust Manual (DSC-WX50 series) must be pre-installed on host PC to enable
  "Destination Data Write" => Adjust Station is a real PC-side USB client that
  talks to the camera in SOME service/adjust mode.
- Flash error E:91:01; reset via MENU->Settings->Main Settings->Initialize->OK
  (menu path, not USB -- but proves hidden service functions exist in fw).

IMPLICATION: there IS a USB service/adjust entry point we haven't found. Likely:
  (a) a distinct USB PID/mode the camera exposes only in a service mode
      (entered by a button combo at USB-plug, or a "PC Remote"/service menu),
  (b) OR a vendor PTP/MTP opcode / MSC vendor SCSI command we haven't hit
      because the camera wasn't in the right mode.
We have only scanned PID_094B (MTP/PMCA) and PID_08B3 (MSC bulk). Adjust
Station probably uses a THIRD PID or a mode we haven't triggered.

NEXT USB STEPS (respecting USB-only):
  1. Enumerate ALL USB PIDs the camera exposes: in each on-screen USB mode
     (Mass Storage / MTP / PC Remote?) AND while holding a button combo at
     plug (common Sony service-entry trick). We only know 094B + 08B3.
  2. Identify how Adjust Station connects (USB mode/cable) -- user to check
     manual or camera menu. If a 3rd PID appears, probe it like we did 08B3.
  3. The "USB Serial No." / "Hash data" write suggests a service PTP object or
     vendor op on that channel -- hunt for it once the mode/PID is known.

## Open questions for user
- Which USB mode is the camera currently set to (Mass Storage / MTP / PC Remote)?
- Does the manual show how Adjust Station physically connects (USB mode, button
  combo at plug, specific cable)?
- Does the user have Adjust Station SW / the DSC-WX50 Adjust Manual?
