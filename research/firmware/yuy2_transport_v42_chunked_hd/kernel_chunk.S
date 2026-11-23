.syntax unified
.arm
.section .text.yc42_chunk,"ax",%progbits
.global __yc42_extract_size
.type __yc42_extract_size,%function
__yc42_extract_size:
 ldr r7,[fp,#-0x2c]
 tst r7,#0x20000000
 bicne r7,r7,#0xe0000000
 b __yc42_ret_extract
.size __yc42_extract_size,.-__yc42_extract_size
.global __yc42_fid
.type __yc42_fid,%function
__yc42_fid:
 ldr r3,[fp,#-0x2c]
 tst r3,#0x20000000
 beq 1f
 ubfx r3,r3,#30,#1
 b 2f
1:
 ldr r3,[r5,#0x24]
 cmp r3,#1
 moveq r3,#0
 movne r3,#1
2:
 str r3,[r5,#0x24]
 b __yc42_ret_fid
.size __yc42_fid,.-__yc42_fid
.global __yc42_eof
.type __yc42_eof,%function
__yc42_eof:
 sub r8,r8,#0x72
 ldr r3,[fp,#-0x2c]
 tst r3,#0x20000000
 beq 1f
 tst r3,#0x80000000
 bicne r8,r8,#2
1:
 b __yc42_ret_eof
.size __yc42_eof,.-__yc42_eof
