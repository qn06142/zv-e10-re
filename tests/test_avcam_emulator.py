"""
test_avcam_emulator.py - Unit and Regression Tests for BIONZ X av-cam.bin Emulation
"""

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.emulator.avcam_emulator import BionzEmulator

def test_emulator_initialization():
    emu = BionzEmulator(verbose=False)
    assert emu is not None
    assert len(emu.firmware_bytes) == 17289388

def test_aspect_ratio_calculations():
    emu = BionzEmulator(verbose=False)
    
    # 0 -> 4:3
    num, den = emu.test_calc_aspect_ratio(0)
    assert (num, den) == (4, 3)

    # 1 -> 3:2
    num, den = emu.test_calc_aspect_ratio(1)
    assert (num, den) == (3, 2)

    # 2 -> 16:9
    num, den = emu.test_calc_aspect_ratio(2)
    assert (num, den) == (16, 9)

    # 3 -> 1:1
    num, den = emu.test_calc_aspect_ratio(3)
    assert (num, den) == (1, 1)

def test_packet_injection_3_2_opengate():
    emu = BionzEmulator(verbose=False)
    res = emu.inject_movie_aspect_packet(2) # 3:2 Open Gate
    
    events = res["captured_events"]
    assert len(events) >= 1
    # Check that event 0x8012 was posted to channel 0x40
    assert any(e["type_id"] == "0x8012" and e["channel"] == "0x40" for e in events)
