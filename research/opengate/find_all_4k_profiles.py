import struct

with open('D:/02_Development_And_Projects/pmca-re/dumps/camera_2025/usr/usr/lib/libmpr.so', 'rb') as f:
    data = f.read()

print('Scanning FRPA table for 3840x2160 entries...')
count = 0
for i in range(0xc40000, 0xc60000, 2):
    if data[i:i+4] == b'\x70\x08\x00\x0f': # height 2160, width 3840
        va = 0x08673000 + (i - 0x00c40000)
        h = struct.unpack('<H', data[i:i+2])[0]
        w = struct.unpack('<H', data[i+2:i+4])[0]
        aspect = struct.unpack('<H', data[i+4:i+6])[0]
        tag = data[i+12:i+16]
        print(f'Entry at foff 0x{i:x} (VA 0x{va:08x}): w={w} h={h} aspect={aspect} tag={tag}')
        count += 1
print('Total 3840x2160 entries found:', count)
