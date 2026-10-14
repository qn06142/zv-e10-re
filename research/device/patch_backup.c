int open(const char* pathname, int flags, ...);
int close(int fd);
int read(int fd, void* buf, unsigned int count);
int write(int fd, const void* buf, unsigned int count);
long lseek(int fd, long offset, int whence);
void sync(void);
int printf(const char* format, ...);
void* malloc(unsigned int size);
void free(void* ptr);
int memcmp(const void* s1, const void* s2, unsigned int n);

#define O_RDONLY    00000000
#define O_WRONLY    00000001
#define O_RDWR      00000002
#define O_CREAT     00000100
#define O_TRUNC     00001000

#define BACKUP_PATH   "/setting/Backup.bin"
#define BACKUP_MIRROR "/setting/Backup.bak"
#define BACKUP_ORIG   "/setting/Backup.orig"

#define PROP_MOVIE_ASPECT_OFFSET 0xc12e8
#define PROP_MR_ASPECT_OFFSET    0xc1bc0
#define FILE_SIZE                1235740

__attribute__((constructor))
void do_backup_patch(void) {
    printf("=====================================================\n");
    printf(" Sony ZV-E10 NVRAM Native 3:2 Open Gate Patcher (v1.0)\n");
    printf("=====================================================\n");

    int fd = open(BACKUP_PATH, O_RDONLY);
    if (fd < 0) {
        printf("[-] Failed to open %s\n", BACKUP_PATH);
        return;
    }

    unsigned char* buf = (unsigned char*)malloc(FILE_SIZE);
    if (!buf) {
        printf("[-] Failed to allocate %d bytes\n", FILE_SIZE);
        close(fd);
        return;
    }

    int bytes_read = 0;
    while (bytes_read < FILE_SIZE) {
        int r = read(fd, buf + bytes_read, FILE_SIZE - bytes_read);
        if (r <= 0) break;
        bytes_read += r;
    }
    close(fd);

    if (bytes_read != FILE_SIZE) {
        printf("[-] Incomplete read: %d of %d bytes\n", bytes_read, FILE_SIZE);
        free(buf);
        return;
    }

    if (memcmp(buf + 0x0c, "BK4", 3) != 0) {
        printf("[-] Invalid header! Expected BK4 magic.\n");
        free(buf);
        return;
    }
    printf("[+] Validated BK4 database header.\n");

    /* Create .orig backup if not already present */
    int fd_orig_check = open(BACKUP_ORIG, O_RDONLY);
    if (fd_orig_check < 0) {
        int fd_orig = open(BACKUP_ORIG, O_WRONLY | O_CREAT | O_TRUNC, 0666);
        if (fd_orig >= 0) {
            write(fd_orig, buf, FILE_SIZE);
            close(fd_orig);
            printf("[+] Created pristine backup: %s\n", BACKUP_ORIG);
        }
    } else {
        close(fd_orig_check);
        printf("[*] Backup already exists at %s\n", BACKUP_ORIG);
    }

    printf("[*] Current 0x1070012 value: 0x%02x\n", buf[PROP_MOVIE_ASPECT_OFFSET]);

    /* Patch 0x1070012 to 0x02 (3:2) */
    buf[PROP_MOVIE_ASPECT_OFFSET] = 0x02;
    buf[PROP_MOVIE_ASPECT_OFFSET + 1] = 0x02;

    /* Patch 0x10703b2 (MR mode slots) to 0x02 */
    buf[PROP_MR_ASPECT_OFFSET] = 0x02;
    buf[PROP_MR_ASPECT_OFFSET + 1] = 0x02;
    buf[PROP_MR_ASPECT_OFFSET + 2] = 0x02;
    buf[PROP_MR_ASPECT_OFFSET + 3] = 0x02;
    buf[PROP_MR_ASPECT_OFFSET + 4] = 0x02;

    printf("[+] Patched 0x1070012 -> 0x02 (3:2 Open Gate)\n");
    printf("[+] Patched 0x10703b2 -> 0x02 0x02 0x02 0x02 (3:2 MR Slots)\n");

    /* Recompute Checksum */
    unsigned int dataOffset = *(unsigned int*)(buf + 0x18);
    unsigned int dataSize   = *(unsigned int*)(buf + 0x1c);
    unsigned int totalSize  = dataOffset + dataSize;
    if (totalSize > FILE_SIZE) totalSize = FILE_SIZE;

    unsigned int csum = 0;
    for (unsigned int i = 0; i < totalSize; i++) {
        if (i < 0x20 || i >= 0x24) {
            csum += buf[i];
        }
    }
    *(unsigned int*)(buf + 0x20) = csum;
    printf("[+] Computed new NVRAM checksum: 0x%08x\n", csum);

    /* Write back to Backup.bin */
    int fd_out = open(BACKUP_PATH, O_WRONLY | O_TRUNC);
    if (fd_out < 0) {
        printf("[-] Failed to open %s for writing\n", BACKUP_PATH);
        free(buf);
        return;
    }
    write(fd_out, buf, FILE_SIZE);
    close(fd_out);
    printf("[+] Successfully written to %s\n", BACKUP_PATH);

    /* Update mirror Backup.bak */
    int fd_bak = open(BACKUP_MIRROR, O_WRONLY | O_TRUNC);
    if (fd_bak >= 0) {
        write(fd_bak, buf, FILE_SIZE);
        close(fd_bak);
        printf("[+] Successfully updated mirror %s\n", BACKUP_MIRROR);
    }

    sync();
    printf("=====================================================\n");
    printf(" [+] NVRAM 3:2 OPEN GATE PERMANENT UPDATE COMPLETE!\n");
    printf("=====================================================\n");

    free(buf);
}
