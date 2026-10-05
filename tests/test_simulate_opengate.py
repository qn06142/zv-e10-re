"""
test_simulate_opengate.py - Test End-to-End Simulation Runner
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.emulator.simulate_opengate import run_pipeline_simulation

def test_pipeline_simulation():
    res = run_pipeline_simulation()
    assert res == 0
