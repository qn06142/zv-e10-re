#include "vga_contract.h"
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do{if(!(x)){puts("FAILED: " #x);exit(1);}}while(0)
int main(void){
 sony_yc_metadata source={0},dest={0},m;
 source.image_attach=1;source.data_placement=1;source.data_content=2;source.data_scan=1;source.unit_type=0x295;source.unit_handle=42;
 source.canvas_size_x=source.valid_size_x=1920;
 source.canvas_size_y=source.valid_size_y=1080;source.yc_compress=1;
 CHECK(!vga_source_contract(&source,2073600,42));
 CHECK(vga_source_contract(&source,2073599,42));
 CHECK(vga_source_contract(&source,2073600,43));
 m=source;m.unit_data_offset=0xfffffff0u;CHECK(vga_source_contract(&m,2073600,42));
 m=source;m.data_site=1;CHECK(vga_source_contract(&m,2073600,42));
 m=source;m.valid_offset_x=1;CHECK(vga_source_contract(&m,2073600,42));
 m=source;m.canvas_size_x=0x80000000u;CHECK(vga_source_contract(&m,2073600,42));
 m=source;m.yc_compress=0;CHECK(vga_source_contract(&m,2073600,42));CHECK(!vga_source_contract(&m,4147200,42));
 m=source;m.yc_compress=2;CHECK(vga_source_contract(&m,4147200,42));
 /* Test data_transfer relaxation: accept 0 and 1, reject > 1 */
 m=source;m.data_transfer=0;CHECK(!vga_source_contract(&m,2073600,42));CHECK(!vga_source_validate_metadata(&m,2073600,42));
 m=source;m.data_transfer=1;CHECK(!vga_source_contract(&m,2073600,42));CHECK(!vga_source_validate_metadata(&m,2073600,42));
 m=source;m.data_transfer=2;CHECK(vga_source_contract(&m,2073600,42));CHECK(vga_source_validate_metadata(&m,2073600,42));
 m=source;m.data_transfer=255;CHECK(vga_source_contract(&m,2073600,42));CHECK(vga_source_validate_metadata(&m,2073600,42));

 /* Validate against genuine retained descriptor from live hardware capture */
 {
  static unsigned char retained_buf[4096];
  const char *paths[]={
   ".local/outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin",
   "../outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin",
   "../../outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin",
   "../../../outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin",
   "../../../../outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin",
   "D:/02_Development_And_Projects/pmca-re/.local/outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin"
  };
  FILE *f=NULL;
  for(size_t i=0;i<sizeof(paths)/sizeof(paths[0]);i++){
   f=fopen(paths[i],"rb");
   if(f) break;
  }
  CHECK(f!=NULL);
  size_t n_read=fread(retained_buf,1,sizeof(retained_buf),f);
  fclose(f);
  CHECK(n_read==4096);
  sony_yc_metadata retained_m={0};
  CHECK(!sony_yc_sds_decode_image(retained_buf,n_read,&retained_m));
  CHECK(retained_m.image_attach==1);
  CHECK(retained_m.unit_type==0x295);
  CHECK(retained_m.unit_handle==0x7f24);
  CHECK(retained_m.data_site==0);
  CHECK(retained_m.yc_compress==1);
  CHECK(retained_m.data_transfer==1);
  CHECK(retained_m.data_placement==1);
  CHECK(retained_m.data_content==2);
  CHECK(retained_m.data_scan==1);
  CHECK(retained_m.canvas_size_x==1920 && retained_m.canvas_size_y==1080);
  CHECK(retained_m.valid_size_x==1920 && retained_m.valid_size_y==1080);
  CHECK(retained_m.strip_width==64);
  CHECK(!vga_source_contract(&retained_m,2073600,0x7f24));
  CHECK(!vga_source_validate_metadata(&retained_m,2073600,0x7f24));
  CHECK(vga_source_contract(&retained_m,2073599,0x7f24));
  CHECK(vga_source_contract(&retained_m,2073600,0x7f25));
 }

 dest.image_attach=1;dest.unit_type=0x127;dest.unit_handle=13;
 dest.canvas_size_x=dest.valid_size_x=dest.target_size_x=1920;
 dest.canvas_size_y=dest.valid_size_y=dest.target_size_y=1080;
 CHECK(!vga_destination_contract(&dest,4147200,13));
 CHECK(vga_destination_contract(&dest,4147199,13));
 CHECK(vga_destination_contract(&dest,4147200,12));
 m=dest;m.yc_compress=1;CHECK(vga_destination_contract(&m,4147200,13));
 m=dest;m.canvas_size_y=360;CHECK(vga_destination_contract(&m,4147200,13));
 m=dest;m.valid_offset_y=1;CHECK(vga_destination_contract(&m,4147200,13));
 m=dest;m.target_size_x=0;CHECK(vga_destination_contract(&m,4147200,13));
 m=dest;m.unit_data_offset=1;CHECK(vga_destination_contract(&m,4147200,13));CHECK(!vga_destination_contract(&m,4147201,13));
 CHECK(vga_destination_contract(0,4147200,13));
 m=source;m.canvas_size_x=m.valid_size_x=640;m.canvas_size_y=m.valid_size_y=480;CHECK(vga_source_contract(&m,2073600,42));
 m=dest;m.yc_bit_depth=1;CHECK(vga_destination_contract(&m,4147200,13));
 puts("PASS: metadata contract and genuine descriptor checks");return 0;
}
