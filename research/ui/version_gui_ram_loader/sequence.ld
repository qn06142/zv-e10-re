original_ctor = 0x4108d;
original_transform = 0x3f421;
original_layout = 0x41a0d;
state_address = 0x97b30;
ENTRY(ctor_hook)
SECTIONS {
 . = 0xa00c0;
 .text : { *(.text.hooks) *(.text*) *(.rodata*) }
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
}
