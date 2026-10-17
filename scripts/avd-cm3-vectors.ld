SECTIONS {
 .vectors 0 : { KEEP(*(.vectors)) }
 .text : ALIGN(4) { *(.text*) }
 .rodata : ALIGN(4) { *(.rodata*) }
 .data : ALIGN(4) { *(.data*) }
 .ARM.extab : ALIGN(4) { *(.ARM.extab*) }
 .ARM.exidx : ALIGN(4) { *(.ARM.exidx*) }
 /DISCARD/ : { *(.comment) *(.note*) }
}
ASSERT(ADDR(.vectors) == 0, "Cortex-M3 vectors must start at firmware offset zero")
