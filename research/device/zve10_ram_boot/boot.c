/* SPDX-License-Identifier: GPL-2.0 */
#include <linux/module.h>
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/slab.h>
#include <linux/mm.h>
#include <linux/workqueue.h>
#include <linux/moduleparam.h>
#include <linux/kallsyms.h>
#include <linux/delay.h>
#include <linux/cpu.h>
#include <asm/cacheflush.h>
#include <asm/io.h>
#include <mach/hardware.h>
#include <mach/platform.h>
/* Only this platform's tested, minimal keep-mappings handoff. No flash writes. */
extern const unsigned char zve10_os_start[],zve10_os_end[];
struct boot_info {unsigned magic,gpio,reset,delay,entered,heartbeat,fault,display_failed,osd_control,animation,rtos_entry,rtos_context;};
static struct boot_info info;
static void *image;
static unsigned long stack;
static void __iomem *gpio,*misc;
static void *(*allocate_code)(unsigned long);
static void (*free_code)(struct module*,void*);
static void (*restart_prepare)(char*);
static void (*machine_stop)(void);
static void (*sync_files)(void);
static void (*remount_ro)(struct work_struct*);
static void (*touch_wdt)(void);
static char state[16]="UNPREPARED";
static atomic_t queued=ATOMIC_INIT(0);
static struct delayed_work boot_work;
#ifdef ZVE10_OSD_COMPARE
#include "osd_compare.h"
#ifdef ZVE10_OSD_FIRE
#include "osd_fire.h"
#endif
#endif
#ifdef ZVE10_RTOS_LOADER
#include "rtos_loader.h"
#endif
module_param_string(state,state,sizeof(state),0444);
static void boot_worker(struct work_struct *work) {
    if(raw_smp_processor_id()!=0) {strcpy(state,"CPU_ERROR");module_put(THIS_MODULE);return;}
    strcpy(state,"BOOTING");
    printk(KERN_EMERG "ZVBOOT_TAKEOVER_V1 CPU0 shutdown then RAM entry; MMU retained\n");
    sync_files();
    remount_ro(NULL);     /* Synchronously remount all RW block filesystems read-only. */
    sync_files();
    restart_prepare(NULL); /* Sony's normal notifier and device shutdown sequence. */
    machine_stop();       /* Park the other CPUs through the stock SMP stop path. */
    if(num_online_cpus()!=1 || !cpu_online(0)) {
        writel(0x11,misc+0x44);for(;;)cpu_relax();
    }
    local_irq_disable();
    local_fiq_disable();
    touch_wdt();          /* Refresh CPU0/global 500 ms budget before our ~300 ms image. */
#ifdef ZVE10_OSD_COMPARE
    {
        int result = start_osd_compare();
        info.display_failed = result && result != -ENODATA;
        info.osd_control = result ? 0 : (unsigned)osd_word(0x00);
#ifdef ZVE10_OSD_FIRE
        info.animation = result ? 0 : (unsigned)run_fire;
#endif
        if (result == -ENODATA)
            info.delay = max(info.delay / 4, 1U);
    }
#endif
    ((void(*)(struct boot_info*,unsigned long))image)(&info,stack+(PAGE_SIZE<<1));
    /* The image is non-returning. If it returns, force the same hardware reset. */
    writel(0x11,misc+0x44);
    for(;;)cpu_relax();
}
static int set_command(const char *value,const struct kernel_param *parameter) {
    if(value[0]!='G'||value[1]!='O'||(value[2] && !(value[2]=='\n'&&!value[3])))return -EINVAL;
    if(strcmp(state,"READY"))return -EINVAL;
    if(atomic_cmpxchg(&queued,0,1))return -EBUSY;
    if(!try_module_get(THIS_MODULE)){atomic_set(&queued,0);return -EBUSY;}
    strcpy(state,"QUEUED");
    if(!schedule_delayed_work_on(0,&boot_work,HZ)) {
        strcpy(state,"READY");atomic_set(&queued,0);module_put(THIS_MODULE);return -EBUSY;
    }
    return 0;
}
static const struct kernel_param_ops command_ops={.set=set_command};
module_param_cb(command,&command_ops,NULL,0200);
static void release_resources(void) {
#ifdef ZVE10_RTOS_LOADER
    release_rtos();
#endif
#ifdef ZVE10_OSD_COMPARE
    release_osd_compare();
#endif
    if(image && free_code)free_code(NULL,image);
    if(stack)free_pages(stack,1);
    /* GPIO and MISC use the board's pre-existing static device mappings. */
    image=NULL;stack=0;gpio=NULL;misc=NULL;
}
static int __init boot_init(void) {
    unsigned long bytes=zve10_os_end-zve10_os_start;
    if(num_online_cpus()!=4 || !bytes || bytes>PAGE_SIZE)return -EINVAL;
    allocate_code=(void*)kallsyms_lookup_name("module_alloc");
    free_code=(void*)kallsyms_lookup_name("module_free");
    restart_prepare=(void*)kallsyms_lookup_name("kernel_restart_prepare");
    machine_stop=(void*)kallsyms_lookup_name("machine_shutdown");
    sync_files=(void*)kallsyms_lookup_name("sys_sync");
    remount_ro=(void*)kallsyms_lookup_name("do_emergency_remount");
    touch_wdt=(void*)kallsyms_lookup_name("watchdog_touch");
    if(!allocate_code||!free_code||!restart_prepare||!machine_stop||!sync_files||!remount_ro||!touch_wdt)return -ENOENT;
    info.delay=loops_per_jiffy*(HZ/20);
    if(!info.delay || info.delay>100000000)return -EINVAL;
    image=allocate_code(PAGE_SIZE);
    stack=__get_free_pages(GFP_KERNEL|__GFP_ZERO,1);
    gpio=(void __iomem*)IO_ADDRESSP(CXD900X0_GPIO_BASE);
    misc=(void __iomem*)VA_MISC;
    if(!image||!stack||!gpio||!misc){release_resources();return -ENOMEM;}
    /* The private image and info mappings must share the worker's existing 1 MiB
       kernel page-table region. The image's private stack has no Linux thread_info. */
    {
        unsigned long region=(unsigned long)boot_worker>>20;
        if(((unsigned long)image>>20)!=region || ((unsigned long)&info>>20)!=region) {release_resources();return -ERANGE;}
    }
    memcpy(image,zve10_os_start,bytes);
    flush_icache_range((unsigned long)image,(unsigned long)image+bytes);
    info.magic=0x5a564231;info.gpio=(unsigned)gpio;info.reset=(unsigned)(misc+0x44);info.entered=0;
#ifdef ZVE10_OSD_COMPARE
    {
        int ret = prepare_osd_compare();
#ifdef ZVE10_OSD_FIRE
        if (!ret) ret = prepare_fire();
#endif
        if (ret) {release_resources();return ret;}
    }
#endif
#ifdef ZVE10_RTOS_LOADER
    {
        int ret = prepare_rtos();
        if (ret) {release_resources();return ret;}
    }
#endif
    INIT_DELAYED_WORK(&boot_work,boot_worker);
    strcpy(state,"READY");
    #ifdef ZVE10_DISPLAY_TEST
    printk(KERN_INFO "ZVBOOT_STAGE_V3 LCD colour trial prepared; inherited panel timings; no display writes yet\n");
#endif
#ifdef ZVE10_RESIDENT_RUNTIME
    printk(KERN_INFO "ZVBOOT_STAGE_V2 resident runtime prepared; battery restart to exit\n");
#endif
    printk(KERN_INFO "ZVBOOT_STAGE_V1 READY image=%p bytes=%lu stack=%lx delay=%u; no handoff yet\n",image,bytes,stack,info.delay);
    return 0;
}
static void __exit boot_exit(void) {
    cancel_delayed_work_sync(&boot_work);
    release_resources();printk(KERN_INFO "ZVBOOT_STAGE_V1 UNLOADED\n");
}
module_init(boot_init);module_exit(boot_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Explicit GO-only RAM image takeover; inherits MMU and resets after LED test");
const unsigned zve10_abi_layout[] __attribute__((section(".zve10_abi"),used))={
 sizeof(struct module),offsetof(struct module,name),offsetof(struct module,init),offsetof(struct module,exit)
};
