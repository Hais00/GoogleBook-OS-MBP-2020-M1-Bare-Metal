// SPDX-License-Identifier: Apache-2.0
// Test fixture setup: request real Binder devices from this VM's kernel.
#include <linux/android/binderfs.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>
#include <string.h>
int main(void) {
    if (access("/GOS_LOCAL_AUDIO_TEST", F_OK) || access("/dev/snd", F_OK) == 0) return 1;
    int fd = open("/dev/binderfs/binder-control", O_RDWR | O_CLOEXEC);
    if (fd < 0) { perror("binder-control"); return 1; }
    const char* names[] = {"binder", "hwbinder", "vndbinder"};
    for (unsigned i = 0; i < sizeof(names)/sizeof(names[0]); ++i) {
        struct binderfs_device dev = {0};
        strcpy(dev.name, names[i]);
        char path[64]; snprintf(path, sizeof(path), "/dev/%s", names[i]);
        char target[64]; snprintf(target, sizeof(target), "binderfs/%s", names[i]);
        char absolute[80]; snprintf(absolute, sizeof(absolute), "/dev/%s", target);
        struct stat info;
        if (stat(absolute, &info) == 0 && S_ISCHR(info.st_mode)) {
            dev.major = major(info.st_rdev); dev.minor = minor(info.st_rdev);
        } else if (ioctl(fd, BINDER_CTL_ADD, &dev)) {
            perror("BINDER_CTL_ADD"); close(fd); return 1;
        }
        if (symlink(target, path)) { perror("binder symlink"); close(fd); return 1; }
        printf("LOCAL_REAL_KERNEL_BINDER_DEVICE=%s %u:%u\n", dev.name, dev.major, dev.minor);
    }
    close(fd); return 0;
}
