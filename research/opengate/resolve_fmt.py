with open('dumps/camera_2025/usr/usr/lib/libObj.so', 'rb') as f:
    # 0x2ccb6a: ldr r3, [pc, #0xf0]
    # In Thumb, pc for 0x2ccb6a is (0x2ccb6a + 4) & ~3 = 0x2ccb70
    # 0x2ccb70 + 0xf0 = 0x2ccc60
    f.seek(0x2ccc60)
    rel = int.from_bytes(f.read(4), 'little', signed=True)
    # The instruction at 0x2ccb72 is add r3, pc
    # At 0x2ccb72, pc = 0x2ccb72 + 4 = 0x2ccb76
    target = 0x2ccb76 + rel
    print(f"0x2ccb6a target: 0x{target:x}")
    f.seek(target)
    print("String 1:", f.read(128).split(b'\x00')[0])

    # 0x2ccbd6: ldr r3, [pc, #0x88]
    # At 0x2ccbd6, pc is (0x2ccbd6 + 4) & ~3 = 0x2ccbd8 + 0x88 = 0x2ccc60
    f.seek(0x2ccbd8 + 0x88)
    rel2 = int.from_bytes(f.read(4), 'little', signed=True)
    # At 0x2ccbde, add r3, pc -> pc is 0x2ccbde + 4 = 0x2ccbe2
    target2 = 0x2ccbe2 + rel2
    print(f"0x2ccbd6 target: 0x{target2:x}")
    f.seek(target2)
    print("String 2:", f.read(128).split(b'\x00')[0])
