/* Connect the adapted Sony CPU renderer to pmca-re's emulated OSD0.
 * The guest publishes its own completed framebuffer; no host menu drawing.
 */
#ifndef PMCA_MENU_OSD_H
#define PMCA_MENU_OSD_H
#include <stdint.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

static void pmca_menu_present(uint32_t physical)
{
    static volatile uint32_t *osd;
    if (physical < 0x20000000u || physical > 0x28000000u - 640u * 480u * 2u)
        _exit(72);
    if (!osd) {
        int fd = open("/dev/mem", O_RDWR | O_SYNC);
        if (fd < 0) _exit(72);
        void *mapped = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0xf3441000u);
        close(fd);
        if (mapped == MAP_FAILED) _exit(72);
        osd = mapped;
    }
    __sync_synchronize();
    osd[0x320 / 4] = physical;
    osd[0x324 / 4] = 1280;
    osd[0x300 / 4] = 3;
    __sync_synchronize();
}
#endif
