#define _GNU_SOURCE
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ptrace.h>
#include <sys/wait.h>
#include <unistd.h>

static pid_t wait_for(pid_t tid, int *status)
{
    pid_t result;
    do {
        result = waitpid(tid, status, __WALL);
    } while (result == -1 && errno == EINTR);
    return result;
}

static int snapshot(pid_t tid)
{
    /* ARM Linux PTRACE_GETREGS returns r0-r15, CPSR and orig_r0. */
    unsigned long regs[18];
    int status;

    if (ptrace(PTRACE_ATTACH, tid, 0, 0) == -1) {
        perror("PTRACE_ATTACH");
        return 1;
    }
    if (wait_for(tid, &status) == -1) {
        perror("waitpid");
        return 1;
    }
    if (!WIFSTOPPED(status)) {
        fputs("Thread exited before its registers could be read.\n", stderr);
        return 1;
    }

    int signal = WSTOPSIG(status);
    int result = ptrace(PTRACE_GETREGS, tid, 0, regs);
    int register_error = errno;
    if (ptrace(PTRACE_DETACH, tid, 0, signal == SIGSTOP ? 0 : signal) == -1) {
        perror("PTRACE_DETACH");
        return 1;
    }
    if (result == -1) {
        errno = register_error;
        perror("PTRACE_GETREGS");
        return 1;
    }

    printf("tid=%ld pc=%08lx sp=%08lx lr=%08lx cpsr=%08lx orig_r0=%08lx\n",
           (long)tid, regs[15], regs[13], regs[14], regs[16], regs[17]);
    for (int i = 0; i < 13; ++i)
        printf("r%d=%08lx%c", i, regs[i], i == 12 ? '\n' : ' ');
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "Usage: %s TID (briefly stops the target)\n", argv[0]);
        return 2;
    }

    char *end;
    errno = 0;
    long tid = strtol(argv[1], &end, 10);
    if (errno || end == argv[1] || *end || tid <= 1 || tid > INT_MAX || tid == getpid()) {
        fputs("Supply a valid target thread ID greater than 1.\n", stderr);
        return 2;
    }
    return snapshot((pid_t)tid);
}
