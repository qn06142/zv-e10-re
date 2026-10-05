import pytest
from research.device.osd_harness import (
    OsdOnOffPacket,
    OsdLayoutPacket,
    RectBlitParams,
    generate_osd_injection_c_source,
)


def test_osd_on_off_packet_structure():
    p = OsdOnOffPacket(on_off=1, alpha=255, plane_mask=1, layout_id=0)
    data = p.pack()
    assert len(data) == 20
    assert data[0:2] == b"\x01\x20"  # CMD 0x2001
    assert data[2:4] == b"\x02\x03"  # SUBCMD 0x0302
    assert data[4:6] == b"\x14\x00"  # LEN 20
    assert data[6:8] == b"\x01\x00"  # VER 1
    assert data[8] == 1              # ON
    assert data[9] == 255            # ALPHA
    assert data[12] == 1             # PLANE MASK


def test_osd_layout_packet_structure():
    p = OsdLayoutPacket(x=0, y=0, width=960, height=640, stride=960 * 4, format=1)
    data = p.pack()
    assert len(data) == 24
    assert data[0:2] == b"\x01\x20"  # CMD 0x2001
    assert data[2:4] == b"\x03\x03"  # SUBCMD 0x0303
    assert data[4:6] == b"\x18\x00"  # LEN 24
    assert data[6:8] == b"\x01\x00"  # VER 1


def test_rect_blit_params_structure():
    p = RectBlitParams(dst_x=10, dst_y=20, width=100, height=50)
    data = p.pack()
    assert len(data) == 22


def test_c_source_generation():
    src = generate_osd_injection_c_source()
    assert "OBJAVBBCBASECLASS5VdfCh11setOSDOnOff" in src
    assert "GRM_gpermRectblit" in src
    assert "GraphicsEngine" in src
