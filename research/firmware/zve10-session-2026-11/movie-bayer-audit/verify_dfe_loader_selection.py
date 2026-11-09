"""Execute native loader selection; intercept transfer and external I/O boundaries.

Default case uses the unmodified embedded getter. Fallback cases explicitly force
its return to zero to test otherwise unreachable control flow, not device state.
"""
import argparse, json, sys
from pathlib import Path
from unicorn.arm_const import UC_ARM_REG_SP
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('repo', type=Path)
a = p.parse_args()
sys.path.insert(0, str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness, MEM

rows = []
for case in ['native_embedded', 'forced_fallback_gate_closed', 'forced_fallback_gate_open']:
    h = Harness()
    primary, secondary = MEM, MEM+0x1000
    h.run(0x63d9cec4, primary, 0)
    h.run(0x63d9cf36, secondary, 0)
    observed = []
    def log(args): h.ret(0)
    h.callbacks[0x639d9788] = log
    if case != 'native_embedded':
        h.callbacks[0x63da0666] = lambda args: h.ret(0)
    def gate(args):
        observed.append({'boundary':'external_io_gate'})
        h.ret(int(case == 'forced_fallback_gate_open'))
    h.callbacks[0x639e0f18] = gate
    def load(args):
        text = bytes(h.u.mem_read(args[3], 64)).split(b'\0')[0].decode()
        observed.append({'boundary':'external_file', 'path':text})
        h.put(args[0]+4, MEM+0x20000)
        h.put(args[0]+0xc, 0x1234)
        h.ret(0)
    h.callbacks[0x63da11c0] = load
    def transfer(boundary):
        def cb(args):
            observed.append({'boundary':boundary, 'source':hex(h.word(args[1])),
                             'length':h.word(args[2]), 'descriptor':hex(args[3]),
                             'extra_descriptor':hex(h.word(h.u.reg_read(UC_ARM_REG_SP)))})
            h.ret(0)
        return cb
    h.callbacks[0x639dae50] = transfer('prepare_transfer')
    h.callbacks[0x63d9d33a] = transfer('submit_transfer')
    h.callbacks[0x639e0f80] = lambda args: h.ret(0)
    result = h.run(0x639daeb4, MEM+0x3000, secondary, primary)
    if case == 'native_embedded':
        assert [r['boundary'] for r in observed] == ['prepare_transfer','submit_transfer']
        assert all(r['source']=='0x64560700' and r['length']==65536 for r in observed)
        assert result == 1
    elif case.endswith('closed'):
        assert observed == [{'boundary':'external_io_gate'}] and result == 0
    else:
        assert [r['boundary'] for r in observed] == ['external_io_gate','external_file','prepare_transfer','submit_transfer']
        assert observed[1]['path'] == '/usr/dfe/dfe.bin'
        assert result == 1
    rows.append(dict(case=case, returned=result, observed=observed))
print(json.dumps(dict(cases=len(rows), native_loader='0x639daeb4',
    native_getter='0x639dfb38', default_getter_mocked=False,
    intercepted=['logger','transfer preparation','transfer submission','external I/O gate/load/close'],
    hardware_transfer_executed=False, rows=rows), indent=2))
