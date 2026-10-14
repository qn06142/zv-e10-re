base_libobj = 0x06592000
base_libmpr = 0x07a2b000

patches = [
    # (name, va, hex_bytes, desc)
    ('mpr_whitelist', base_libmpr + 0x5422e8, '2f', 'Whitelist aspect 2 (3:2)'),
    ('obj_renderer', base_libobj + 0x25f918, '01207047', 'ObjRenderer -> Aspect 1 (Case 1: 3:2)'),
    ('obj_lv_table', base_libobj + 0xeb0f26, '01', 'Live View Table -> Case 1 (3240x2160)'),
    ('obj_rec_aspect', base_libobj + 0x978bea, '0222', 'Rec format 4K aspect -> 2 (3:2)'),
    ('obj_seq_1', base_libobj + 0x2d2388, '0222', 'Proxy seq 1 -> aspect 2'),
    ('obj_seq_2', base_libobj + 0x2d23a0, '0222', 'Proxy seq 2 -> aspect 2'),
    ('obj_seq_3', base_libobj + 0x2d23c4, '0223', 'Proxy seq 3 -> aspect 2'),
    ('obj_seq_4', base_libobj + 0x2d229c, '0223', 'AutoEdit enc -> aspect 2'),
    ('obj_astra_asp1', base_libobj + 0x2ccb3a, '0223', 'Astra Primary stream aspect -> 2'),
    ('obj_astra_asp2', base_libobj + 0x2ccb4a, '0223', 'Astra Secondary stream aspect -> 2'),
    ('obj_astra_msg_asp', base_libobj + 0x2cce38, '022300bf', 'AVBBC 0x55001f packet aspect -> 2 (BIONZ X 3:2 full readout)'),
    ('obj_astra_thm_w', base_libobj + 0x2d0020, '4ff48763', 'Astra thumbnail width -> 1080 (0x438)'),
    ('obj_astra_thm_ws', base_libobj + 0x2d002c, 'b423', 'Astra thumbnail width small -> 180 (0xb4)'),
    ('obj_lv_canvas_w', base_libobj + 0x260916, '40f6a842', 'Live view root canvas width -> 3240 (0xca8)'),
    ('obj_lv_case2_w', base_libobj + 0x26095e, '40f6a843', 'Live view Case 2 fallback width -> 3240 (0xca8)'),
]

lines = ['#!/bin/sh', 'PID=$(pidof im.elf)', '[ -z "$PID" ] && PID=157', 'echo "[+] Target im.elf PID: $PID"']
for name, va, val, desc in patches:
    lines.append(f'echo "[*] Patching {name}: {desc}..."')
    lines.append(f'/setting/mem_patch.elf $PID {va:08x} {val}')

# Add all 60 4K profile offsets
profile_offsets = [
    0x00c4a8f6, 0x00c4a98e, 0x00c4aa26, 0x00c4aabe, 0x00c4b736, 0x00c4b7ce,
    0x00c4b866, 0x00c4b8fe, 0x00c4bc8e, 0x00c4bd26, 0x00c4bdbe, 0x00c4be56,
    0x00c4c79a, 0x00c4c832, 0x00c4c8ca, 0x00c4c962, 0x00c4c9fa, 0x00c4ca92,
    0x00c4cb2a, 0x00c4cbc2, 0x00c4cc5a, 0x00c4ccf2, 0x00c4cd8a, 0x00c4ce22,
    0x00c4ceba, 0x00c4cf52, 0x00c4cfea, 0x00c4d082, 0x00c4d11a, 0x00c4d1b2,
    0x00c4d24a, 0x00c4d2e2, 0x00c4d37a, 0x00c4d412, 0x00c4d4aa, 0x00c4d542,
    0x00c507ba, 0x00c50852, 0x00c508ea, 0x00c50982, 0x00c50a1a, 0x00c50ab2,
    0x00c5198a, 0x00c51a22, 0x00c51aba, 0x00c51b52, 0x00c51bea, 0x00c51c82,
    0x00c5493a, 0x00c549d2, 0x00c54a6a, 0x00c54b02, 0x00c5518a, 0x00c55222,
    0x00c552ba, 0x00c55352, 0x00c5564a, 0x00c556e2, 0x00c5577a, 0x00c55812,
]
lines.append('echo "[*] Patching all 60 libmpr.so 4K profiles to 3240 width..."')
for po in profile_offsets:
    va = base_libmpr + po
    lines.append(f'/setting/mem_patch.elf $PID {va:08x} a80c >/dev/null 2>&1')

lines.append('echo "[+] Successfully patched all 60 profiles!"')
lines.append('echo "==================================================="')
lines.append('echo "[+] FULL ASTRA OPEN GATE 3:2 LIVE PATCH COMPLETE!"')
lines.append('echo "==================================================="')

script_content = '\n'.join(lines) + '\n'
with open('out/apply_full_opengate.sh', 'w', newline='\n') as f:
    f.write(script_content)

print(f'Generated out/apply_full_opengate.sh ({len(script_content)} bytes)')
