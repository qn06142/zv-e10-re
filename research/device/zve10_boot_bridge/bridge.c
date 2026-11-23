/* SPDX-License-Identifier: GPL-2.0 */
#include <linux/module.h>
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/stddef.h>
/* Read-only privileged entry probe. No shutdown, MMIO writes or memory handoff. */
static int __init bridge_init(void) {
    unsigned cpsr,sctlr,mpidr;
    asm volatile("mrs %0, cpsr":"=r"(cpsr));
    asm volatile("mrc p15, 0, %0, c1, c0, 0":"=r"(sctlr));
    asm volatile("mrc p15, 0, %0, c0, c0, 5":"=r"(mpidr));
    printk(KERN_INFO "ZVBOOT_GATE_V1 mode=%02x sctlr=%08x mpidr=%08x RETURNED\n",
           cpsr&31,sctlr,mpidr);
    return (cpsr&31)==0x13?0:-22;
}
static void __exit bridge_exit(void) {
    printk(KERN_INFO "ZVBOOT_GATE_V1 UNLOADED\n");
}
module_init(bridge_init);
module_exit(bridge_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Returning privileged boot-handoff entry probe; no takeover");
const unsigned zve10_abi_layout[] __attribute__((section(".zve10_abi"),used))={
    sizeof(struct module),offsetof(struct module,name),
    offsetof(struct module,init),offsetof(struct module,exit)
};
