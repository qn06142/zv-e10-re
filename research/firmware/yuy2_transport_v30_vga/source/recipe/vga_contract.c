#include "vga_contract.h"
#include "vga_resize.h"
int vga_source_contract(const sony_yc_metadata *m,uint32_t bytes,uint32_t handle){
 if(!m || !handle || handle>65535 || m->image_attach!=1 || m->unit_type!=0x295 ||
    m->unit_handle!=handle || m->data_site || m->yc_compress>1 ||
    m->data_transfer || m->data_placement!=1 || m->data_content!=2 || m->data_scan!=1 ||
    !m->canvas_size_x || !m->canvas_size_y ||
    m->canvas_size_x>4096 || m->canvas_size_y>4096 ||
    !m->valid_size_x || !m->valid_size_y ||
    m->valid_offset_x>m->canvas_size_x || m->valid_size_x>m->canvas_size_x-m->valid_offset_x ||
    m->valid_offset_y>m->canvas_size_y || m->valid_size_y>m->canvas_size_y-m->valid_offset_y)
  return -1;
 uint32_t n=m->canvas_size_x*m->canvas_size_y*(m->yc_compress==1?1u:2u);
 return m->unit_data_offset>bytes || n>bytes-m->unit_data_offset ? -1:0;
}
int vga_destination_contract(const sony_yc_metadata *m,uint32_t bytes,uint32_t handle){
 if(!m || !handle || handle>65535 || !m->image_attach || m->unit_type!=0x220 ||
    m->unit_handle!=handle || m->data_site || m->yc_compress ||
    m->canvas_size_x!=640 || m->canvas_size_y!=480 ||
    m->valid_offset_x || m->valid_offset_y || m->valid_size_x!=640 || m->valid_size_y!=480 ||
    m->target_offset_x || m->target_offset_y || m->target_size_x!=640 || m->target_size_y!=480)
  return -1;
 return m->unit_data_offset>bytes || VGA_BYTES>bytes-m->unit_data_offset ? -1:0;
}
