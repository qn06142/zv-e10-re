#!/usr/bin/env python3
"""Generates structured index and trace artifact for Sony ulogio binary log capture."""

import hashlib
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from research.log_decoder.decode_app_log import LogDecoder, LogRecord, UnparsedBlock, format_timestamp

SAMPLE_PATH = (
    r"C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\usb-debug-20261024-01\camera\app-sequential.log"
)
OUTPUT_PATH = os.path.join(
    REPO_ROOT, "research", "log_decoder", "app_log_index.json"
)


def compute_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def generate_index() -> None:
    if not os.path.isfile(SAMPLE_PATH):
        print(f"Sample log {SAMPLE_PATH} not found.")
        return

    file_size = os.path.getsize(SAMPLE_PATH)
    file_sha256 = compute_sha256(SAMPLE_PATH)

    decoder = LogDecoder()
    gen = decoder.decode_file(SAMPLE_PATH)

    records = []
    unparsed = []

    try:
        while True:
            item = next(gen)
            if isinstance(item, LogRecord):
                records.append(item)
            elif isinstance(item, UnparsedBlock):
                unparsed.append(item)
    except StopIteration as stop:
        stats = stop.value

    # Identify Phase 1 runs
    phase1_runs = []
    current_aid = None
    run_start_idx = 0
    run_start_off = 0
    run_records = 0
    run_min_ts = None
    run_max_ts = None

    for i, r in enumerate(records):
        if r.offset >= 499470:
            # End of Phase 1
            if current_aid is not None:
                phase1_runs.append(
                    {
                        "run_id": len(phase1_runs),
                        "area_id": current_aid,
                        "area_name": records[run_start_idx].area_name,
                        "record_range": [run_start_idx, i - 1],
                        "record_count": run_records,
                        "byte_range": [run_start_off, r.offset],
                        "timestamp_range_s": [
                            run_min_ts / 1e6,
                            run_max_ts / 1e6,
                        ],
                    }
                )
            break

        if r.area_id != current_aid:
            if current_aid is not None:
                phase1_runs.append(
                    {
                        "run_id": len(phase1_runs),
                        "area_id": current_aid,
                        "area_name": records[run_start_idx].area_name,
                        "record_range": [run_start_idx, i - 1],
                        "record_count": run_records,
                        "byte_range": [run_start_off, r.offset],
                        "timestamp_range_s": [
                            run_min_ts / 1e6,
                            run_max_ts / 1e6,
                        ],
                    }
                )
            current_aid = r.area_id
            run_start_idx = i
            run_start_off = r.offset
            run_records = 0
            run_min_ts = r.timestamp_us
            run_max_ts = r.timestamp_us

        run_records += 1
        if run_min_ts is None or r.timestamp_us < run_min_ts:
            run_min_ts = r.timestamp_us
        if run_max_ts is None or r.timestamp_us > run_max_ts:
            run_max_ts = r.timestamp_us

    # Identify key milestones
    milestones = []
    key_errors = []

    for r in records:
        # Check baseline 1
        if r.offset == 504783:
            milestones.append(
                {
                    "event": "service_mode_baseline_1",
                    "record_index": r.index,
                    "offset": r.offset,
                    "timestamp_s": r.timestamp_s,
                    "timestamp_str": r.timestamp_str,
                    "message": r.message,
                }
            )
        # Check baseline 2
        elif r.offset == 508944:
            milestones.append(
                {
                    "event": "service_mode_baseline_2_exit",
                    "record_index": r.index,
                    "offset": r.offset,
                    "timestamp_s": r.timestamp_s,
                    "timestamp_str": r.timestamp_str,
                    "message": r.message,
                }
            )
        # Check 0x50f unit allocations
        elif "0f050000" in r.payload_hex:
            milestones.append(
                {
                    "event": "unit_0x50f_allocation_request",
                    "record_index": r.index,
                    "offset": r.offset,
                    "timestamp_s": r.timestamp_s,
                    "timestamp_str": r.timestamp_str,
                    "area_id": r.area_id,
                    "payload_hex": r.payload_hex,
                    "message": r.message,
                }
            )
        # Check Model loaded
        elif "camera Model loaded" in r.message:
            milestones.append(
                {
                    "event": "camera_model_loaded",
                    "record_index": r.index,
                    "offset": r.offset,
                    "timestamp_s": r.timestamp_s,
                    "timestamp_str": r.timestamp_str,
                    "message": r.message,
                }
            )
        # Check transition errors
        elif r.area_id == 10 and r.parsed.get("tag") in ("ERROR", "MwfError"):
            item = {
                "record_index": r.index,
                "offset": r.offset,
                "timestamp_s": r.timestamp_s,
                "timestamp_str": r.timestamp_str,
                "tag": r.parsed.get("tag"),
                "message": r.message,
                "payload_hex": r.payload_hex,
            }
            key_errors.append(item)
            if r.offset in (0x0bad34, 0x0bad60, 0x0c2dd7):
                milestones.append(
                    {
                        "event": f"transition_failure_{r.parsed.get('tag')}",
                        **item,
                    }
                )
        # Check video mute
        elif "ActionSetYuvUiMute" in r.message and r.offset == 0x1d39fc:
            milestones.append(
                {
                    "event": "terminal_yuv_ui_mute",
                    "record_index": r.index,
                    "offset": r.offset,
                    "timestamp_s": r.timestamp_s,
                    "timestamp_str": r.timestamp_str,
                    "message": r.message,
                }
            )

    # Terminal record
    final_rec = records[-1]
    milestones.append(
        {
            "event": "terminal_record_before_power_off",
            "record_index": final_rec.index,
            "offset": final_rec.offset,
            "timestamp_s": final_rec.timestamp_s,
            "timestamp_str": final_rec.timestamp_str,
            "message": final_rec.message,
        }
    )

    doc = {
        "file_metadata": {
            "path": SAMPLE_PATH,
            "size_bytes": file_size,
            "sha256": file_sha256,
            "total_records": len(records),
            "parsed_bytes": stats.parsed_bytes,
            "unparsed_bytes": stats.unparsed_bytes,
            "corrupted_records": stats.corrupted_records,
            "timestamp_range": {
                "min_us": stats.min_timestamp_us,
                "max_us": stats.max_timestamp_us,
                "min_s": (stats.min_timestamp_us or 0) / 1e6,
                "max_s": (stats.max_timestamp_us or 0) / 1e6,
                "duration_s": stats.timespan_seconds,
            },
        },
        "phases": {
            "phase_1_ring_buffer_backlog": {
                "byte_range": [0, 499470],
                "record_range": [0, 15364],
                "record_count": 15365,
                "runs": phase1_runs,
            },
            "phase_2_live_streaming": {
                "byte_range": [499470, file_size],
                "record_range": [15365, len(records) - 1],
                "record_count": len(records) - 15365,
                "start_timestamp_s": records[15365].timestamp_s,
                "end_timestamp_s": final_rec.timestamp_s,
                "duration_seconds": final_rec.timestamp_s - records[15365].timestamp_s,
            },
        },
        "milestones": milestones,
        "subsystems": stats.subsystem_counts,
        "area_distribution": stats.area_counts,
        "error_event_count": len(key_errors),
        "key_error_events_sample": key_errors[:15],
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)

    print(f"Generated index: {OUTPUT_PATH}")
    print(f"Total records indexed: {len(records)}, milestones: {len(milestones)}")


if __name__ == "__main__":
    generate_index()
