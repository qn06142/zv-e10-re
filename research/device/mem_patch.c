#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>

#define PTRACE_PEEKTEXT   1
#define PTRACE_PEEKDATA   2
#define PTRACE_POKETEXT   4
#define PTRACE_POKEDATA   5
#define PTRACE_ATTACH    16
#define PTRACE_DETACH    17

extern int *__errno_location(void);
#define errno (*__errno_location())

extern long ptrace(int request, int pid, void *addr, void *data);
extern int waitpid(int pid, int *status, int options);

int main(int argc, char** argv) {
    if (argc < 4) {
        printf("Usage: mem_patch <pid> <hex_addr> <hex_bytes>\n");
        return 1;
    }
    int pid = atoi(argv[1]);
    unsigned long addr = strtoul(argv[2], NULL, 16);
    char* hex = argv[3];
    int len = strlen(hex) / 2;
    unsigned char* bytes = (unsigned char*)malloc(len);
    for (int i = 0; i < len; i++) {
        unsigned int b = 0;
        sscanf(&hex[i * 2], "%02x", &b);
        bytes[i] = (unsigned char)b;
    }

    printf("[*] Target PID: %d, Addr: 0x%08lx, Length: %d bytes\n", pid, addr, len);

    /* 1. Try direct write to /proc/<pid>/mem */
    char mempath[64];
    snprintf(mempath, sizeof(mempath), "/proc/%d/mem", pid);
    int fd = open(mempath, O_RDWR);
    int wrote = -1;
    if (fd >= 0) {
        if (lseek(fd, (off_t)addr, SEEK_SET) == (off_t)addr) {
            wrote = write(fd, bytes, len);
        }
        close(fd);
    }

    if (wrote == len) {
        printf("[+] Direct write to /proc/%d/mem succeeded!\n", pid);
    } else {
        printf("[-] Direct write returned %d (errno=%d), falling back to ptrace...\n", wrote, errno);

        if (ptrace(PTRACE_ATTACH, pid, NULL, NULL) < 0) {
            perror("ptrace attach");
            return 2;
        }
        int status = 0;
        waitpid(pid, &status, 0);

        for (int i = 0; i < len; i += 4) {
            unsigned long word_addr = (addr + i) & ~3UL;
            long val = ptrace(PTRACE_PEEKTEXT, pid, (void*)word_addr, NULL);
            unsigned char* pval = (unsigned char*)&val;
            for (int j = 0; j < 4 && (i + j) < len; j++) {
                int offset_in_word = (addr + i + j) - word_addr;
                pval[offset_in_word] = bytes[i + j];
            }
            if (ptrace(PTRACE_POKETEXT, pid, (void*)word_addr, (void*)val) < 0) {
                perror("ptrace poketext");
            }
        }

        ptrace(PTRACE_DETACH, pid, NULL, NULL);
        printf("[+] ptrace poke complete.\n");
    }

    /* Verification read */
    fd = open(mempath, O_RDONLY);
    if (fd >= 0) {
        unsigned char verify[32];
        int vlen = len > 32 ? 32 : len;
        lseek(fd, (off_t)addr, SEEK_SET);
        int r = read(fd, verify, vlen);
        close(fd);
        printf("[*] Verification read at 0x%08lx: ", addr);
        for (int i = 0; i < vlen; i++) {
            printf("%02x ", verify[i]);
        }
        printf("\n");
        if (r >= len && memcmp(bytes, verify, len) == 0) {
            printf("[+] VERIFICATION SUCCESS: Memory matches patch!\n");
        } else {
            printf("[-] VERIFICATION FAILED: Memory does not match!\n");
        }
    }
    return 0;
}
