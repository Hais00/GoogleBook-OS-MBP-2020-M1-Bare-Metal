/* Query the actual Android label matcher and active SELinux access decisions. */
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <selinux/label.h>
#include <selinux/selinux.h>
#include <sys/stat.h>

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    struct selinux_opt opts[] = {{ SELABEL_OPT_PATH, argv[1] }};
    struct selabel_handle *handle = selabel_open(SELABEL_CTX_FILE, opts, 1);
    if (!handle) { perror("selabel_open"); return 1; }
    const char *nodes[] = {"/dev/dri/card0", "/dev/dri/card1", "/dev/dri/card3",
                         "/dev/dri/card137", "/dev/dri/renderD128", "/dev/dri/renderD130"};
    unsigned failures = 0;
    for (unsigned i = 0; i < sizeof(nodes)/sizeof(nodes[0]); ++i) {
        char *label = NULL;
        int rc = selabel_lookup(handle, &label, nodes[i], S_IFCHR);
        printf("GOS_DRM_LABEL %s %s\n", nodes[i], label ? label : "LOOKUP_FAILED");
        if (rc || !label || strcmp(label, "u:object_r:gpu_device:s0")) ++failures;
        if (label) freecon(label);
    }
    selabel_close(handle);
    const char *domains[] = {"surfaceflinger", "gpuservice", "hal_graphics_allocator_default",
                            "hal_graphics_composer_default", "shell"};
    for (unsigned i = 0; i < sizeof(domains)/sizeof(domains[0]); ++i) {
        char from[160];
        snprintf(from, sizeof(from), "u:r:%s:s0", domains[i]);
        errno = 0;
        int rc = selinux_check_access(from, "u:object_r:sysfs_gpu:s0", "file", "read", NULL);
        printf("GOS_GPU_POLICY %s sysfs_gpu:file read=%s errno=%d\n",
               domains[i], rc ? "DENIED" : "ALLOWED", errno);
        if (rc) ++failures;
        if (strcmp(domains[i], "shell")) {
            const char *perms[] = {"getattr", "open", "read", "write", "ioctl"};
            for (unsigned j = 0; j < sizeof(perms)/sizeof(perms[0]); ++j) {
                rc = selinux_check_access(from, "u:object_r:gpu_device:s0", "chr_file", perms[j], NULL);
                printf("GOS_GPU_POLICY %s gpu_device:chr_file %s=%s\n",
                       domains[i], perms[j], rc ? "DENIED" : "ALLOWED");
                if (rc) ++failures;
            }
        }
    }
    printf("GOS_GRAPHICS_POLICY_%s failures=%u\n", failures ? "FAIL" : "PASS", failures);
    return failures ? 1 : 0;
}
