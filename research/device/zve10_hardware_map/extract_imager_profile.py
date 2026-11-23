"""Recover native imager initialization and command uploads using a saved Backup.

Offline only. Sony event waits are recorded and modeled successful, so the
result is not an executable hardware initialization recipe. Raw command bytes
and profile bytes are written only when explicitly requested to a local output.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (
    UC_ARM_REG_CP_REG, UC_ARM_REG_FPEXC, UC_ARM_REG_LR, UC_ARM_REG_PC,
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP,
)

from audit_imager_control import IMAGE_BASE, IMAGE_SHA256

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from pmca.backup import BackupFile

SCRATCH, STOP = 0x20000000, 0x20008000
PROFILE_IDS = (0xbc0003, 0xbc0005, 0xbc0006, 0xbc000f, 0xbc0013, 0xbc0015,
               0xbc0001, 0xbc0002, 0xbc000d, 0xbc000e, 0xbc0000, 0xbc0010,
               0x1320000, 0x1320001, 0x1320002, 0x1320003, 0x1320004, 0x1320005, 0x1320006)
PROFILE_VAS = (0x640ba460, 0x640ba560, 0x640ba660, 0x640ba6e0, 0x640ba7e0, 0x640ba2c0,
               0x640bd5e0, 0x640ca9c0, 0x640da8c0, 0x640ba8e0, 0x640be1c0, 0x641228c0,
               0x640fa8c0, 0x641098c0, 0x640ba9e0, 0x641188c0, 0x640e98c0, 0x640f88c0, 0x640c31c0)


def recover(firmware, backup, mode, profile_dir=None, from_mode=None, *, frame_request=None):
    if frame_request is not None and (mode != 0x37 or from_mode is None or len(frame_request) != 32):
        raise ValueError("A 32-byte frame request requires mode 0x37 and a prior mode")
    image = firmware.read_bytes()
    identity = hashlib.sha256(image).hexdigest()
    if identity not in (IMAGE_SHA256, "98f05bebd113cb5b4911d71384e5ae7cec21dd4494b0f0569bb2f1b2b3231c6b"):
        raise ValueError("Unexpected firmware identity")
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    cpu.mem_map(IMAGE_BASE, (len(image) + 4095) & ~4095)
    cpu.mem_write(IMAGE_BASE, image)
    for base, length in ((SCRATCH, 0x10000), (0xfc000000, 0x1000000),
                         (0xf3000000, 0x1000000), (0xf2910000, 0x3000)):
        cpu.mem_map(base, length)
    if from_mode is not None:
        # The native mode switch reads an ADC value and uses VFP instructions.
        cpu.mem_map(0xf2406000, 0x2000)
        cpu.reg_write(UC_ARM_REG_CP_REG, (15, 0, 0, 1, 0, 0, 2, 0xf00000))
        cpu.reg_write(UC_ARM_REG_FPEXC, 1 << 30)
    report = {"reference_sha256": identity,
              "backup_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
              "profile_source": "captured-properties" if profile_dir else "saved-backup",
              "requested_internal_mode": mode, "prior_mode_replayed": from_mode,
              "camera_access": False,
              "hardware_tested": False, "initialization_complete": False,
              "host_calls": [], "mmio_writes": [], "uploads": [], "profiles": []}
    phase = "constructor"

    def read_property(key):
        if profile_dir is None:
            return bf.getProperty(key).data
        # A current-profile run must never silently fall back to archived data.
        return (profile_dir / f"profile-{key:08x}.bin").read_bytes()

    def word(address):
        return struct.unpack("<I", cpu.mem_read(address, 4))[0]

    def host(uc, address, _size, _ctx):
        args = [uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        r0, r1 = args[:2]
        record = {"phase": phase, "entry": hex(address), "args": [hex(a) for a in args]}
        result = 0
        if address in (0x635df7d4, 0x635df9b8, 0x635df80c):
            data = read_property(r0)
            if address == 0x635df7d4:
                result = len(data)
            elif address == 0x635df9b8:
                if len(data) > 4: raise ValueError("Oversized four-byte Backup read")
                result = int.from_bytes(data, "little")
            else:
                uc.mem_write(r1, data)
                result = 1
        elif address == 0x635df860:
            record["properties"] = []
            for index in range(64):
                key = word(r0 + index * 4)
                if key == 0: break
                target = word(r1 + index * 4)
                data = read_property(key)
                uc.mem_write(target, data)
                record["properties"].append({"id": hex(key), "target": hex(target), "bytes": len(data)})
            else:
                raise ValueError("Unterminated Backup read list")
            result = 1
        elif address == 0x635df1cc:
            record["hardware_wait_modeled_successful"] = True
        elif address in (0x6396f8c4, 0x6396e9d0):
            record["trace_suppressed"] = True
        else:
            record["host_service_modeled"] = True
        report["host_calls"].append(record)
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    # Backup reads, callback registration, tracing, Linux IRQ-enable wrapper,
    # and event set/clear/wait. No hardware accessor is intercepted.
    for address in (0x635df7d4, 0x635df9b8, 0x635df80c, 0x635df860,
                    0x635df980, 0x6396f8c4, 0x635df56c,
                    0x635df194, 0x635df1b0, 0x635df1cc):
        cpu.hook_add(UC_HOOK_CODE, host, begin=address, end=address)
    if from_mode is not None:
        # The still transition emits an IPC trace record via the firmware log queue.
        cpu.hook_add(UC_HOOK_CODE, host, begin=0x6396e9d0, end=0x6396e9d0)

    def upload(uc, _address, _size, _ctx):
        source, count, index = [uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2)]
        if index != 1 or not 0 < count <= 256:
            raise ValueError("Unexpected native upload bounds or sequencer index")
        data = bytes(uc.mem_read(source, count))
        report["uploads"].append({"phase": phase, "index": index, "count": count,
                                  "sha256": hashlib.sha256(data).hexdigest(), "bytes_hex": data.hex()})

    cpu.hook_add(UC_HOOK_CODE, upload, begin=0x637a8c98, end=0x637a8c98)

    def write(_uc, _access, address, size, value, _ctx):
        if address >= 0xf0000000:
            report["mmio_writes"].append({"phase": phase, "address": hex(address), "size": size, "value": hex(value)})

    cpu.hook_add(UC_HOOK_MEM_WRITE, write)

    def call(entry, *args):
        cpu.reg_write(UC_ARM_REG_SP, SCRATCH + 0xfff0)
        cpu.reg_write(UC_ARM_REG_LR, STOP | 1)
        for register, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            cpu.reg_write(register, value)
        cpu.emu_start(entry | 1, STOP, count=1000000)
        if cpu.reg_read(UC_ARM_REG_PC) != STOP:
            raise ValueError(f"Native function {entry:x} did not return")
        return cpu.reg_read(UC_ARM_REG_R0)

    with backup.open("rb") as stream:
        bf = BackupFile(stream)
        call(0x637abbe4, SCRATCH, 0)
        if from_mode is not None:
            # The stock imager accessor loads this published object pointer.
            cpu.mem_write(0x6426B7B8, struct.pack("<I", SCRATCH))
        phase = "initializer"
        call(0x637abba4, SCRATCH)
        # Verify the native initializer chose these bindings, rather than copying
        # properties to destinations inferred from their lengths.
        requested = {int(p["id"], 16): int(p["target"], 16)
                     for event in report["host_calls"] for p in event.get("properties", [])}
        assert requested == dict(zip(PROFILE_IDS, PROFILE_VAS)), {hex(k): hex(v) for k, v in requested.items()}
        for key, address in zip(PROFILE_IDS, PROFILE_VAS):
            data = read_property(key)
            assert bytes(cpu.mem_read(address, len(data))) == data
            report["profiles"].append({"id": hex(key), "va": hex(address), "bytes": len(data),
                                       "sha256": hashlib.sha256(data).hexdigest()})
        if from_mode is not None:
            if frame_request is not None:
                # The original imager setup at 0x637ae374 initializes this
                # provider with InitParam before mode and exposure handling.
                phase = "provider-init"
                call(0x63D2B564, word(SCRATCH + 0x284), 0, SCRATCH + 0x134)
            phase = "prior-mode"
            cpu.mem_write(SCRATCH + 0x1000, struct.pack("<II", from_mode, 0))
            if call(0x637acd98, SCRATCH, SCRATCH + 0x1000) != 0:
                raise ValueError("Native initializer rejected the prior mode")
            if call(0x637ad06c, SCRATCH, 0) != 0:
                raise ValueError("Native readout rejected the prior mode")
        phase = "set-mode"
        cpu.mem_write(SCRATCH + 0x1000, struct.pack("<II", mode, 0))
        result = call(0x637acd98, SCRATCH, SCRATCH + 0x1000)
        if result != 0: raise ValueError(f"Native mode rejected: {result}")
        if frame_request is not None:
            phase = "frame-request"
            request = SCRATCH + 0x1100
            cpu.mem_write(request, bytes(frame_request))
            # The still caller supplies the context flag as arg 2 and 1 as
            # arg 3. Use flag 1 in this offline request fixture.
            status = call(0x637ACA24, SCRATCH, request, 1, 1)
            if status != 0:
                raise ValueError(f"Native mode-0x37 frame request returned {status}")
            report["frame_request"] = {"bytes_hex": frame_request.hex(), "flags": [1, 1], "result": status}
        phase = "readout"
        report["readout_result"] = call(0x637ad06c, SCRATCH, 0)
    report["limits"] = [
        "Captured profiles describe USB Senser state" if profile_dir else "Saved Backup profile is not a new current-body capture",
        "Event waits, callbacks, Linux IRQ enable and trace calls are modeled",
        "No power/reset transition, receiver clock/link lock or DMA completion is established",
        ("Frame request bytes are caller-supplied and the still context flag is modeled as 1"
         if frame_request is not None else
         "Constructor timing state is used; per-frame SetImgRd descriptor was not supplied"),
        "Internal mode ID is not bound to a usable live-view geometry",
        "Raw MMIO writes must not be replayed as an initialization recipe",
    ]
    if from_mode is not None:
        report["limits"].append(
            "Mode transition uses RAM-backed ADC reads and suppresses firmware IPC trace records"
        )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path)
    parser.add_argument("backup", type=Path)
    parser.add_argument("--mode", type=lambda s: int(s, 0), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--profile-dir", type=Path)
    parser.add_argument("--from-mode", type=lambda s: int(s, 0),
                        help="replay the prior mode before setting up target readout")
    parser.add_argument("--frame-request-hex", type=bytes.fromhex,
                        help="apply a 32-byte SetImgRd fixture before mode-0x37 readout")
    args = parser.parse_args()
    if args.out.exists(): parser.error("Output already exists; preserve prior evidence")
    result = recover(args.firmware, args.backup, args.mode, args.profile_dir, args.from_mode,
                     frame_request=args.frame_request_hex)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(f"Recovered {len(result['profiles'])} native profile bindings and {len(result['uploads'])} command uploads; physical initialization untested.")
