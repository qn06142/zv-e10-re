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
 dest.image_attach=1;dest.unit_type=0x220;dest.unit_handle=13;
 dest.canvas_size_x=dest.valid_size_x=dest.target_size_x=640;
 dest.canvas_size_y=dest.valid_size_y=dest.target_size_y=480;
 CHECK(!vga_destination_contract(&dest,614400,13));
 CHECK(vga_destination_contract(&dest,614399,13));
 CHECK(vga_destination_contract(&dest,614400,12));
 m=dest;m.yc_compress=1;CHECK(vga_destination_contract(&m,614400,13));
 m=dest;m.canvas_size_y=360;CHECK(vga_destination_contract(&m,614400,13));
 m=dest;m.valid_offset_y=1;CHECK(vga_destination_contract(&m,614400,13));
 m=dest;m.target_size_x=0;CHECK(vga_destination_contract(&m,614400,13));
 m=dest;m.unit_data_offset=1;CHECK(vga_destination_contract(&m,614400,13));CHECK(!vga_destination_contract(&m,614401,13));
 CHECK(vga_destination_contract(0,614400,13));
 puts("PASS: 20 metadata contract checks");return 0;
}
