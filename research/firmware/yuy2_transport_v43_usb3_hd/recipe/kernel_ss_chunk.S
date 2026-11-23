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

.global __yc48_register_drivers
.type __yc48_register_drivers,%function
__yc48_register_drivers:
	push {r4, r5, r6, lr}
	mov r4, r0                 /* r4 = &dev->hs_driver (dev + 0x38) */
	sub r5, r4, #0x38          /* r5 = dev */

	/* 1. Register High-Speed driver */
	bl usb_gadgetcore_register_driver
	subs r6, r0, #0
	bne 9f                     /* HS registration failed -> exit */

	/* 2. Clone 60 bytes (15 words) from dev+0x38 (hs_driver) to dev+0x74 (ss_driver) */
	mov r2, #1
	strb r2, [r5, #0x2c]       /* dev->has_ss = 1 */
	add r0, r5, #0x74          /* r0 = &dev->ss_driver */

	mov ip, r0
	mov lr, r4
	ldmia lr!, {r1, r2, r3, r4}
	stmia ip!, {r1, r2, r3, r4}
	ldmia lr!, {r1, r2, r3, r4}
	stmia ip!, {r1, r2, r3, r4}
	ldmia lr!, {r1, r2, r3, r4}
	stmia ip!, {r1, r2, r3, r4}
	ldmia lr,  {r1, r2, r3}
	stmia ip,  {r1, r2, r3}

	/* 3. Configure SuperSpeed driver fields */
	ldrb r1, [r5, #0x3c]       /* endpoint number (from hs_driver.ep_num) */
	strb r1, [r5, #0x78]       /* ss_driver.ep_num = hs_driver.ep_num */
	mov r2, #5                 /* USB_SPEED_SUPER (5) */
	strb r2, [r5, #0x79]       /* ss_driver.speed = 5 */

	/* 4. Register SuperSpeed driver */
	add r0, r5, #0x74          /* &dev->ss_driver */
	bl usb_gadgetcore_register_driver
	subs r6, r0, #0
	beq 8f                     /* Success */

	/* SS registration failed: rollback HS driver */
	add r0, r5, #0x38
	bl usb_gadgetcore_unregister_driver
	mov r2, #0
	strb r2, [r5, #0x2c]
	b 9f

8:
	mov r0, #0
	pop {r4, r5, r6, pc}

9:
	mov r0, r6
	pop {r4, r5, r6, pc}
.size __yc48_register_drivers,.-__yc48_register_drivers

.global __yc48_unregister_drivers
.type __yc48_unregister_drivers,%function
__yc48_unregister_drivers:
	push {r4, r5, lr}
	mov r4, r0                 /* r4 = &dev->hs_driver (dev + 0x38) */
	sub r5, r4, #0x38          /* r5 = dev */

	/* Check if SuperSpeed driver was registered */
	ldrb r3, [r5, #0x2c]
	cmp r3, #0
	beq 1f

	/* Unregister SuperSpeed driver first */
	add r0, r5, #0x74          /* &dev->ss_driver */
	bl usb_gadgetcore_unregister_driver
	mov r3, #0
	strb r3, [r5, #0x2c]

1:
	/* Unregister High-Speed driver */
	mov r0, r4                 /* &dev->hs_driver */
	bl usb_gadgetcore_unregister_driver
	pop {r4, r5, pc}
.size __yc48_unregister_drivers,.-__yc48_unregister_drivers
