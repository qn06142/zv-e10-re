"""Generate raw_uvc_carrier.c by adapting the verified yuy2_1080_v43chunk.c transport."""
from pathlib import Path

ROOT = Path(r"D:\02_Development_And_Projects\pmca-re")
SRC = ROOT / "research/firmware/yuy2_transport_v43_usb3_hd/recipe/yuy2_1080_v43chunk.c"
OUT = ROOT / "research/firmware/raw_uvc_v01/raw_uvc_carrier.c"

text = SRC.read_text(encoding="utf-8")

# Replace header include and frame parameters
text = text.replace('#include "vga_resize.h"', '#include "raw_source_file.h"')
text = text.replace("#define FRAME_BYTES (1920u*1080u*2u)", "#define FRAME_BYTES RAW_UVC_FRAME_BYTES")
text = text.replace("#define CHUNK_BYTES 614400u", "#define CHUNK_BYTES RAW_UVC_CHUNK_BYTES")
text = text.replace("#define INTERVAL_100NS 416667u", "#define INTERVAL_100NS 2000000u")
text = text.replace('#define LOG "/log/yuy2_1080_v43chunk/runtime.log"', '#define LOG "/log/raw_uvc_v01/runtime.log"')
text = text.replace('dlopen("/usr/lib/yuy2_1080_v43chunk.so",2|4)', 'dlopen("/usr/lib/raw_uvc_v01.so",2|4)')

# Track per-frame header & RAW byte size
old_vars = "static unsigned frame_offset,frame_sequence;"
new_vars = """static unsigned frame_offset,frame_sequence;
static unsigned char current_raw_hdr[RAW_UVC_HDR_BYTES];
static uint32_t current_raw_bytes;"""
assert old_vars in text
text = text.replace(old_vars, new_vars, 1)

# Replace resize_reusable / resize_stop with raw_source_close
text = text.replace("if(output_session_closed || !vga_resize_reusable())return 41;",
                    "if(output_session_closed)return 41;")
text = text.replace("vga_resize_stop();", "raw_source_close();")

# Replace chunk acquisition inside produce()
old_chunk = """ uint32_t sequence=0;
 unsigned chunk=FRAME_BYTES-frame_offset;if(chunk>CHUNK_BYTES)chunk=CHUNK_BYTES;
 int source_error=vga_resize_copy_chunk(pixels,capacity,&sequence,physical,base,staging,handle,frame_offset,chunk);"""
new_chunk = """ uint32_t sequence=frame_sequence?frame_sequence:(frames+1u);
 if(!frame_offset){
  int pe=raw_source_prepare(sequence,current_raw_hdr,&current_raw_bytes);
  if(pe){
   if(raw_errors<0xffffffffu)raw_errors++;
   if(raw_errors==1)log3("RAW_WAIT_CAPTURE",(u32)pe,raw_errors,0);
   sched_yield();return 4;
  }
 }
 unsigned chunk=FRAME_BYTES-frame_offset;if(chunk>CHUNK_BYTES)chunk=CHUNK_BYTES;
 int source_error=raw_source_read_chunk(current_raw_hdr,current_raw_bytes,frame_offset,(u8*)pixels,chunk);"""
assert old_chunk in text
text = text.replace(old_chunk, new_chunk, 1)

# Replace vga_resize_frame_done(sequence) cleanly
old_done = "if(vga_resize_frame_done(sequence)){request_failure(45);return 4;}"
new_done = "/* Full raw frame chunks completed */"
assert old_done in text
text = text.replace(old_done, new_done, 1)

# Update descriptor dimensions 1920x1080 -> 6144x4100 and 5 fps bitrate (fits u32)
text = text.replace("w16(f+5,1920);w16(f+7,1080);",
                    "w16(f+5,RAW_UVC_WIDTH);w16(f+7,RAW_UVC_HEIGHT);")
text = text.replace("w32(f+9,FRAME_BYTES*8*24);w32(f+13,FRAME_BYTES*8*24);",
                    "w32(f+9,FRAME_BYTES*8u*5u);w32(f+13,FRAME_BYTES*8u*5u);")

# Also adapt make_trampoline/extra_guards placeholder so build.py fills it from libInfraStreamingUsb.so
old_guards = "static const u8 extra_guards[6][10]={{0x2d,0xe9,0xf0,0x41,0x92,0xb0,0x0,0x22,0x4,0x46},{0xf0,0xb5,0x4,0x46,0x83,0xb0,0x2,0xaf,0x4,0x20},{0xf0,0xb5,0x4,0x46,0x83,0xb0,0x4,0x20,0x3,0x21},{0xb0,0xb5,0x4,0x46,0x1,0x21,0x4,0x20,0x0,0x22},{0x80,0xb5,0x3,0x20,0x0,0xaf,0x1,0x21,0x0,0x22},{0x3,0x20,0x0,0x22,0x80,0xb5,0x1,0x46,0x0,0xaf}};"
new_guards = "static const u8 extra_guards[6][10]={EXTRA_GUARDS};"
assert old_guards in text
text = text.replace(old_guards, new_guards, 1)

# Clean log tag
text = text.replace('"YUY2 %s %08x %08x %08x\\n"', '"RAWUVC %s %08x %08x %08x\\n"')
text = text.replace('log3("RAW_BYTES",sequence,raw_offset,FRAME_BYTES);',
                    'log3("RAW_BYTES",sequence,current_raw_bytes,FRAME_BYTES);')

OUT.write_text(text, encoding="utf-8", newline="\n")
print("Wrote", OUT, len(text), "bytes")
