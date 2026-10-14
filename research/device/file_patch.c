#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>

int main(int argc, char** argv) {
    if (argc < 4) {
        printf("Usage: file_patch <filepath> <hex_offset> <hex_bytes>\n");
        return 1;
    }
    const char* path = argv[1];
    unsigned long offset = strtoul(argv[2], NULL, 16);
    const char* hex = argv[3];
    int len = strlen(hex) / 2;
    unsigned char* bytes = (unsigned char*)malloc(len);
    for (int i = 0; i < len; i++) {
        unsigned int b = 0;
        sscanf(&hex[i * 2], "%02x", &b);
        bytes[i] = (unsigned char)b;
    }

    int fd = open(path, O_RDWR);
    if (fd < 0) {
        perror("open failed");
        free(bytes);
        return 2;
    }
    if (lseek(fd, (off_t)offset, SEEK_SET) != (off_t)offset) {
        perror("lseek failed");
        close(fd);
        free(bytes);
        return 3;
    }
    int wrote = write(fd, bytes, len);
    if (wrote != len) {
        perror("write failed");
        close(fd);
        free(bytes);
        return 4;
    }
    fsync(fd);

    /* Verify write */
    lseek(fd, (off_t)offset, SEEK_SET);
    unsigned char* verify = (unsigned char*)malloc(len);
    int r = read(fd, verify, len);
    close(fd);

    if (r == len && memcmp(bytes, verify, len) == 0) {
        printf("[+] VERIFICATION SUCCESS: %s @ 0x%08lx patched (%d bytes)\n", path, offset, len);
        free(bytes);
        free(verify);
        return 0;
    } else {
        printf("[-] VERIFICATION FAILED for %s @ 0x%08lx\n", path, offset);
        free(bytes);
        free(verify);
        return 5;
    }
}
