/* SPDX-License-Identifier: GPL-2.0 */
/* Linker script for C bare-metal ZV-E10 payloads running at DDR0 VA 0x81000000. */

ENTRY(_start)

SECTIONS {
    . = 0x81000000;
    __image_start = .;

    .text : ALIGN(4) {
        *(.text.boot*)
        *(.text*)
    }

    .rodata : ALIGN(4) {
        *(.rodata*)
    }

    .data : ALIGN(4) {
        *(.data*)
    }

    . = ALIGN(4);
    __image_end = .;

    .bss (NOLOAD) : ALIGN(8) {
        __bss_start = .;
        *(.bss*)
        *(COMMON)
        . = ALIGN(8);
        __bss_end = .;
    }

    /DISCARD/ : {
        *(.ARM.exidx*)
        *(.ARM.extab*)
        *(.comment*)
        *(.note*)
    }
}
