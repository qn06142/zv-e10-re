import sys, json
from pathlib import Path

# Add recipes path for rtos_harness
RECIPES_PATH = Path(r'D:/02_Development_And_Projects/pmca-re/research/firmware/raw_frame_source/verified_yc/evidence/frame-contract-20261029/recipes')
sys.path.insert(0, str(RECIPES_PATH.resolve()))
from rtos_harness import Harness

def test_global_gate_0x63d893f4():
    """Verify that 0x63d893f4 returns 1 ONLY when 0x6396e358(1) == 9, correcting previous report."""
    results = {}
    for test_val in range(12):
        h = Harness()
        h.callbacks[0x6396e358] = lambda a, tv=test_val: h.ret(tv)
        ret = h.run(0x63d893f4)
        results[test_val] = ret
        expected = 1 if test_val == 9 else 0
        assert ret == expected, f"Failed for {test_val}: got {ret}, expected {expected}"
    return results

def test_raw_decision_0x638f3adc():
    """Verify the exact decision logic of 0x638f3adc controlling AllocMem_Raw_Snr."""
    cases = []
    
    # Context structure base in harness RAM
    CTX = 0x40010000
    
    # Case 1: [context + 0x790] == 2 -> should return 0 (disabled mode)
    h = Harness()
    h.put(CTX + 0x790, 2)
    ret = h.run(0x638f3adc, CTX)
    assert ret == 0, f"Expected 0 for mode 2, got {ret}"
    cases.append(dict(description="mode 2", ret=ret))
    
    # Case 2: [context + 0x841] == 1 and dump tag 0x6c enabled -> should return 1
    h = Harness()
    h.put(CTX + 0x790, 0)
    h.put(CTX + 0x841, 1)
    # Callback for 0x63d89408 (CheckDumpEnabled)
    h.callbacks[0x63d89408] = lambda a: h.ret(1 if a[0] == 0x6c else 0)
    ret = h.run(0x638f3adc, CTX)
    assert ret == 1, f"Expected 1 for dump tag 0x6c enabled, got {ret}"
    cases.append(dict(description="dump tag 0x6c enabled", ret=ret))
    
    # Case 3: [context + 0x841] == 1 but dump tag 0x6c disabled, and [0x6858] == 0 -> should return 0
    h = Harness()
    h.put(CTX + 0x790, 0)
    h.put(CTX + 0x841, 1)
    h.callbacks[0x63d89408] = lambda a: h.ret(0)
    h.put(CTX + 0x6858, 0)
    ret = h.run(0x638f3adc, CTX)
    assert ret == 0, f"Expected 0 when dump tag disabled and mode 0, got {ret}"
    cases.append(dict(description="dump tag disabled, mode 0", ret=ret))
    
    # Case 4: Normal still capture: [context + 0x6858] == 1, config[0x6c] == 1, [context + 0x685c] == 0 -> should return 1
    h = Harness()
    h.put(CTX + 0x790, 0)
    h.put(CTX + 0x841, 0)
    h.put(CTX + 0x6858, 1)
    h.put(CTX + 0x685c, 0)
    # Mock config object GOT slot 0x6463cc24 pointing to 0x643bf438
    CONFIG_OBJ = 0x40020000
    h.put(0x6463cc24, CONFIG_OBJ)
    h.put(CONFIG_OBJ + 0x6c, 1) # Enable RAW in config
    ret = h.run(0x638f3adc, CTX)
    assert ret == 1, f"Expected 1 for still capture with config[0x6c]=1, got {ret}"
    cases.append(dict(description="still capture config[0x6c]=1", ret=ret))
    
    # Case 5: Normal still capture with config[0x6c] == 0 -> should return 0
    h = Harness()
    h.put(CTX + 0x790, 0)
    h.put(CTX + 0x841, 0)
    h.put(CTX + 0x6858, 1)
    h.put(CTX + 0x685c, 0)
    h.put(0x6463cc24, CONFIG_OBJ)
    h.put(CONFIG_OBJ + 0x6c, 0) # RAW disabled in config
    ret = h.run(0x638f3adc, CTX)
    assert ret == 0, f"Expected 0 for still capture with config[0x6c]=0, got {ret}"
    cases.append(dict(description="still capture config[0x6c]=0", ret=ret))
    
    return cases

if __name__ == '__main__':
    print("Testing 0x63d893f4...")
    gate_results = test_global_gate_0x63d893f4()
    print("Passed 0x63d893f4 tests:", gate_results)
    
    print("Testing 0x638f3adc...")
    dec_cases = test_raw_decision_0x638f3adc()
    print(f"Passed {len(dec_cases)} 0x638f3adc decision cases:", dec_cases)
    
    out_dir = Path('research/firmware/raw_frame_source/verified_bayer/evidence/raw-pipeline-audit-20261031')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / 'gate-decision-tests.json'
    out_file.write_text(json.dumps({
        'original_instructions': True,
        'camera_access': False,
        'global_gate_0x63d893f4_exact_value': 9,
        'raw_decision_cases': dec_cases,
        'limitations': 'Mocked external call returns and memory mappings. Establishes exact branch predicates.'
    }, indent=2))
    print(f"Saved evidence to {out_file}")
