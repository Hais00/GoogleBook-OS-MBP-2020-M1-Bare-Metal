// Exercise the real kernel filesystems required by Android's early init.
#include <errno.h>
#include <fcntl.h>
#include <linux/loop.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/ioctl.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>

static void done(int failed, const char *step) {
    printf("SELINUX_SMOKE_%s: %s (errno=%d %s)\n",
           failed ? "FAIL" : "PASS", step, failed ? errno : 0,
           failed ? strerror(errno) : "OK");
    fflush(stdout);
    sync();
    reboot(RB_POWER_OFF);
    for (;;) pause();
}

static void must_mount(const char *type, const char *target) {
    mkdir(target, 0755);
    if (mount(type, target, type, 0, NULL)) done(1, target);
}

static void write_control(const char *path, const char *value) {
    int fd = open(path, O_WRONLY);
    if (fd < 0 || write(fd, value, strlen(value)) != (ssize_t)strlen(value))
        done(1, path);
    close(fd);
}

static void cpuset_and_logging(void) {
    mkdir("/dev/cpuset", 0755);
    if (mount("cpuset", "/dev/cpuset", "cgroup", 0, "cpuset"))
        done(1, "mount legacy cpuset v1");
    if (mkdir("/dev/cpuset/smoke", 0755)) done(1, "create cpuset");
    write_control("/dev/cpuset/smoke/cpuset.mems", "0");
    write_control("/dev/cpuset/smoke/cpuset.cpus", "0");
    char pid[32];
    snprintf(pid, sizeof(pid), "%d", getpid());
    write_control("/dev/cpuset/smoke/tasks", pid);
    write_control("/dev/cpuset/tasks", pid);
    if (rmdir("/dev/cpuset/smoke")) done(1, "remove cpuset");
    printf("CPUSET_V1_SMOKE_PASS: mounted and moved a task into a legacy cpuset\n");

    if (mknod("/dev/kmsg", S_IFCHR | 0600, makedev(1, 11)) && errno != EEXIST)
        done(1, "create kernel message device");
    int out = open("/dev/kmsg", O_WRONLY);
    int in = open("/dev/kmsg", O_RDONLY | O_NONBLOCK);
    if (out < 0 || in < 0) done(1, "open kernel message ring");
    for (int i = 0; i < 100; i++) {
        char message[80];
        int n = snprintf(message, sizeof(message), "<6>GOS_KMSG_BURST_%03d\n", i);
        if (write(out, message, n) != n) done(1, "write kernel message burst");
    }
    close(out);
    int count = 0;
    char record[8192];
    for (;;) {
        ssize_t n = read(in, record, sizeof(record)-1);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0 && errno == EAGAIN) break;
        if (n <= 0) done(1, "read kernel message burst");
        record[n] = 0;
        if (strstr(record, "GOS_KMSG_BURST_")) count++;
    }
    close(in);
    if (count != 100) done(1, "kernel message burst was rate limited");
    printf("DEVKMSG_SMOKE_PASS: all 100 userspace messages retained\n");
}

static void quota_filesystem(void) {
    if (mknod("/dev/loop0", S_IFBLK | 0600, makedev(7, 0)) && errno != EEXIST)
        done(1, "create quota loop device");
    int image = open("/quota.img", O_RDWR);
    int loop = open("/dev/loop0", O_RDWR);
    if (image < 0 || loop < 0 || ioctl(loop, LOOP_SET_FD, image))
        done(1, "attach quota filesystem loop");
    mkdir("/quota-mount", 0755);
    if (mount("/dev/loop0", "/quota-mount", "ext4", 0, NULL))
        done(1, "mount ext4 with quota feature");
    int probe = open("/quota-mount/probe", O_CREAT | O_WRONLY, 0600);
    if (probe < 0) done(1, "create file on quota filesystem");
    close(probe);
    write_control("/quota-mount/probe", "android quota mount writes work");
    if (access("/sys/fs/ext4/features/encryption", R_OK) ||
        access("/sys/fs/ext4/features/verity", R_OK) ||
        access("/sys/fs/ext4/features/casefold", R_OK))
        done(1, "ext4 Android encryption/verity/casefold features");
    sync();
    if (umount("/quota-mount") || ioctl(loop, LOOP_CLR_FD, 0))
        done(1, "detach quota filesystem");
    close(image); close(loop);
    printf("EXT4_QUOTA_SMOKE_PASS: mounted quota filesystem writable; Android features available\n");
}

int main(int argc, char **argv) {
    must_mount("proc", "/proc");
    must_mount("sysfs", "/sys");
    must_mount("securityfs", "/sys/kernel/security");
    must_mount("selinuxfs", "/sys/fs/selinux");
    must_mount("binder", "/dev/binderfs");
    cpuset_and_logging();
    quota_filesystem();
    char buf[512] = {0};
    int fd = open("/sys/kernel/security/lsm", O_RDONLY);
    if (fd < 0) done(1, "read active LSMs");
    ssize_t n = read(fd, buf, sizeof(buf)-1); close(fd);
    if (n < 0 || !strstr(buf, "selinux")) done(1, "SELinux absent from active LSM list");
    printf("Active LSMs: %s\n", buf);
    memset(buf, 0, sizeof(buf));
    fd = open("/sys/fs/selinux/enforce", O_RDONLY);
    if (fd < 0 || read(fd, buf, sizeof(buf)-1) < 1) done(1, "read enforcing state");
    close(fd); printf("Enforcing state: %s\n", buf);
    if (argc > 1 && !strcmp(argv[1], "--policy")) {
        fd = open("/policy", O_RDONLY);
        struct stat st;
        if (fd < 0 || fstat(fd, &st)) done(1, "read Android policy");
        char *data = malloc(st.st_size);
        if (!data) done(1, "policy buffer");
        ssize_t total = 0;
        while (total < st.st_size) {
            n = read(fd, data+total, st.st_size-total);
            if (n <= 0) done(1, "read full policy");
            total += n;
        }
        close(fd); fd = open("/sys/fs/selinux/load", O_WRONLY);
        if (fd < 0 || write(fd, data, total) != total) done(1, "load original Android policy");
        close(fd); free(data);
        done(0, "SELinux/Binder mounted; original Android policy loaded");
    }
    if (buf[0] != '1') done(1, "expected enforcing=1");
    done(0, "SELinux/Binder mounted with enforcing=1");
}
