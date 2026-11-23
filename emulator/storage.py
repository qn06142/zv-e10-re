"""Pure-Python VFAT (FAT16) synthesizer and composite eMMC image builder.

Synthesizes missing ZV-E10 VFAT partitions (`nflasha10` for `/etc`+`/tmp`,
`nflasha11` for `/log`, `nflasha9/12/18`, and optional `dmode=0` `nflasha2`)
without external `mkdosfs`/`mtools` dependencies, and packs real + synthesized
partitions into a composite eMMC image with the CXD90045 sector-0 `"8246" "1.00"`
partition table expected by Sony's `/kmod/emmc.ko`.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path, PurePosixPath
import shutil
import struct
import tarfile
from typing import Mapping

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DUMPS_DIR = REPO_ROOT / ".local" / "dumps"
DEFAULT_STORAGE_WORK_DIR = REPO_ROOT / ".local" / "emulator" / "work" / "storage"

SECTOR_SIZE = 512
PARTITION_ALIGN = 65536
PTBL_MAGIC = b"8246"
PTBL_VERSION = b"1.00"
PTBL_PART_TYPE_VFAT_EXT2 = 3
PTBL_FLAG_ACTIVE = 1
TOTAL_EMMC_SLOTS = 18

_VALID_83_CHARS = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!#$%&'()-@^_`{}~"
)


def _align_up(value: int, align: int) -> int:
    return ((value + align - 1) // align) * align


def _choose_fat16_geometry(size_bytes: int, sectors_per_cluster: int | None = None) -> tuple[int, int, int, int]:
    """Return `(total_sectors, spc, sectors_per_fat, cluster_count)` for FAT16."""
    bps = SECTOR_SIZE
    rsvd = 1
    fats = 2
    root_dir_sectors = (512 * 32) // bps
    total_sectors = size_bytes // bps
    if size_bytes % bps != 0 or total_sectors < 4200:
        raise ValueError(f"FAT16 image size must be >= 2,150,400 bytes and 512B-aligned, got {size_bytes}")

    candidates = [sectors_per_cluster] if sectors_per_cluster is not None else [16, 8, 4, 2, 1, 32, 64]
    for spc in candidates:
        spf = 16
        for _ in range(4):
            data_sectors = total_sectors - rsvd - fats * spf - root_dir_sectors
            if data_sectors <= 0:
                break
            clusters = data_sectors // spc
            spf = math.ceil((clusters + 2) * 2 / bps)
        data_sectors = total_sectors - rsvd - fats * spf - root_dir_sectors
        if data_sectors <= 0:
            continue
        clusters = data_sectors // spc
        if 4085 <= clusters <= 65524:
            return total_sectors, spc, spf, clusters

    raise ValueError(
        f"Cannot form valid FAT16 cluster count (4085..65524) for size_bytes={size_bytes}, spc={sectors_per_cluster}"
    )


def _needs_lfn(name: str) -> bool:
    """Return True if basename needs VFAT LFN entries to preserve name/case on Linux."""
    if not name or name in (".", ".."):
        return False
    if name.startswith("."):
        return True
    if name != name.upper():
        return True
    parts = name.split(".")
    if len(parts) > 2:
        return True
    stem = parts[0]
    ext = parts[1] if len(parts) == 2 else ""
    if not stem or len(stem) > 8 or len(ext) > 3:
        return True
    if any(ch not in _VALID_83_CHARS for ch in stem + ext):
        return True
    return False


def _make_83_name(name: str, used: set[bytes]) -> bytes:
    """Create a unique 11-byte uppercase 8.3 directory entry name."""
    if name.startswith("."):
        stem_raw = name.lstrip(".") or "FILE"
        ext_raw = ""
    else:
        dot = name.rfind(".")
        if dot > 0:
            stem_raw, ext_raw = name[:dot], name[dot + 1 :]
        else:
            stem_raw, ext_raw = name, ""

    def _clean(s: str) -> str:
        out = []
        for ch in s.upper():
            if ch in _VALID_83_CHARS:
                out.append(ch)
            elif ch not in (" ", "."):
                out.append("_")
        return "".join(out)

    stem_clean = _clean(stem_raw) or "FILE"
    ext_clean = _clean(ext_raw)[:3]

    if not _needs_lfn(name):
        candidate = (stem_clean[:8].ljust(8) + ext_clean.ljust(3)).encode("ascii")
        if candidate not in used:
            used.add(candidate)
            return candidate

    for idx in range(1, 999999):
        suffix = f"~{idx}"
        prefix = stem_clean[: max(1, 8 - len(suffix))]
        candidate = ((prefix + suffix).ljust(8) + ext_clean.ljust(3)).encode("ascii")
        if candidate not in used:
            used.add(candidate)
            return candidate

    raise RuntimeError(f"Exhausted short 8.3 aliases for {name!r}")


def _lfn_checksum(short_name: bytes) -> int:
    s = 0
    for b in short_name:
        s = (((s & 1) << 7) + (s >> 1) + b) & 0xFF
    return s


def _encode_lfn_entries(long_name: str, short_name: bytes) -> list[bytes]:
    """Encode VFAT LFN 32-byte slots in on-disk order (last chunk first)."""
    chk = _lfn_checksum(short_name)
    code_units = list(struct.unpack(f"<{len(long_name.encode('utf-16-le')) // 2}H", long_name.encode("utf-16-le")))
    code_units.append(0x0000)
    while len(code_units) % 13 != 0:
        code_units.append(0xFFFF)

    num_chunks = len(code_units) // 13
    entries: list[bytes] = []
    for seq in range(num_chunks, 0, -1):
        chunk = code_units[(seq - 1) * 13 : seq * 13]
        ordinal = seq | (0x40 if seq == num_chunks else 0)
        part1 = struct.pack("<5H", *chunk[0:5])
        part2 = struct.pack("<6H", *chunk[5:11])
        part3 = struct.pack("<2H", *chunk[11:13])
        entries.append(
            struct.pack("<B10sBBB12sH4s", ordinal, part1, 0x0F, 0x00, chk, part2, 0, part3)
        )
    return entries


def _pack_83_entry(
    short_name: bytes,
    attr: int,
    start_cluster: int,
    size: int,
) -> bytes:
    # Fixed DOS timestamp: 2025-03-15 03:07:10 (matches stock firmware build date)
    dos_time = (3 << 11) | (7 << 5) | 5
    dos_date = ((2025 - 1980) << 9) | (3 << 5) | 15
    return struct.pack(
        "<11sBBBHHHHHHHI",
        short_name,
        attr,
        0,
        0,
        dos_time,
        dos_date,
        dos_date,
        0,
        dos_time,
        dos_date,
        start_cluster & 0xFFFF,
        size & 0xFFFFFFFF,
    )


class _FatNode:
    def __init__(self, name: str, is_dir: bool, data: bytes = b"") -> None:
        self.name = name
        self.is_dir = is_dir
        self.data = data
        self.children: dict[str, _FatNode] = {}
        self.start_cluster = 0


def build_fat16_image(
    out_path: Path | str,
    size_bytes: int,
    files: Mapping[str, bytes | None],
    *,
    volume_label: str = "ZVE10",
    sectors_per_cluster: int | None = None,
) -> Path:
    """Build a spec-compliant FAT16 disk image in pure Python."""
    total_sectors, spc, spf, max_clusters = _choose_fat16_geometry(size_bytes, sectors_per_cluster)
    bps = SECTOR_SIZE
    rsvd = 1
    fats = 2
    rde = 512
    root_dir_sectors = (rde * 32) // bps
    cluster_size = spc * bps
    fat_offset = rsvd * bps
    root_offset = (rsvd + fats * spf) * bps
    data_offset = root_offset + root_dir_sectors * bps

    root = _FatNode("", is_dir=True)
    for raw_path, content in files.items():
        norm = PurePosixPath(str(raw_path).replace("\\", "/").lstrip("/"))
        parts = [p for p in norm.parts if p not in ("", ".")]
        if not parts:
            continue
        cur = root
        for part in parts[:-1]:
            child = cur.children.get(part)
            if child is None:
                child = _FatNode(part, is_dir=True)
                cur.children[part] = child
            elif not child.is_dir:
                raise ValueError(f"Path conflict in FAT16 tree: {raw_path!r}")
            cur = child

        leaf = parts[-1]
        if content is None:
            if leaf not in cur.children:
                cur.children[leaf] = _FatNode(leaf, is_dir=True)
        else:
            existing = cur.children.get(leaf)
            if existing is not None and existing.is_dir:
                raise ValueError(f"Cannot overwrite directory with file: {raw_path!r}")
            cur.children[leaf] = _FatNode(leaf, is_dir=False, data=bytes(content))

    image = bytearray(size_bytes)
    fat = [0] * (max_clusters + 2)
    fat[0] = 0xFFF8
    fat[1] = 0xFFFF
    next_cluster = 2

    def alloc_chain(payload: bytes) -> int:
        nonlocal next_cluster
        if not payload:
            return 0
        needed = (len(payload) + cluster_size - 1) // cluster_size
        if next_cluster + needed - 1 > max_clusters + 1:
            raise ValueError(
                f"FAT16 image ({size_bytes} bytes) out of clusters allocating {len(payload)} bytes"
            )
        first = next_cluster
        for idx in range(needed):
            clus = next_cluster
            next_cluster += 1
            fat[clus] = clus + 1 if idx + 1 < needed else 0xFFFF
            chunk = payload[idx * cluster_size : (idx + 1) * cluster_size]
            off = data_offset + (clus - 2) * cluster_size
            image[off : off + len(chunk)] = chunk
        return first

    def build_dir_bytes(node: _FatNode, parent_cluster: int) -> bytes:
        used_83: set[bytes] = set()
        raw = bytearray()
        if node is not root:
            raw.extend(_pack_83_entry(b".          ", 0x10, node.start_cluster, 0))
            raw.extend(_pack_83_entry(b"..         ", 0x10, parent_cluster, 0))
        for child_name in sorted(node.children):
            child = node.children[child_name]
            if child.is_dir:
                child_start = next_cluster
                # Reserve first cluster now, write dir chain recursively after knowing cluster
                # Actually allocate child_dir clusters bottom-up only if parent cluster known:
                # since we pass node.start_cluster to child, allocate child's bytes after assigning
                # child's start cluster! For multi-cluster dirs we need contiguous OR pre-known count.
                # Calculate dir size accurately by building its short/lfn entries upfront!
                raise_guard = child_start
                _ = raise_guard
            sfn = _make_83_name(child.name, used_83)
            if _needs_lfn(child.name):
                for lfn_ent in _encode_lfn_entries(child.name, sfn):
                    raw.extend(lfn_ent)
            if child.is_dir:
                # Recurse: first compute how many clusters child dir itself needs
                sub_bytes = populate_subdir(child, node.start_cluster)
                child.start_cluster = alloc_chain(sub_bytes)
                raw.extend(_pack_83_entry(sfn, 0x10, child.start_cluster, 0))
            else:
                file_clus = alloc_chain(child.data)
                raw.extend(_pack_83_entry(sfn, 0x20, file_clus, len(child.data)))
        return bytes(raw)

    def populate_subdir(dir_node: _FatNode, parent_cluster: int) -> bytes:
        nonlocal next_cluster
        # First assign directory's own cluster(s) BEFORE populating "." and children's "..".
        # Calculate total 32B entry count of dir_node so we know its exact cluster span upfront.
        used_83: set[bytes] = set()
        entry_specs: list[tuple[_FatNode, bytes, list[bytes]]] = []
        total_entries = 2  # "." and ".."
        for child_name in sorted(dir_node.children):
            child = dir_node.children[child_name]
            sfn = _make_83_name(child.name, used_83)
            lfns = _encode_lfn_entries(child.name, sfn) if _needs_lfn(child.name) else []
            entry_specs.append((child, sfn, lfns))
            total_entries += len(lfns) + 1

        dir_bytes_len = max(cluster_size, _align_up(total_entries * 32, cluster_size))
        needed_clusters = dir_bytes_len // cluster_size
        if next_cluster + needed_clusters - 1 > max_clusters + 1:
            raise ValueError(f"FAT16 image ({size_bytes} bytes) out of clusters for directory {dir_node.name!r}")

        dir_node.start_cluster = next_cluster
        next_cluster += needed_clusters
        for i in range(needed_clusters):
            clus = dir_node.start_cluster + i
            fat[clus] = clus + 1 if i + 1 < needed_clusters else 0xFFFF

        buf = bytearray(dir_bytes_len)
        pos = 0
        for dot_ent in (
            _pack_83_entry(b".          ", 0x10, dir_node.start_cluster, 0),
            _pack_83_entry(b"..         ", 0x10, parent_cluster, 0),
        ):
            buf[pos : pos + 32] = dot_ent
            pos += 32

        for child, sfn, lfns in entry_specs:
            for lfn_ent in lfns:
                buf[pos : pos + 32] = lfn_ent
                pos += 32
            if child.is_dir:
                populate_subdir(child, dir_node.start_cluster)
                buf[pos : pos + 32] = _pack_83_entry(sfn, 0x10, child.start_cluster, 0)
            else:
                file_clus = alloc_chain(child.data)
                buf[pos : pos + 32] = _pack_83_entry(sfn, 0x20, file_clus, len(child.data))
            pos += 32

        for i in range(needed_clusters):
            clus = dir_node.start_cluster + i
            off = data_offset + (clus - 2) * cluster_size
            image[off : off + cluster_size] = buf[i * cluster_size : (i + 1) * cluster_size]
        return bytes(buf)

    # Populate root directory entries (max 512 slots)
    used_root: set[bytes] = set()
    root_buf = bytearray(rde * 32)
    root_pos = 0
    for child_name in sorted(root.children):
        child = root.children[child_name]
        sfn = _make_83_name(child.name, used_root)
        lfns = _encode_lfn_entries(child.name, sfn) if _needs_lfn(child.name) else []
        needed_bytes = (len(lfns) + 1) * 32
        if root_pos + needed_bytes > len(root_buf):
            raise ValueError("FAT16 root directory entry count exceeded 512")
        for lfn_ent in lfns:
            root_buf[root_pos : root_pos + 32] = lfn_ent
            root_pos += 32
        if child.is_dir:
            populate_subdir(child, 0)
            root_buf[root_pos : root_pos + 32] = _pack_83_entry(sfn, 0x10, child.start_cluster, 0)
        else:
            file_clus = alloc_chain(child.data)
            root_buf[root_pos : root_pos + 32] = _pack_83_entry(sfn, 0x20, file_clus, len(child.data))
        root_pos += 32
    _ = build_dir_bytes  # unused helper guard

    image[root_offset : root_offset + len(root_buf)] = root_buf

    # Write FAT tables (FAT0 and FAT1)
    fat_bytes = struct.pack(f"<{len(fat)}H", *fat)
    fat_padded = fat_bytes.ljust(spf * bps, b"\x00")[: spf * bps]
    for f_idx in range(fats):
        f_off = fat_offset + f_idx * spf * bps
        image[f_off : f_off + len(fat_padded)] = fat_padded

    # Write Boot Sector (sector 0)
    tot16 = total_sectors if total_sectors < 0x10000 else 0
    tot32 = 0 if total_sectors < 0x10000 else total_sectors
    label_bytes = volume_label.upper().encode("ascii", errors="replace")[:11].ljust(11)
    boot = bytearray(bps)
    boot[0:3] = b"\xEB\x3C\x90"
    boot[3:11] = b"PMCA_FAT"
    struct.pack_into("<HBHBHHBHHHII", boot, 11, bps, spc, rsvd, fats, rde, tot16, 0xF8, spf, 32, 64, 0, tot32)
    struct.pack_into("<BBBI11s8s", boot, 36, 0x80, 0x00, 0x29, 0x20250315, label_bytes, b"FAT16   ")
    boot[510:512] = b"\x55\xAA"
    image[0:bps] = boot

    dst = Path(out_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(image)
    return dst


def load_tgz_tree(tgz_path: Path | str, *, strip_prefix: str = "") -> dict[str, bytes | None]:
    """Read regular files & directories from a `.tgz` archive into a `{relpath: bytes | None}` map."""
    tree: dict[str, bytes | None] = {}
    prefix_parts = [p for p in strip_prefix.strip("/").split("/") if p]
    with tarfile.open(tgz_path, "r:gz") as tf:
        for member in tf.getmembers():
            parts = [p for p in PurePosixPath(member.name).parts if p not in ("", ".")]
            if prefix_parts and parts[: len(prefix_parts)] == prefix_parts:
                parts = parts[len(prefix_parts) :]
            if not parts:
                continue
            rel = "/".join(parts)
            if member.isdir():
                tree.setdefault(rel, None)
            elif member.isreg():
                fh = tf.extractfile(member)
                tree[rel] = fh.read() if fh is not None else b""
    return tree


def _locate_dump_image(dumps_dir: Path, filename: str) -> Path:
    for candidate in (dumps_dir / filename, dumps_dir / "card" / filename):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Missing partition image {filename} under {dumps_dir} or {dumps_dir / 'card'}")


@dataclass(frozen=True)
class PartitionSlice:
    index: int
    device_name: str
    mount_point: str
    start_bytes: int
    size_bytes: int
    part_type: int
    flags: int
    source_path: Path | None = None


@dataclass(frozen=True)
class StagedStorage:
    work_dir: Path
    emmc_image: Path
    ptbl_sector0: bytes
    partitions: tuple[PartitionSlice, ...]
    kernel_only: bool
    include_usr: bool


def build_partition_table_sector(partitions: tuple[PartitionSlice, ...]) -> bytes:
    """Serialize Sony sector-0 `"8246" "1.00"` eMMC partition table (512 bytes)."""
    if len(partitions) > 30:
        raise ValueError(f"Sony emmc.ko supports at most 30 partitions, got {len(partitions)}")
    sec = bytearray(SECTOR_SIZE)
    sec[0:4] = PTBL_MAGIC
    sec[4:8] = PTBL_VERSION
    struct.pack_into("<I", sec, 8, len(partitions))
    for i, part in enumerate(partitions):
        if part.start_bytes % SECTOR_SIZE != 0 or part.size_bytes % SECTOR_SIZE != 0:
            raise ValueError(f"Partition {part.device_name} is not 512B aligned")
        if part.start_bytes + part.size_bytes > 0xFFFFFFFF:
            raise ValueError(f"Partition {part.device_name} exceeds 32-bit byte offset")
        struct.pack_into(
            "<IIII",
            sec,
            32 + i * 16,
            part.start_bytes,
            part.size_bytes,
            part.part_type,
            part.flags,
        )
    return bytes(sec)


def stage_storage(
    *,
    dumps_dir: Path | str = DEFAULT_DUMPS_DIR,
    work_dir: Path | str = DEFAULT_STORAGE_WORK_DIR,
    kernel_only: bool = True,
    include_usr: bool = True,
    rebuild: bool = False,
) -> StagedStorage:
    """Synthesize missing VFAT images and assemble a composite eMMC image."""
    dumps = Path(dumps_dir)
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    # 1. /etc + /tmp -> nflasha10 (16 MiB FAT16 from trees/etc.tgz)
    nflasha10 = work / "nflasha10.img"
    if rebuild or not nflasha10.is_file():
        etc_files = load_tgz_tree(dumps / "trees" / "etc.tgz", strip_prefix="etc")
        build_fat16_image(nflasha10, 16 * 1024 * 1024, etc_files, volume_label="ETC_TMP")

    # 2. /log -> nflasha11 (8 MiB clean FAT16 so dosfsck passes without reformatting)
    nflasha11 = work / "nflasha11.img"
    if rebuild or not nflasha11.is_file():
        build_fat16_image(nflasha11, 8 * 1024 * 1024, {}, volume_label="LOG")

    # 3. Auxiliary small VFAT mounts checked by /sbin/init
    aux_images: dict[int, tuple[str, Path]] = {}
    for slot, mount_pt, label in (
        (9, "/usr/upgrade", "UPGRADE"),
        (12, "/cert", "CERT"),
        (18, "/lens", "LENS"),
    ):
        aux_path = work / f"nflasha{slot}.img"
        if rebuild or not aux_path.is_file():
            build_fat16_image(aux_path, 4 * 1024 * 1024 + 512 * 1024, {}, volume_label=label)
        aux_images[slot] = (mount_pt, aux_path)

    # 4. /setting -> nflasha2 (real card dump for normal boot, or +mode/dmode=0 for kernel_only)
    if kernel_only:
        nflasha2 = work / "nflasha2_dmode0.img"
        if rebuild or not nflasha2.is_file():
            setting_files = load_tgz_tree(dumps / "trees" / "setting.tgz", strip_prefix="setting")
            setting_files["mode/dmode"] = b"0\n"
            build_fat16_image(nflasha2, 20 * 1024 * 1024, setting_files, volume_label="SETTING", sectors_per_cluster=8)
    else:
        nflasha2 = work / "nflasha2_normal.img"
        if rebuild or not nflasha2.is_file():
            shutil.copy2(_locate_dump_image(dumps, "nflasha2.img"), nflasha2)

    # 5. Real dumps copied/referenced for active slots
    nflasha3_src = _locate_dump_image(dumps, "nflasha3.img")
    nflasha7_src = _locate_dump_image(dumps, "nflasha7.img")

    if include_usr:
        nflasha15_src = _locate_dump_image(dumps, "nflasha15.img")
    else:
        # Compact empty FAT16 fallback if minimal fast image requested
        nflasha15_src = work / "nflasha15_stub.img"
        if rebuild or not nflasha15_src.is_file():
            build_fat16_image(nflasha15_src, 4 * 1024 * 1024 + 512 * 1024, {"bin": None}, volume_label="USR_STUB")

    active_sources: dict[int, tuple[str, Path]] = {
        2: ("/setting", nflasha2),
        3: ("/system", nflasha3_src),
        7: ("/rootfs", nflasha7_src),
        9: aux_images[9],
        10: ("/etc,/tmp", nflasha10),
        11: ("/log", nflasha11),
        12: aux_images[12],
        15: ("/usr", nflasha15_src),
        18: aux_images[18],
    }

    # Layout partitions into composite disk starting at offset 64 KiB
    cursor = PARTITION_ALIGN
    slices: list[PartitionSlice] = []
    for part_num in range(1, TOTAL_EMMC_SLOTS + 1):
        if part_num in active_sources:
            mount_pt, src_path = active_sources[part_num]
            size = src_path.stat().st_size
            slices.append(
                PartitionSlice(
                    index=part_num - 1,
                    device_name=f"nflasha{part_num}",
                    mount_point=mount_pt,
                    start_bytes=cursor,
                    size_bytes=size,
                    part_type=PTBL_PART_TYPE_VFAT_EXT2,
                    flags=PTBL_FLAG_ACTIVE,
                    source_path=src_path,
                )
            )
            cursor = _align_up(cursor + size, PARTITION_ALIGN)
        else:
            dummy_size = PARTITION_ALIGN
            slices.append(
                PartitionSlice(
                    index=part_num - 1,
                    device_name=f"nflasha{part_num}",
                    mount_point="",
                    start_bytes=cursor,
                    size_bytes=dummy_size,
                    part_type=PTBL_PART_TYPE_VFAT_EXT2,
                    flags=0,
                    source_path=None,
                )
            )
            cursor += dummy_size

    part_tuple = tuple(slices)
    ptbl_sec = build_partition_table_sector(part_tuple)

    tag = f"{'dmode0' if kernel_only else 'normal'}_{'fullusr' if include_usr else 'nousr'}"
    composite_path = work / f"emmc_composite_{tag}.img"
    total_size = _align_up(cursor, PARTITION_ALIGN)

    # Rebuild composite if missing or size/header changed
    needs_write = rebuild or not composite_path.is_file() or composite_path.stat().st_size != total_size
    if not needs_write and composite_path.is_file():
        with composite_path.open("rb") as fh:
            if fh.read(SECTOR_SIZE) != ptbl_sec:
                needs_write = True

    if needs_write:
        tmp_path = work / f".{composite_path.name}.tmp"
        with tmp_path.open("wb") as out_f:
            out_f.truncate(total_size)
            out_f.seek(0)
            out_f.write(ptbl_sec)
            for s in part_tuple:
                if s.source_path is not None and s.flags:
                    out_f.seek(s.start_bytes)
                    with s.source_path.open("rb") as in_f:
                        shutil.copyfileobj(in_f, out_f, length=1024 * 1024)
        tmp_path.replace(composite_path)

    return StagedStorage(
        work_dir=work,
        emmc_image=composite_path,
        ptbl_sector0=ptbl_sec,
        partitions=part_tuple,
        kernel_only=kernel_only,
        include_usr=include_usr,
    )
