"""Audit the ZV-E10's selected LCD profile and the generic panel request gates offline."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from unicorn import UC_ARCH_ARM, UC_HOOK_MEM_WRITE, UC_MODE_THUMB, Uc
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP

BASE = 0x635C6000
PROFILE = 0x6455FE88
PROFILE_IDS = 0x645ECAF0
CONFIG = 0x645267FA
DESCRIPTOR = 0x64429B5C
SCRATCH = 0x02000000
RETURN = SCRATCH + 0x100


def audit(repo):
    sys.path.insert(0, str(repo))
    from pmca.backup import BackupFile

    image = (repo / ".local/dumps/av-cam.bin").read_bytes()
    image_hash = hashlib.sha256(image).hexdigest()
    assert image_hash == "bc6cba98c1ce5ef9c7692b9701ed855c25958d285a646ef90dc3fdf398f5c4fa"
    identity = json.loads((repo / "docs/hardware/data/display-current-body.json").read_text())
    assert identity["lcd_profile0"]["selector"] == 0
    ids = struct.unpack_from("<304I", image, PROFILE_IDS - BASE)
    backup_path = repo / ".local/dumps/camera_2025/usr/setting/Backup.bin"
    with backup_path.open("rb") as backup_file:
        backup = BackupFile(backup_file)
        values = [backup.getProperty(key).data for key in ids]
    assert all(len(value) == 1 for value in values)
    profile = b"".join(values)
    profile_hash = hashlib.sha256(profile).hexdigest()
    assert profile_hash == identity["lcd_profile0"]["sha256"]
    assert (profile[0], profile[1], profile[0x18], profile[0x2B], profile[0x2F]) == (0x10, 0, 1, 0, 0x60)

    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    cpu.mem_map(BASE, (len(image) + 0xFFF) & ~0xFFF)
    cpu.mem_write(BASE, image)
    cpu.mem_write(PROFILE, profile)
    cpu.mem_map(SCRATCH, 0x4000)
    writes = []

    def record(_cpu, _access, address, size, value, _data):
        if address >= 0xF0000000:
            writes.append((address, size, value))

    cpu.hook_add(UC_HOOK_MEM_WRITE, record)

    def run(entry, args, stop=RETURN):
        for register, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2), args):
            cpu.reg_write(register, value)
        cpu.reg_write(UC_ARM_REG_SP, SCRATCH + 0x3FF0)
        cpu.reg_write(UC_ARM_REG_LR, RETURN | 1)
        cpu.emu_start(entry | 1, stop, count=2000)
        assert cpu.reg_read(UC_ARM_REG_PC) == stop
        return cpu.reg_read(UC_ARM_REG_R0)

    # Use the stock profile decoder and compare actual body and boundary type bytes.
    cpu.mem_write(CONFIG, bytes(0x80))
    run(0x63AC85A8, (CONFIG, 0x64526B76))
    assert bytes(cpu.mem_read(CONFIG, 2)) == bytes((0x10, 0))
    body_config = bytes(cpu.mem_read(CONFIG, 0x30))

    trials = []
    for entry, queue_wrapper in ((0x63ACE390, 0x63ACBE84), (0x63ACE244, 0x63ACBF3C)):
        for type_byte in (0x10, 0, 1, 12, 13):
            cpu.mem_write(CONFIG, bytes((type_byte,)) + body_config[1:])
            cpu.mem_write(DESCRIPTOR, b"\xA5" * 64)
            reaches_queue = 1 <= type_byte <= 12
            result = run(entry, (CONFIG, 4, SCRATCH + 0x200), queue_wrapper if reaches_queue else RETURN)
            if reaches_queue:
                assert result == 0x740017
                assert cpu.reg_read(UC_ARM_REG_R1) == DESCRIPTOR
                assert cpu.mem_read(DESCRIPTOR, 64) != b"\xA5" * 64
            else:
                assert result == 0
                assert cpu.mem_read(DESCRIPTOR, 64) == b"\xA5" * 64
            trials.append({"entry": hex(entry), "type_byte": hex(type_byte), "reached_queue_wrapper": reaches_queue})

    for device, flag in ((1, 0x64526806), (2, 0x64526B82)):
        for value in (0, 1):
            cpu.mem_write(flag, b"\xFF")
            stop = 0x63C5FE48 if device == 2 else RETURN
            run(0x63ACBD94, (device, value), stop)
            assert bytes(cpu.mem_read(flag, 1)) == bytes((value,))
    assert not writes
    return {
        "reference_sha256": image_hash,
        "profile_sha256": profile_hash,
        "profile_fields": {hex(offset): hex(profile[offset]) for offset in (0, 1, 0x18, 0x2B, 0x2F, 0x111)},
        "stage3_shadow_flag_addresses": ["0x64526806", "0x64526b82"],
        "panel_request_descriptor_va": hex(DESCRIPTOR),
        "panel_request_queue_id": "0x740017",
        "queue_gate_trials": trials,
        "camera_access_performed": False,
        "mmio_writes_in_audit": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not __debug__:
        parser.error("Run without Python optimization to retain instruction assertions")
    report = audit(args.repo.resolve())
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f'{len(report["queue_gate_trials"])} LCD request cases and four flag cases passed')


if __name__ == "__main__":
    main()
