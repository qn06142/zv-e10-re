#!/usr/bin/env python3
"""
msc_scsi_probe.py - raw SCSI/MSC probe of the Sony DSC W830 in Mass Storage
mode, with the MSC interface bound to WinUSB (Zadig) so libusb owns it.

Sends USB Mass Storage Class bulk CBW/CSW commands:
  1) Standard INQUIRY (0x12) - confirm transport + get vendor/model.
  2) READ CAPACITY(10) (0x25), REQUEST SENSE (0x03) - sanity.
  3) Vendor command sweep: CDB opcode 0xE0..0xFF (6-byte CDB, IN direction,
     various alloc lengths). Capture any that return data or non-failed CSW --
     these are the candidate service-mode / firmware-read entry points.

Saves to msc_scsi_results.json. Non-destructive (no writes to the device).
"""
import sys, json, struct, time
import usb.core
import usb.util

import pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]

VID, PID = 0x054c, 0x08b3
OUT = None
IN = None
TIMEOUT = 2000
JSON_PATH = (REPO / 'msc_scsi_results.json').as_posix()

def eprint(*a):
    print(*a); sys.stdout.flush()

RES = {'inquiry': None, 'standard': {}, 'vendor_sweep': {}}

def build_cbw(tag, xfer_len, flags, cdb):
    assert 1 <= len(cdb) <= 16
    cbw = b'USBC'                       # dCBWSignature (little-endian 0x43425355)
    cbw += struct.pack('<I', tag)       # dCBWTag
    cbw += struct.pack('<I', xfer_len)  # dCBWDataTransferLength
    cbw += bytes([flags, 0, len(cdb)])  # bmCBWFlags, bCBWLUN, bCBWCBLength
    cbw += cdb + b'\x00' * (16 - len(cdb))
    return cbw

def do_scsi(dev, cdb, direction=0x80, alloc=64, tag=0xDEADBEEF):
    """direction 0x80 = IN (device->host), 0x00 = OUT. Returns (status, data, residue)."""
    xfer = alloc if direction == 0x80 else 0
    cbw = build_cbw(tag, xfer, direction, cdb)
    dev.write(OUT, cbw, TIMEOUT)
    data = b''
    if xfer > 0:
        # read in chunks up to alloc (short read ends it)
        remaining = xfer
        while remaining > 0:
            try:
                chunk = dev.read(IN, min(remaining, 4096), TIMEOUT)
            except usb.core.USBError as e:
                if 'timed out' in str(e).lower() or 'timeout' in str(e).lower():
                    break
                raise
            if not chunk:
                break
            data += bytes(chunk)
            remaining -= len(chunk)
            if len(chunk) < 4096:
                break
    # read CSW (13 bytes): sig(4) tag(4) residue(4) status(1)
    try:
        csw = bytes(dev.read(IN, 13, TIMEOUT))
    except usb.core.USBError as e:
        if 'timed out' in str(e).lower() or 'timeout' in str(e).lower():
            return ('TIMEOUT', data, None)
        return ('USBERR', data, None)
    if len(csw) < 13 or csw[0:4] != b'USBS':
        return ('BAD_CSW', data, None)
    ctag, residue, status = struct.unpack('<IIB', csw[4:13])
    return (status, data, residue)

def main():
    global OUT, IN
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        eprint('No Sony MSC device (libusb). Is it bound to WinUSB + plugged?')
        return
    eprint('Found VID_054C PID_08B3')
    try:
        # On Windows+WinUSB, set_configuration() raises NotImplementedError; the
        # device is already in its active config, so skip it.
        try:
            dev.set_configuration()
        except NotImplementedError:
            eprint('(set_configuration not supported on this platform; using active config)')
        cfg = dev.get_active_configuration()
        intf = cfg[(0, 0)]
        # Select endpoints by TYPE (bulk), not just direction -- this device also
        # has an interrupt IN endpoint (0x83) that must NOT be used for CSW/data.
        for ep in intf:
            is_out = usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_OUT
            is_bulk = (ep.bmAttributes & 0x03) == usb.util.ENDPOINT_TYPE_BULK
            if is_out and is_bulk:
                OUT = ep.bEndpointAddress
            elif (not is_out) and is_bulk:
                IN = ep.bEndpointAddress
        eprint('OUT ep=0x%02X  IN ep=0x%02X (bulk)' % (OUT, IN))
        # WinUSB requires the interface to be claimed before any transfer.
        try:
            usb.util.claim_interface(dev, 0)
            eprint('claimed interface 0')
        except Exception as e:
            eprint('(claim_interface note: %r)' % e)

        # 1) INQUIRY (standard)
        st, data, _ = do_scsi(dev, b'\x12\x00\x00\x00\x24\x00', 0x80, 36)
        if st == 0 and len(data) >= 8:
            RES['inquiry'] = {
                'status': st,
                'peripheral': data[0],
                'vendor': data[8:16].decode('latin1', 'replace').strip(),
                'product': data[16:32].decode('latin1', 'replace').strip(),
                'revision': data[32:36].decode('latin1', 'replace').strip(),
                'raw_hex': data[:64].hex(),
            }
        else:
            RES['inquiry'] = {'status': st, 'data_hex': data.hex() if data else None}

        # 2) standard commands
        for name, cdb, alloc in (('READ_CAPACITY_10', b'\x25\x00\x00\x00\x00\x00\x00', 8),
                                 ('REQUEST_SENSE', b'\x03\x00\x00\x00\x12\x00', 18)):
            st, data, _ = do_scsi(dev, cdb, 0x80, alloc)
            RES['standard'][name] = {'status': st, 'data_hex': data.hex() if data else None}

        # 3) VENDOR sweep 0xE0..0xFF (6-byte CDB, IN)
        for op in range(0xE0, 0x100):
            for alloc in (0, 64, 256):
                cdb = bytes([op, 0, 0, 0, alloc & 0xFF, 0])
                try:
                    st, data, residue = do_scsi(dev, cdb, 0x80, max(alloc, 1))
                except usb.core.USBError as e:
                    RES['vendor_sweep']['op_0x%02X' % op] = {'error': str(e)}
                    break
                entry = {'status': st, 'data_len': len(data),
                         'data_hex': data[:64].hex() if data else None,
                         'residue': residue}
                # record only interesting ones (data returned, or non-failed with alloc)
                if data or st == 0:
                    RES['vendor_sweep'].setdefault('op_0x%02X' % op, {})
                    RES['vendor_sweep']['op_0x%02X' % op]['alloc_%d' % alloc] = entry
            # keep memory bounded: drop empty entries
        RES['vendor_sweep'] = {k: v for k, v in RES['vendor_sweep'].items() if v}
    except Exception as e:
        import traceback
        RES['fatal'] = traceback.format_exc()
    finally:
        try:
            usb.util.dispose_resources(dev)
        except Exception:
            pass
        with open(JSON_PATH, 'w') as f:
            json.dump(RES, f, indent=2)
    eprint('MSC SCSI probe -> %s' % JSON_PATH)

if __name__ == '__main__':
    main()
