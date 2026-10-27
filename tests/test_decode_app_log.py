"""Unit tests for Sony ulogio binary application log decoder."""

import json
import os
import struct
import subprocess
import sys
import tempfile
from typing import List

import pytest

from research.log_decoder.decode_app_log import (
    DEFAULT_MAX_PAYLOAD,
    HEADER_FORMAT,
    HEADER_SIZE,
    DecodeStatistics,
    LogDecoder,
    LogFilter,
    LogRecord,
    PayloadParser,
    UnparsedBlock,
    format_timestamp,
    parse_area_filter,
    parse_subsystem_filter,
)

SAMPLE_LOG_PATH = (
    r"C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\usb-debug-20261024-01\camera\app-sequential.log"
)


def make_record(
    payload_len: int,
    subsys_id: int,
    area_id: int,
    timestamp_us: int,
    payload: bytes = b"",
) -> bytes:
    """Helper to synthesize a 16-byte header + payload."""
    hdr = struct.pack(HEADER_FORMAT, payload_len, subsys_id, area_id, timestamp_us)
    return hdr + payload


# ============================================================================
# 1. Timestamp formatting tests
# ============================================================================


def test_format_timestamp() -> None:
    assert format_timestamp(0) == "[00000.000000]"
    assert format_timestamp(1_000_000) == "[00001.000000]"
    assert format_timestamp(1_234_567) == "[00001.234567]"
    assert format_timestamp(5048062345) == "[05048.062345]"
    assert format_timestamp(2661115578) == "[02661.115578]"


# ============================================================================
# 2. Filter parsing tests
# ============================================================================


def test_parse_filters() -> None:
    subs = parse_subsystem_filter("131, 0x83, APP")
    assert subs == {131, 0x0083}

    areas = parse_area_filter("1, 0x0a, MW_TRANSACTION, PERF_MARKER")
    assert areas == {1, 10, 12}


# ============================================================================
# 3. Header & Record Property Tests
# ============================================================================


def test_decode_single_record() -> None:
    decoder = LogDecoder()
    payload = b"test_payload_123"
    rec_bytes = make_record(
        payload_len=len(payload),
        subsys_id=0x0083,
        area_id=0x04,
        timestamp_us=5048062345,
        payload=payload,
    )

    items = list(decoder.decode_buffer(rec_bytes))
    assert len(items) == 1
    rec = items[0]
    assert isinstance(rec, LogRecord)
    assert rec.index == 0
    assert rec.offset == 0
    assert rec.payload_len == len(payload)
    assert rec.total_len == 16 + len(payload)
    assert rec.subsys_id == 0x0083
    assert rec.subsys_name == "APP"
    assert rec.area_id == 0x04
    assert rec.area_name == "STREAM_STATE"
    assert rec.timestamp_us == 5048062345
    assert rec.timestamp_s == pytest.approx(5048.062345, rel=1e-6)
    assert rec.timestamp_str == "[05048.062345]"
    assert rec.payload_hex == payload.hex()
    assert rec.is_corrupted is False
    assert rec.error is None

    # Test to_dict serialization
    d = rec.to_dict()
    assert d["index"] == 0
    assert d["subsys_name"] == "APP"
    assert json.dumps(d)  # JSON-serializable


# ============================================================================
# 4. Area Payload Decoder Tests
# ============================================================================


def test_payload_parser_area01_dispatch() -> None:
    # 14 bytes: uint32 arg0, uint32 arg1, uint32 arg2, uint16 event_id
    payload = struct.pack("<IIIH", 0x1234, 0x5678, 0x9abc, 0x0b21)
    d, msg = PayloadParser.parse(0x01, payload)
    assert d["arg0"] == 0x1234
    assert d["arg1"] == 0x5678
    assert d["arg2"] == 0x9abc
    assert d["event_id"] == 0x0b21
    assert d["event_code"] == 0x21
    assert d["event_comp"] == 0x0b
    assert "evt=0x0b21" in msg


def test_payload_parser_area02_param() -> None:
    # 7 bytes: uint16 cmd, uint16 tag, 3 bytes
    payload = struct.pack("<HHBBB", 0x000c, 0x00c3, 10, 20, 30)
    d, msg = PayloadParser.parse(0x02, payload)
    assert d["cmd"] == 0x000c
    assert d["tag"] == 0x00c3
    assert d["b0"] == 10
    assert "cmd=0x000c" in msg


def test_payload_parser_area03_state() -> None:
    # 12 bytes: 3x uint32
    payload = struct.pack("<III", 1, 2, 3)
    d, msg = PayloadParser.parse(0x03, payload)
    assert d["w0"] == 1
    assert d["w1"] == 2
    assert d["w2"] == 3


def test_payload_parser_area04_stream_state() -> None:
    # 18 bytes: 9 uint16
    payload = struct.pack("<9H", 1, 2, 3, 4, 5, 6, 7, 8, 9)
    d, msg = PayloadParser.parse(0x04, payload)
    assert d["words16"] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert "w16=" in msg


def test_payload_parser_area05_06_error() -> None:
    # 20 bytes: event_id, arg0, arg1, arg2, status_code
    payload = struct.pack("<IIIIi", 0x00060001, 0x10, 0x20, 0x30, -1024)
    d, msg = PayloadParser.parse(0x05, payload)
    assert d["event_id"] == 0x00060001
    assert d["status_code"] == -1024
    assert "status=-1024" in msg

    d6, msg6 = PayloadParser.parse(0x06, payload)
    assert d6["status_code"] == -1024


def test_payload_parser_area0a_string_and_tag() -> None:
    # Area 10 Layout 1: 20-byte string
    hdr = struct.pack("<II", 0x01020304, 0x05060708)
    text = b"camera Model loaded\x00"
    payload1 = hdr + text
    d1, msg1 = PayloadParser.parse(0x0a, payload1)
    assert d1["text"] == "camera Model loaded"
    assert "camera Model loaded" in msg1

    # Area 10 Layout 2: args + 8-byte tag string
    args = struct.pack("<III", 0x10, 0x20, 0x30)
    tag = b"ERROR\x00\x00\x00"
    payload2 = hdr + args + tag
    d2, msg2 = PayloadParser.parse(0x0a, payload2)
    assert d2["tag"] == "ERROR"
    assert "tag='ERROR'" in msg2


def test_payload_parser_area0e_telemetry() -> None:
    # 8 bytes: 2x uint32
    payload = struct.pack("<II", 0x12345678, 0x9abcdef0)
    d, msg = PayloadParser.parse(0x0e, payload)
    assert d["w0"] == 0x12345678
    assert d["w1"] == 0x9abcdef0


def test_payload_parser_empty_and_generic() -> None:
    d, msg = PayloadParser.parse(0x03, b"")
    assert d == {}
    assert msg == "<empty>"

    # Generic arbitrary payload
    generic_payload = b"ABC1234XYZ"
    d_gen, msg_gen = PayloadParser.parse(0x99, generic_payload)
    assert "strings" in d_gen


# ============================================================================
# 5. Boundary Condition & Error Recovery Tests
# ============================================================================


def test_empty_buffer() -> None:
    decoder = LogDecoder()
    items = list(decoder.decode_buffer(b""))
    assert len(items) == 0


def test_truncated_header() -> None:
    decoder = LogDecoder()
    # Less than 16 bytes
    truncated = b"\x0e\x00\x00\x00\x83\x00\x01\x00"  # 8 bytes
    items = list(decoder.decode_buffer(truncated))
    assert len(items) == 1
    unparsed = items[0]
    assert isinstance(unparsed, UnparsedBlock)
    assert unparsed.length == 8
    assert "Truncated header" in unparsed.reason


def test_partial_trailing_record() -> None:
    decoder = LogDecoder()
    # 16-byte header says payload is 20 bytes, but only 5 bytes follow
    partial = make_record(
        payload_len=20,
        subsys_id=0x0083,
        area_id=0x01,
        timestamp_us=1000,
        payload=b"12345",
    )
    items = list(decoder.decode_buffer(partial))
    assert len(items) == 1
    unparsed = items[0]
    assert isinstance(unparsed, UnparsedBlock)
    assert "Truncated payload" in unparsed.reason

    # In strict mode, should raise ValueError
    strict_decoder = LogDecoder(strict=True)
    with pytest.raises(ValueError, match="Corruption"):
        list(strict_decoder.decode_buffer(partial))


def test_corrupt_payload_len_and_recovery() -> None:
    # First valid record
    rec1 = make_record(payload_len=4, subsys_id=0x83, area_id=14, timestamp_us=1000, payload=b"ABCD")
    # Corrupt record with enormous payload_len
    corrupt = struct.pack(HEADER_FORMAT, 0x7FFFFFFF, 0x83, 14, 2000)
    # Next valid record
    rec2 = make_record(payload_len=4, subsys_id=0x83, area_id=14, timestamp_us=3000, payload=b"EFGH")

    stream = rec1 + corrupt + rec2

    decoder = LogDecoder(max_payload_len=1024)
    items = list(decoder.decode_buffer(stream))

    # Should decode rec1, flag corruption block, and recover rec2
    assert len(items) == 3
    assert isinstance(items[0], LogRecord)
    assert items[0].index == 0
    assert items[0].payload_hex == b"ABCD".hex()

    assert isinstance(items[1], UnparsedBlock)
    assert items[1].offset == len(rec1)

    assert isinstance(items[2], LogRecord)
    assert items[2].index == 1
    assert items[2].payload_hex == b"EFGH".hex()


# ============================================================================
# 6. Filter & Grep Tests
# ============================================================================


def test_log_filter() -> None:
    rec1 = LogRecord(
        index=0,
        offset=0,
        payload_len=4,
        total_len=20,
        subsys_id=131,
        subsys_name="APP",
        area_id=1,
        area_name="DISPATCH",
        timestamp_us=1_000_000,
        timestamp_s=1.0,
        timestamp_str="[00001.000000]",
        payload_hex="01020304",
        message="event=0x1234",
    )
    rec2 = LogRecord(
        index=1,
        offset=20,
        payload_len=4,
        total_len=20,
        subsys_id=131,
        subsys_name="APP",
        area_id=10,
        area_name="MW_TRANSACTION",
        timestamp_us=5_000_000,
        timestamp_s=5.0,
        timestamp_str="[00005.000000]",
        payload_hex="05060708",
        message="tag='ERROR'",
    )

    # Subsystem filter
    f_sub = LogFilter(subsystems={131})
    assert f_sub.matches(rec1) is True

    # Area filter
    f_area = LogFilter(areas={10})
    assert f_area.matches(rec1) is False
    assert f_area.matches(rec2) is True

    # Timestamp filter
    f_time = LogFilter(start_time_s=2.0, end_time_s=6.0)
    assert f_time.matches(rec1) is False
    assert f_time.matches(rec2) is True

    # Grep filter
    import re

    f_grep = LogFilter(grep_pattern=re.compile(r"ERROR"))
    assert f_grep.matches(rec1) is False
    assert f_grep.matches(rec2) is True


# ============================================================================
# 7. CLI Execution & Output Formatting Tests
# ============================================================================


def run_cli(args: List[str]) -> subprocess.CompletedProcess:
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "research",
        "log_decoder",
        "decode_app_log.py",
    )
    cmd = [sys.executable, "-B", script_path] + args
    return subprocess.run(cmd, capture_output=True, text=True)


def test_cli_help() -> None:
    res = run_cli(["--help"])
    assert res.returncode == 0
    assert "Decode Sony ulogio binary application logs" in res.stdout


def test_cli_missing_file() -> None:
    res = run_cli(["non_existent_file.bin"])
    assert res.returncode != 0
    assert "Error: input file" in res.stderr


def test_cli_synthetic_formats() -> None:
    # Create temporary binary log
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        tmp_name = f.name
        # Write two records
        f.write(
            make_record(
                payload_len=4,
                subsys_id=131,
                area_id=14,
                timestamp_us=1000000,
                payload=b"\x01\x00\x00\x00",
            )
        )
        f.write(
            make_record(
                payload_len=8,
                subsys_id=131,
                area_id=14,
                timestamp_us=2000000,
                payload=b"\x02\x00\x00\x00\x03\x00\x00\x00",
            )
        )

    try:
        # Test text format
        res_text = run_cli([tmp_name, "-f", "text"])
        assert res_text.returncode == 0
        assert "rec=0" in res_text.stdout
        assert "rec=1" in res_text.stdout

        # Test json format
        res_json = run_cli([tmp_name, "-f", "json"])
        assert res_json.returncode == 0
        data = json.loads(res_json.stdout)
        assert len(data) == 2
        assert data[0]["index"] == 0
        assert data[1]["index"] == 1

        # Test jsonl format
        res_jsonl = run_cli([tmp_name, "-f", "jsonl"])
        assert res_jsonl.returncode == 0
        lines = [json.loads(line) for line in res_jsonl.stdout.strip().split("\n")]
        assert len(lines) == 2

        # Test csv format
        res_csv = run_cli([tmp_name, "-f", "csv"])
        assert res_csv.returncode == 0
        assert "index,offset,timestamp_us" in res_csv.stdout

        # Test summary format
        res_sum = run_cli([tmp_name, "-f", "summary"])
        assert res_sum.returncode == 0
        assert "SONY ULOGIO LOG DECODE SUMMARY" in res_sum.stdout
        assert "Total Records     : 2" in res_sum.stdout

        # Test file output flag
        out_tmp = tmp_name + ".out"
        res_out = run_cli([tmp_name, "-o", out_tmp])
        assert res_out.returncode == 0
        assert os.path.isfile(out_tmp)
        with open(out_tmp, "r", encoding="utf-8") as f_out:
            content = f_out.read()
            assert "rec=0" in content
        os.remove(out_tmp)

    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


# ============================================================================
# 8. Real Log Capture Verification (app-sequential.log)
# ============================================================================


@pytest.mark.skipif(
    not os.path.isfile(SAMPLE_LOG_PATH),
    reason="app-sequential.log sample file not present on system",
)
def test_real_app_sequential_log() -> None:
    """Validate full parsing of 1,936,183 bytes and 61,997 records."""
    decoder = LogDecoder()
    records = []
    unparsed_blocks = []

    gen = decoder.decode_file(SAMPLE_LOG_PATH)
    try:
        while True:
            item = next(gen)
            if isinstance(item, LogRecord):
                records.append(item)
            elif isinstance(item, UnparsedBlock):
                unparsed_blocks.append(item)
    except StopIteration as stop:
        stats = stop.value

    # Verify exact counts and zero unparsed bytes
    assert len(records) == 61997
    assert len(unparsed_blocks) == 0
    assert stats.parsed_bytes == 1936183
    assert stats.unparsed_bytes == 0
    assert stats.corrupted_records == 0

    # Verify Subsystem 131 exclusivity
    assert stats.subsystem_counts == {131: 61997}

    # Verify Area counts
    assert stats.area_counts[1] == 551
    assert stats.area_counts[2] == 627
    assert stats.area_counts[3] == 1863
    assert stats.area_counts[4] == 17466
    assert stats.area_counts[5] == 390
    assert stats.area_counts[6] == 230
    assert stats.area_counts[7] == 2230
    assert stats.area_counts[8] == 4577
    assert stats.area_counts[9] == 338
    assert stats.area_counts[10] == 7177
    assert stats.area_counts[11] == 1874
    assert stats.area_counts[12] == 2365
    assert stats.area_counts[14] == 22309
