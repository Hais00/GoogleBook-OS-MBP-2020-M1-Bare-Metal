// SPDX-License-Identifier: Apache-2.0
// Load the unchanged saved policy into this CPU-only VM in one kernel write.
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>
int main(void) {
    if (access("/GOS_LOCAL_AUDIO_TEST", F_OK) || access("/dev/snd", F_OK) == 0) return 1;
    int in = open("/cpu-fixture-policy.bin", O_RDONLY);
    struct stat info;
    if (in < 0 || fstat(in, &info) || info.st_size < 1 || info.st_size > 8388608) return 1;
    void* data = malloc(info.st_size);
    if (!data) return 1;
    ssize_t pos = 0;
    while (pos < info.st_size) {
        ssize_t n = read(in, (char*)data + pos, info.st_size - pos);
        if (n <= 0) return 1;
        pos += n;
    }
    close(in);
    int out = open("/sys/fs/selinux/load", O_WRONLY);
    if (out < 0 || write(out, data, info.st_size) != info.st_size) {
        perror("load real saved SELinux policy"); return 1;
    }
    close(out); free(data);
    puts("LOCAL_UNCHANGED_POLICY_LOADED_PERMISSIVE_CPU_FIXTURE_ONLY");
    return 0;
}
