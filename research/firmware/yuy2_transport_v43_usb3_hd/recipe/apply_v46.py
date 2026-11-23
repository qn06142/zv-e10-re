import re
from pathlib import Path

target_file = Path(r"D:\02_Development_And_Projects\pmca-re\research\firmware\yuy2_transport_v43_usb3_hd\recipe\vga_resize.c")
content = target_file.read_text(encoding="utf-8")

# 1. open_transferred(meta, 1) and handle morc > 0
s1_old = """\
 if(open_transferred(meta,0))return -1;"""
s1_new = """\
 int morc=open_transferred(meta,1);
 if(morc>0){
  if(return_event(meta,pixels))return -1;
  return 1;
 }
 if(morc<0)return -1;"""
assert s1_old in content, "Patch 1 anchor not found"
content = content.replace(s1_old, s1_new, 1)

# 2. Settle loop: 32 attempts, sched_yield, and non-fatal descriptor rejection
s2_old = """\
 for(unsigned attempt=0;attempt<8;attempt++){
  m=(sony_yc_metadata){0};
  memcpy(source_snapshot,meta->map.bytes,n);barrier();
  memcpy(source_verify,meta->map.bytes,n);barrier();
  changed=memcmp(source_snapshot,source_verify,n)!=0;
  ir=sony_yc_sds_decode_image(source_snapshot,n,&m);
  sr=sony_yc_sds_decode_state(source_snapshot,n,&state);
  mr=sony_yc_sds_decode_multi_segment(source_snapshot,n,&multi);
  mask=(meta->ref.bytes<32 || meta->ref.bytes>sizeof(source_snapshot)?1u:0u)|
   (changed?2u:0u)|(ir?4u:0u)|(sr?8u:0u)|(mr!=-2?16u:0u);
  if(!ir && (m.image_attach || m.unit_handle))mask|=(m.unit_type!=0x295?32u:0u)|(!m.unit_handle?64u:0u)|(m.unit_handle==meta->ref.handle?128u:0u);
  if(mask)trace("METADATA_ATTEMPT_REJECTED",attempt+1,mask,n);
  else if(attempt)trace("METADATA_SETTLED",attempt+1,0,n);
  if(!mask || (mask&~30u) || attempt==7 || stopping)break;
  /* Retry the same mapping immediately; no timed delay. */
 }

 if(mask){
  rejection_pending=1;rejection_bytes=n;rejection_mask=mask;
  memset(rejection_header,0,sizeof(rejection_header));memcpy(rejection_header,"YC38RJ01",8);
  record_word(8,1);record_word(12,sizeof(rejection_header));record_word(16,n);record_word(20,meta->ref.bytes);
  record_word(24,mask);record_word(28,ev.sds);record_word(32,ev.type);record_word(36,meta->ref.physical);
  record_word(40,(unsigned)ir);record_word(44,(unsigned)sr);record_word(48,(unsigned)mr);
  record_word(52,m.unit_type);record_word(56,m.unit_handle);record_word(60,m.unit_data_offset);
  record_word(64,m.image_attach);record_word(68,m.yc_compress);record_word(72,changed);record_word(76,80+2*n);
  trace("EVENT_DESCRIPTOR_REJECTED",ev.sds,mask,n);
  trace("EVENT_PARSE_RESULTS",(unsigned)ir,(unsigned)sr,(unsigned)mr);
  trace("EVENT_DESCRIPTOR_HEADER",bounded_word(source_snapshot,n,0),bounded_word(source_snapshot,n,8),bounded_word(source_snapshot,n,12));
  trace("EVENT_DESCRIPTOR_SIZE",meta->ref.bytes,n,bounded_word(source_snapshot,n,16));
  trace("EVENT_IMAGE_ID",m.unit_type,m.unit_handle,m.unit_data_offset);
  trace("EVENT_IMAGE_GEOMETRY",((unsigned)m.canvas_size_x<<16)|m.canvas_size_y,((unsigned)m.valid_size_x<<16)|m.valid_size_y,m.image_attach);
  trace("EVENT_IMAGE_FORMAT",m.yc_compress,((unsigned)m.data_placement<<24)|((unsigned)m.data_content<<16)|((unsigned)m.data_scan<<8)|m.yc_bit_depth,m.strip_width);
  __atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;
 }"""

s2_new = """\
 for(unsigned attempt=0;attempt<32;attempt++){
  m=(sony_yc_metadata){0};
  memcpy(source_snapshot,meta->map.bytes,n);barrier();
  memcpy(source_verify,meta->map.bytes,n);barrier();
  changed=memcmp(source_snapshot,source_verify,n)!=0;
  ir=sony_yc_sds_decode_image(source_snapshot,n,&m);
  sr=sony_yc_sds_decode_state(source_snapshot,n,&state);
  mr=sony_yc_sds_decode_multi_segment(source_snapshot,n,&multi);
  mask=(meta->ref.bytes<32 || meta->ref.bytes>sizeof(source_snapshot)?1u:0u)|
   (changed?2u:0u)|(ir?4u:0u)|(sr?8u:0u)|(mr!=-2?16u:0u);
  if(!ir && (m.image_attach || m.unit_handle))mask|=(m.unit_type!=0x295?32u:0u)|(!m.unit_handle?64u:0u)|(m.unit_handle==meta->ref.handle?128u:0u);
  if(mask)trace("METADATA_ATTEMPT_REJECTED",attempt+1,mask,n);
  else if(attempt)trace("METADATA_SETTLED",attempt+1,0,n);
  if(!mask || (mask&~30u) || attempt==31 || stopping)break;
  syscall(158);
 }

 if(mask){
  rejection_pending=1;rejection_bytes=n;rejection_mask=mask;
  memset(rejection_header,0,sizeof(rejection_header));memcpy(rejection_header,"YC38RJ01",8);
  record_word(8,1);record_word(12,sizeof(rejection_header));record_word(16,n);record_word(20,meta->ref.bytes);
  record_word(24,mask);record_word(28,ev.sds);record_word(32,ev.type);record_word(36,meta->ref.physical);
  record_word(40,(unsigned)ir);record_word(44,(unsigned)sr);record_word(48,(unsigned)mr);
  record_word(52,m.unit_type);record_word(56,m.unit_handle);record_word(60,m.unit_data_offset);
  record_word(64,m.image_attach);record_word(68,m.yc_compress);record_word(72,changed);record_word(76,80+2*n);
  trace("EVENT_DESCRIPTOR_REJECTED",ev.sds,mask,n);
  trace("EVENT_PARSE_RESULTS",(unsigned)ir,(unsigned)sr,(unsigned)mr);
  trace("EVENT_DESCRIPTOR_HEADER",bounded_word(source_snapshot,n,0),bounded_word(source_snapshot,n,8),bounded_word(source_snapshot,n,12));
  trace("EVENT_DESCRIPTOR_SIZE",meta->ref.bytes,n,bounded_word(source_snapshot,n,16));
  trace("EVENT_IMAGE_ID",m.unit_type,m.unit_handle,m.unit_data_offset);
  trace("EVENT_IMAGE_GEOMETRY",((unsigned)m.canvas_size_x<<16)|m.canvas_size_y,((unsigned)m.valid_size_x<<16)|m.valid_size_y,m.image_attach);
  trace("EVENT_IMAGE_FORMAT",m.yc_compress,((unsigned)m.data_placement<<24)|((unsigned)m.data_content<<16)|((unsigned)m.data_scan<<8)|m.yc_bit_depth,m.strip_width);
  if(return_event(meta,pixels))return -1;
  return 1;
 }"""
assert s2_old in content, "Patch 2 anchor not found"
content = content.replace(s2_old, s2_new, 1)

# 3. resize_frame: return 1 on rejection instead of quarantine
s3_old = """\
 if(rc || ack_status || cmp_status){trace("REJECTED",rc,ack_status,cmp_status);__atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);return -1;}"""
s3_new = """\
 if(rc || ack_status || cmp_status){trace("REJECTED",rc,ack_status,cmp_status);return 1;}"""
assert s3_old in content, "Patch 3 anchor not found"
content = content.replace(s3_old, s3_new, 1)

# 4. drain loop in worker: don't assert shared_fault on dropped frames
s4_old = """\
    if(dmm_status(rc,reply) || !reply_identity(reply,4,ev.sds)){
     trace("FREE_UNCERTAIN",ev.sds,(unsigned)rc,reply_word(reply,0));
     __atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);
     break;
    }
    if(yc_port_complete()){
     __atomic_store_n(&shared_fault,1,__ATOMIC_RELEASE);
     break;
    }"""
s4_new = """\
    if(dmm_status(rc,reply) || !reply_identity(reply,4,ev.sds)){
     trace("FREE_UNCERTAIN",ev.sds,(unsigned)rc,reply_word(reply,0));
    }
    if(yc_port_complete()){
     trace("PORT_COMPLETE_FAILED",ev.sds,0,0);
    }"""
assert s4_old in content, "Patch 4 anchor not found"
content = content.replace(s4_old, s4_new, 1)

# 5. worker resize_frame call: handle return 1
s5_old = """\
  if(resize_frame(&meta,&pixels))break;"""
s5_new = """\
  int rres=resize_frame(&meta,&pixels);
  if(rres>0){return_event(&meta,&pixels);trace_flush();continue;}
  if(rres<0)break;"""
assert s5_old in content, "Patch 5 anchor not found"
content = content.replace(s5_old, s5_new, 1)

# 6. done: persist rejection if pending even without fault
s6_old = """\
 if(fault)persist_rejection();"""
s6_new = """\
 if(fault || rejection_pending)persist_rejection();"""
assert s6_old in content, "Patch 6 anchor not found"
content = content.replace(s6_old, s6_new, 1)

target_file.write_text(content, encoding="utf-8")
print("SUCCESSFULLY_PATCHED_VGA_RESIZE_C")
