#!/usr/bin/env python3
"""Sony ulogio Binary Application Log Decoder.

Decodes binary application logs (e.g. `app-sequential.log`) produced by
Sony's ulogio subsystem (`osal_ulogio.ko`, `ulogio.elf`, `libosal_ulogio.so`).

Format Specification:
- Record framing: Contiguous stream, no container header, no alignment padding.
- Record header (16 bytes, little-endian):
    - payload_len (uint32, bytes 0..3)
    - subsys_id   (uint16, bytes 4..5)
    - area_id     (uint16, bytes 6..7)
    - timestamp_us(uint64, bytes 8..15) monotonic uptime in microseconds
- Payload:
    - payload_len bytes immediately following the 16-byte header.
    - Total record size on disk: 16 + payload_len.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import struct
import sys
from dataclasses import asdict, dataclass, field
from typing import BinaryIO, Dict, Generator, Iterator, List, Optional, Set, Tuple, Union

HEADER_FORMAT = "<IHHQ"
HEADER_SIZE = 16
DEFAULT_MAX_PAYLOAD = 1024 * 1024  # 1 MB maximum reasonable payload

# Known Sony Subsystem IDs
KNOWN_SUBSYSTEMS: Dict[int, str] = {
    0x0083: "APP",
    131: "APP",
}

# Known Subsystem 0x83 Area / Component IDs
KNOWN_AREAS: Dict[int, str] = {
    0x01: "DISPATCH",
    0x02: "EVENT_PARAM",
    0x03: "STATE_WORD",
    0x04: "STREAM_STATE",
    0x05: "ERROR_GENERAL",
    0x06: "ERROR_SYSTEM",
    0x07: "CTRL_WORD",
    0x08: "DEV_TELEMETRY",
    0x09: "SYNC_EVENT",
    0x0a: "MW_TRANSACTION",
    0x0b: "TRACE_WORD",
    0x0c: "PERF_MARKER",
    0x0e: "SYNC_MARKER",
}


def format_timestamp(us: int) -> str:
    """Format monotonic microsecond integer into [sssss.uuuuuu] string.

    Matches Sony ulogio_print snprintf("[%05u.%06u] ", sec, usec).
    """
    sec = us // 1_000_000
    usec = us % 1_000_000
    return f"[{sec:05d}.{usec:06d}]"


def extract_printable_strings(data: bytes, min_len: int = 3) -> List[str]:
    """Extract printable ASCII substrings of at least min_len characters."""
    matches = re.findall(rb"[a-zA-Z0-9_\-\[\]\.\/:= ]{" + str(min_len).encode() + rb",}", data)
    return [m.decode("ascii", errors="replace").strip() for m in matches if m.strip()]


@dataclass
class LogRecord:
    """Parsed single log record representation."""

    index: int
    offset: int
    payload_len: int
    total_len: int
    subsys_id: int
    subsys_name: str
    area_id: int
    area_name: str
    timestamp_us: int
    timestamp_s: float
    timestamp_str: str
    payload_hex: str
    parsed: Dict[str, Union[int, str, float, List[int], List[str], Dict[str, int]]] = field(
        default_factory=dict
    )
    message: str = ""
    is_corrupted: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        """Convert record to a JSON-serializable dictionary."""
        d = asdict(self)
        return d

    def format_line(self, verbose: bool = False) -> str:
        """Format record as a single human-readable log line."""
        subsys_str = self.subsys_name
        area_str = self.area_name
        base = (
            f"{self.timestamp_str} "
            f"rec={self.index:<6d} "
            f"off=0x{self.offset:08x} "
            f"[{subsys_str}.{area_str}] "
            f"len={self.payload_len:<2d}: "
            f"{self.message}"
        )
        if verbose and self.payload_hex:
            base += f"\n  raw_hex={self.payload_hex}"
        return base


@dataclass
class UnparsedBlock:
    """Represents an unparsed, skipped, or corrupted chunk of bytes."""

    offset: int
    length: int
    reason: str
    data_hex: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)

    def format_line(self) -> str:
        return f"[CORRUPT/UNPARSED] off=0x{self.offset:08x} len={self.length}: {self.reason} (hex={self.data_hex})"


@dataclass
class DecodeStatistics:
    """Summary statistics of decoding run."""

    total_bytes: int = 0
    total_records: int = 0
    parsed_bytes: int = 0
    unparsed_bytes: int = 0
    corrupted_records: int = 0
    subsystem_counts: Dict[int, int] = field(default_factory=dict)
    area_counts: Dict[int, int] = field(default_factory=dict)
    min_timestamp_us: Optional[int] = None
    max_timestamp_us: Optional[int] = None
    error_count: int = 0

    @property
    def timespan_seconds(self) -> float:
        if self.min_timestamp_us is not None and self.max_timestamp_us is not None:
            return (self.max_timestamp_us - self.min_timestamp_us) / 1_000_000.0
        return 0.0

    def update_record(self, record: LogRecord) -> None:
        self.total_records += 1
        self.parsed_bytes += record.total_len
        self.subsystem_counts[record.subsys_id] = (
            self.subsystem_counts.get(record.subsys_id, 0) + 1
        )
        self.area_counts[record.area_id] = self.area_counts.get(record.area_id, 0) + 1

        if self.min_timestamp_us is None or record.timestamp_us < self.min_timestamp_us:
            self.min_timestamp_us = record.timestamp_us
        if self.max_timestamp_us is None or record.timestamp_us > self.max_timestamp_us:
            self.max_timestamp_us = record.timestamp_us

        if record.is_corrupted:
            self.corrupted_records += 1

        if record.area_id in (0x05, 0x06) or "ERROR" in record.message:
            self.error_count += 1

    def update_unparsed(self, unparsed: UnparsedBlock) -> None:
        self.unparsed_bytes += unparsed.length
        self.corrupted_records += 1

    def summary_string(self) -> str:
        """Produce a formatted multi-line summary of decoding results."""
        min_s = (self.min_timestamp_us / 1_000_000.0) if self.min_timestamp_us else 0.0
        max_s = (self.max_timestamp_us / 1_000_000.0) if self.max_timestamp_us else 0.0
        lines = [
            "============================================================",
            "             SONY ULOGIO LOG DECODE SUMMARY                ",
            "============================================================",
            f"Total File Size   : {self.total_bytes:,} bytes",
            f"Parsed Bytes      : {self.parsed_bytes:,} bytes ({self.parsed_bytes/max(self.total_bytes,1)*100:.2f}%)",
            f"Unparsed/Slack    : {self.unparsed_bytes:,} bytes",
            f"Total Records     : {self.total_records:,}",
            f"Corrupted Records : {self.corrupted_records}",
            f"Error Events Found: {self.error_count}",
            f"Timestamp Range   : {format_timestamp(self.min_timestamp_us or 0)} to {format_timestamp(self.max_timestamp_us or 0)}",
            f"Capture Duration  : {self.timespan_seconds:.3f} seconds ({self.timespan_seconds/60:.2f} minutes)",
            "------------------------------------------------------------",
            "Subsystems:",
        ]
        for sid, cnt in sorted(self.subsystem_counts.items()):
            sname = KNOWN_SUBSYSTEMS.get(sid, f"SUB_0x{sid:04x}")
            lines.append(f"  - 0x{sid:04x} ({sid:>3d}) [{sname:<12s}]: {cnt:,} records")

        lines.append("------------------------------------------------------------")
        lines.append("Area Distribution:")
        for aid, cnt in sorted(self.area_counts.items()):
            aname = KNOWN_AREAS.get(aid, f"AREA_0x{aid:02x}")
            lines.append(f"  - 0x{aid:02x} ({aid:>2d}) [{aname:<14s}]: {cnt:>6,} records")
        lines.append("============================================================")
        return "\n".join(lines)


class PayloadParser:
    """Specialized parsing for Sony Subsystem 0x83 area payload layouts."""

    @staticmethod
    def parse(area_id: int, payload: bytes) -> Tuple[Dict[str, object], str]:
        """Parse payload bytes for a given area ID.

        Returns:
            Tuple of (parsed_dictionary, formatted_message_string).
        """
        plen = len(payload)
        if plen == 0:
            return {}, "<empty>"

        if area_id == 0x01 and plen == 14:
            # Area 1 (14 bytes): Dispatch Action Event
            arg0, arg1, arg2, event_id = struct.unpack("<IIIH", payload)
            comp = (event_id >> 8) & 0xFF
            code = event_id & 0xFF
            d = {
                "arg0": arg0,
                "arg1": arg1,
                "arg2": arg2,
                "event_id": event_id,
                "event_comp": comp,
                "event_code": code,
            }
            msg = f"arg0=0x{arg0:08x} arg1=0x{arg1:08x} arg2=0x{arg2:08x} evt=0x{event_id:04x}(comp={comp},code={code})"
            return d, msg

        elif area_id == 0x02 and plen == 7:
            # Area 2 (7 bytes): Event parameter / command
            cmd, tag, b0, b1, b2 = struct.unpack("<HHBBB", payload)
            d = {"cmd": cmd, "tag": tag, "b0": b0, "b1": b1, "b2": b2}
            msg = f"cmd=0x{cmd:04x} tag=0x{tag:04x} bytes=({b0}, {b1}, {b2})"
            return d, msg

        elif area_id == 0x03 and plen == 12:
            # Area 3 (12 bytes): State words
            w0, w1, w2 = struct.unpack("<III", payload)
            d = {"w0": w0, "w1": w1, "w2": w2}
            msg = f"w0=0x{w0:08x} w1=0x{w1:08x} w2=0x{w2:08x}"
            return d, msg

        elif area_id == 0x04 and plen == 18:
            # Area 4 (18 bytes): Stream state & streaming worker telemetry
            w16 = struct.unpack("<9H", payload)
            w16_hex = [f"0x{w:04x}" for w in w16]
            d = {"words16": list(w16)}
            msg = f"w16=[{', '.join(w16_hex)}]"
            return d, msg

        elif area_id in (0x05, 0x06) and plen == 20:
            # Area 5 / 6 (20 bytes): General / System Error (DataflowInfraLog)
            event_id, arg0, arg1, arg2, status_code = struct.unpack("<IIIIi", payload)
            d = {
                "event_id": event_id,
                "arg0": arg0,
                "arg1": arg1,
                "arg2": arg2,
                "status_code": status_code,
            }
            msg = (
                f"event=0x{event_id:08x} arg0=0x{arg0:08x} arg1=0x{arg1:08x} "
                f"arg2=0x{arg2:08x} status={status_code}"
            )
            return d, msg

        elif area_id == 0x07 and plen == 6:
            # Area 7 (6 bytes): Control words
            w0, w1, w2 = struct.unpack("<HHH", payload)
            d = {"w0": w0, "w1": w1, "w2": w2}
            msg = f"w0=0x{w0:04x} w1=0x{w1:04x} w2=0x{w2:04x}"
            return d, msg

        elif area_id == 0x08 and plen == 21:
            # Area 8 (21 bytes): Device telemetry
            w0, w1, w2, w3, w4, tail = struct.unpack("<IIIIIB", payload)
            d = {"words": [w0, w1, w2, w3, w4], "tail": tail}
            msg = f"words=[0x{w0:08x}, 0x{w1:08x}, 0x{w2:08x}, 0x{w3:08x}, 0x{w4:08x}] tail=0x{tail:02x}"
            return d, msg

        elif area_id == 0x09 and plen == 16:
            # Area 9 (16 bytes): Sync Event
            w0, w1, w2, w3 = struct.unpack("<IIII", payload)
            d = {"w0": w0, "w1": w1, "w2": w2, "w3": w3}
            msg = f"w0=0x{w0:08x} w1=0x{w1:08x} w2=0x{w2:08x} w3=0x{w3:08x}"
            return d, msg

        elif area_id == 0x0a and plen == 28:
            # Area 10 (28 bytes): Middleware State & Transaction
            # Layout 1: [8B hdr] + [20B ASCII string null-terminated]
            # Layout 2: [8B hdr] + [12B args] + [8B ASCII tag string null-terminated]
            hdr0, hdr1 = struct.unpack("<II", payload[:8])
            rem20 = payload[8:]
            tag8 = payload[20:]
            p0, p1, p2 = struct.unpack("<III", payload[8:20])

            s20_raw = rem20.split(b"\x00")[0]
            s8_raw = tag8.split(b"\x00")[0]

            is_s20 = len(s20_raw) >= 3 and all(32 <= c <= 126 for c in s20_raw)
            is_s8 = len(s8_raw) >= 2 and all(32 <= c <= 126 for c in s8_raw)

            d: Dict[str, object] = {"hdr0": hdr0, "hdr1": hdr1}

            if is_s20 and len(s20_raw) > 8:
                # Clearly a long string spanning past the tag field (Layout 1)
                text = s20_raw.decode("ascii", errors="replace")
                d["text"] = text
                msg = f"hdr=(0x{hdr0:08x}, 0x{hdr1:08x}) text='{text}'"
            elif is_s8:
                # 8-byte tag string at the end of the structure (Layout 2)
                tag = s8_raw.decode("ascii", errors="replace")
                d["args"] = [p0, p1, p2]
                d["tag"] = tag
                msg = (
                    f"hdr=(0x{hdr0:08x}, 0x{hdr1:08x}) "
                    f"args=(0x{p0:08x}, 0x{p1:08x}, 0x{p2:08x}) tag='{tag}'"
                )
            elif is_s20:
                # Short string starting at byte 8
                text = s20_raw.decode("ascii", errors="replace")
                d["text"] = text
                msg = f"hdr=(0x{hdr0:08x}, 0x{hdr1:08x}) text='{text}'"
            else:
                d["args"] = [p0, p1, p2]
                w_tail = struct.unpack("<II", tag8)
                d["tail_words"] = list(w_tail)
                msg = (
                    f"hdr=(0x{hdr0:08x}, 0x{hdr1:08x}) "
                    f"args=(0x{p0:08x}, 0x{p1:08x}, 0x{p2:08x}) "
                    f"tail=(0x{w_tail[0]:08x}, 0x{w_tail[1]:08x})"
                )
            return d, msg

        elif area_id == 0x0b and plen == 12:
            # Area 11 (12 bytes): Trace words
            w0, w1, w2 = struct.unpack("<III", payload)
            d = {"w0": w0, "w1": w1, "w2": w2}
            msg = f"w0=0x{w0:08x} w1=0x{w1:08x} w2=0x{w2:08x}"
            return d, msg

        elif area_id == 0x0c and plen == 28:
            # Area 12 (28 bytes): Performance Marker
            strings = extract_printable_strings(payload, min_len=3)
            w32 = struct.unpack("<7I", payload)
            d = {"words": list(w32), "strings": strings}
            if strings:
                msg = f"strings={strings} words=[{', '.join(f'0x{w:08x}' for w in w32[:3])}...]"
            else:
                msg = f"words=[{', '.join(f'0x{w:08x}' for w in w32)}]"
            return d, msg

        elif area_id == 0x0e and plen == 8:
            # Area 14 (8 bytes): Telemetry / Sync marker words
            w0, w1 = struct.unpack("<II", payload)
            d = {"w0": w0, "w1": w1}
            msg = f"w0=0x{w0:08x} w1=0x{w1:08x}"
            return d, msg

        # Generic / Fallback Payload Decoding
        strings = extract_printable_strings(payload, min_len=3)
        d = {"strings": strings}
        if plen % 4 == 0:
            words = struct.unpack(f"<{plen // 4}I", payload)
            d["words"] = list(words)
            if strings:
                msg = f"strings={strings} words=[{', '.join(f'0x{w:08x}' for w in words)}]"
            else:
                msg = f"words=[{', '.join(f'0x{w:08x}' for w in words)}]"
        elif strings:
            msg = f"strings={strings} hex={payload.hex()}"
        else:
            msg = f"hex={payload.hex()}"
        return d, msg


class LogDecoder:
    """Sony ulogio binary log decoder."""

    def __init__(
        self,
        max_payload_len: int = DEFAULT_MAX_PAYLOAD,
        strict: bool = False,
        known_subsystems: Optional[Dict[int, str]] = None,
        known_areas: Optional[Dict[int, str]] = None,
    ) -> None:
        self.max_payload_len = max_payload_len
        self.strict = strict
        self.known_subsystems = (
            known_subsystems if known_subsystems is not None else KNOWN_SUBSYSTEMS
        )
        self.known_areas = (
            known_areas if known_areas is not None else KNOWN_AREAS
        )

    def decode_buffer(
        self,
        data: bytes,
        start_offset: int = 0,
        max_records: Optional[int] = None,
    ) -> Generator[Union[LogRecord, UnparsedBlock], None, DecodeStatistics]:
        """Decode records from a byte buffer generator."""
        stats = DecodeStatistics(total_bytes=len(data))
        off = start_offset
        rec_idx = 0
        total_len = len(data)

        while off < total_len:
            if max_records is not None and rec_idx >= max_records:
                break

            # Check if at least 16 bytes available for header
            if off + HEADER_SIZE > total_len:
                remaining = total_len - off
                unparsed = UnparsedBlock(
                    offset=off,
                    length=remaining,
                    reason="Truncated header at end of file",
                    data_hex=data[off:].hex(),
                )
                stats.update_unparsed(unparsed)
                yield unparsed
                break

            # Parse 16-byte header
            payload_len, subsys_id, area_id, timestamp_us = struct.unpack_from(
                HEADER_FORMAT, data, off
            )

            # Check payload bounds
            record_total = HEADER_SIZE + payload_len
            if (
                payload_len > self.max_payload_len
                or off + record_total > total_len
            ):
                reason = (
                    f"Invalid payload length {payload_len} (exceeds max {self.max_payload_len})"
                    if payload_len > self.max_payload_len
                    else f"Truncated payload: expected {payload_len} bytes, got {total_len - off - HEADER_SIZE}"
                )
                if self.strict:
                    raise ValueError(f"Corruption at 0x{off:08x}: {reason}")

                # Resilient error recovery:
                # In resilient mode, search forward for next valid header
                skip_len = self._find_next_sync(data, off + 1, total_len)
                unparsed_data = data[off : off + skip_len]
                unparsed = UnparsedBlock(
                    offset=off,
                    length=skip_len,
                    reason=reason,
                    data_hex=unparsed_data.hex(),
                )
                stats.update_unparsed(unparsed)
                yield unparsed
                off += skip_len
                continue

            # Extract payload
            payload = data[off + HEADER_SIZE : off + record_total]
            parsed_dict, msg = PayloadParser.parse(area_id, payload)

            subsys_name = self.known_subsystems.get(
                subsys_id, f"SUB_0x{subsys_id:04x}"
            )
            area_name = self.known_areas.get(area_id, f"AREA_0x{area_id:02x}")
            ts_str = format_timestamp(timestamp_us)
            ts_s = timestamp_us / 1_000_000.0

            rec = LogRecord(
                index=rec_idx,
                offset=off,
                payload_len=payload_len,
                total_len=record_total,
                subsys_id=subsys_id,
                subsys_name=subsys_name,
                area_id=area_id,
                area_name=area_name,
                timestamp_us=timestamp_us,
                timestamp_s=ts_s,
                timestamp_str=ts_str,
                payload_hex=payload.hex(),
                parsed=parsed_dict,
                message=msg,
                is_corrupted=False,
            )

            stats.update_record(rec)
            yield rec

            rec_idx += 1
            off += record_total

        return stats

    def decode_file(
        self,
        filepath: str,
        start_offset: int = 0,
        max_records: Optional[int] = None,
    ) -> Generator[Union[LogRecord, UnparsedBlock], None, DecodeStatistics]:
        """Decode records from a file path."""
        with open(filepath, "rb") as f:
            data = f.read()
        return self.decode_buffer(
            data, start_offset=start_offset, max_records=max_records
        )

    def _find_next_sync(self, data: bytes, start_pos: int, total_len: int) -> int:
        """Scan forward to find the next valid record header.

        Returns the number of bytes to skip from start_pos - 1.
        """
        pos = start_pos
        while pos + HEADER_SIZE <= total_len:
            plen, sid, aid, _ = struct.unpack_from(HEADER_FORMAT, data, pos)
            # Check if sid is known or aid is reasonable, and plen is within reasonable bounds
            if (
                sid in self.known_subsystems or sid in (0x0083, 131)
            ) and aid in self.known_areas and plen <= 1024:
                # Plausible header candidate
                if pos + HEADER_SIZE + plen <= total_len:
                    return pos - (start_pos - 1)
            pos += 1
        # No sync found; skip entire remainder
        return total_len - (start_pos - 1)


class LogFilter:
    """Filters records based on CLI criteria."""

    def __init__(
        self,
        subsystems: Optional[Set[int]] = None,
        areas: Optional[Set[int]] = None,
        start_time_s: Optional[float] = None,
        end_time_s: Optional[float] = None,
        grep_pattern: Optional[re.Pattern] = None,
    ) -> None:
        self.subsystems = subsystems
        self.areas = areas
        self.start_time_s = start_time_s
        self.end_time_s = end_time_s
        self.grep_pattern = grep_pattern

    def matches(self, item: Union[LogRecord, UnparsedBlock]) -> bool:
        if isinstance(item, UnparsedBlock):
            return True

        if self.subsystems is not None and item.subsys_id not in self.subsystems:
            return False

        if self.areas is not None and item.area_id not in self.areas:
            return False

        if self.start_time_s is not None and item.timestamp_s < self.start_time_s:
            return False

        if self.end_time_s is not None and item.timestamp_s > self.end_time_s:
            return False

        if self.grep_pattern is not None:
            # Search in message, payload hex, and parsed string fields
            search_text = f"{item.message} {item.payload_hex} {item.area_name} {item.subsys_name}"
            if not self.grep_pattern.search(search_text):
                return False

        return True


def parse_subsystem_filter(val: str) -> Set[int]:
    """Parse comma-separated subsystem specifiers (e.g. '131,0x83,APP')."""
    res = set()
    for token in val.split(","):
        token = token.strip()
        if not token:
            continue
        if token.upper() == "APP":
            res.add(0x0083)
        elif token.startswith("0x") or token.startswith("0X"):
            res.add(int(token, 16))
        else:
            res.add(int(token))
    return res


def parse_area_filter(val: str) -> Set[int]:
    """Parse comma-separated area specifiers (e.g. '1,4,10,0x0a')."""
    res = set()
    # Invert KNOWN_AREAS
    name_to_id = {v.upper(): k for k, v in KNOWN_AREAS.items()}
    for token in val.split(","):
        token = token.strip()
        if not token:
            continue
        token_upper = token.upper()
        if token_upper in name_to_id:
            res.add(name_to_id[token_upper])
        elif token.startswith("0x") or token.startswith("0X"):
            res.add(int(token, 16))
        else:
            res.add(int(token))
    return res


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="decode_app_log.py",
        description="Decode Sony ulogio binary application logs (e.g. app-sequential.log).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        type=str,
        help="Path to binary log file (e.g. app-sequential.log).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output destination file path (default: stdout).",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["text", "json", "jsonl", "csv", "summary"],
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "-s",
        "--subsystem",
        type=str,
        default=None,
        help="Filter by subsystem ID(s) or name (e.g. '131', '0x83', 'APP').",
    )
    parser.add_argument(
        "-a",
        "--area",
        type=str,
        default=None,
        help="Filter by area ID(s) or name (e.g. '10', '0x0a', 'MW_TRANSACTION').",
    )
    parser.add_argument(
        "--start",
        type=float,
        default=None,
        help="Filter records with timestamp >= start time in seconds.",
    )
    parser.add_argument(
        "--end",
        type=float,
        default=None,
        help="Filter records with timestamp <= end time in seconds.",
    )
    parser.add_argument(
        "-g",
        "--grep",
        type=str,
        default=None,
        help="Search/grep regex pattern in message text or payload.",
    )
    parser.add_argument(
        "-n",
        "--max-records",
        type=int,
        default=None,
        help="Limit maximum number of records processed.",
    )
    parser.add_argument(
        "--seek",
        type=int,
        default=0,
        help="Start decoding from specific byte offset in file (default: 0).",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print summary statistics after decoding.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Raise error on corrupted records instead of resiliently logging.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Include raw payload hex in text output.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if not os.path.isfile(args.input):
        sys.stderr.write(f"Error: input file '{args.input}' not found.\n")
        return 1

    subsystems = parse_subsystem_filter(args.subsystem) if args.subsystem else None
    areas = parse_area_filter(args.area) if args.area else None
    grep_pat = re.compile(args.grep, re.IGNORECASE) if args.grep else None

    log_filter = LogFilter(
        subsystems=subsystems,
        areas=areas,
        start_time_s=args.start,
        end_time_s=args.end,
        grep_pattern=grep_pat,
    )

    decoder = LogDecoder(strict=args.strict)

    # Open output stream
    out_file: io.TextIOWrapper | io.StringIO
    if args.output:
        out_f = open(args.output, "w", encoding="utf-8")
        out_close = True
    else:
        out_f = sys.stdout
        out_close = False

    try:
        gen = decoder.decode_file(
            args.input,
            start_offset=args.seek,
            max_records=None,
        )

        matched_records = 0
        json_records = []
        csv_writer = None

        if args.format == "csv":
            csv_writer = csv.writer(out_f)
            csv_writer.writerow(
                [
                    "index",
                    "offset",
                    "timestamp_us",
                    "timestamp_s",
                    "subsys_id",
                    "subsys_name",
                    "area_id",
                    "area_name",
                    "payload_len",
                    "message",
                    "payload_hex",
                ]
            )

        try:
            while True:
                item = next(gen)
                if not log_filter.matches(item):
                    continue

                matched_records += 1

                if args.format == "text":
                    out_f.write(item.format_line(verbose=args.verbose) + "\n")
                elif args.format == "jsonl":
                    out_f.write(json.dumps(item.to_dict()) + "\n")
                elif args.format == "json":
                    json_records.append(item.to_dict())
                elif args.format == "csv" and csv_writer:
                    if isinstance(item, LogRecord):
                        csv_writer.writerow(
                            [
                                item.index,
                                f"0x{item.offset:08x}",
                                item.timestamp_us,
                                f"{item.timestamp_s:.6f}",
                                item.subsys_id,
                                item.subsys_name,
                                item.area_id,
                                item.area_name,
                                item.payload_len,
                                item.message,
                                item.payload_hex,
                            ]
                        )
                    elif isinstance(item, UnparsedBlock):
                        csv_writer.writerow(
                            [
                                -1,
                                f"0x{item.offset:08x}",
                                0,
                                "0.0",
                                -1,
                                "UNPARSED",
                                -1,
                                "UNPARSED",
                                item.length,
                                item.reason,
                                item.data_hex,
                            ]
                        )

                if args.max_records is not None and matched_records >= args.max_records:
                    break

        except StopIteration as stop:
            stats = stop.value

        if args.format == "json":
            out_f.write(json.dumps(json_records, indent=2) + "\n")

        if args.format == "summary" or args.summary:
            summary_txt = stats.summary_string()
            if args.format == "summary":
                out_f.write(summary_txt + "\n")
            else:
                sys.stderr.write(summary_txt + "\n")

    finally:
        if out_close:
            out_f.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
