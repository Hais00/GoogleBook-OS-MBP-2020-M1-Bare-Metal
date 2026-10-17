// SPDX-License-Identifier: Apache-2.0
// Real owner-ioctl permission checks. Creates/destroys queues, submits no GPU work.
#include <drm-uapi/asahi_drm.h>
#include <linux/capability.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>

int main(void)
{
   setbuf(stdout, NULL);
   struct __user_cap_header_struct header = { .version = _LINUX_CAPABILITY_VERSION_3 };
   struct __user_cap_data_struct caps[2] = {{0}};
   if (syscall(__NR_capget, &header, caps)) return 2;
   int privileged = !!(caps[0].effective & (1u << CAP_SYS_NICE));
   int fd = -1;
   struct drm_asahi_params_global params = {0};
   for (unsigned i = 128; i < 192; i++) {
      char node[48];
      snprintf(node, sizeof(node), "/dev/dri/renderD%u", i);
      int candidate = open(node, O_RDWR | O_CLOEXEC);
      if (candidate < 0) continue;
      struct drm_asahi_get_params request = { .pointer = (uintptr_t)&params, .size = sizeof(params) };
      if (!ioctl(candidate, DRM_IOCTL_ASAHI_GET_PARAMS, &request) && params.chip_id == 0x8103) {
         fd = candidate; break;
      }
      close(candidate);
   }
   if (fd < 0) { puts("ASAHI_OWNER_PERMISSION_PROBE_NO_M1_RENDER_NODE"); return 2; }
   int advertised = !!(params.features & DRM_ASAHI_FEATURE_PRIVILEGED_PRIORITY);
   printf("ASAHI_OWNER_CAP_SYS_NICE=%d PRIVILEGED_PRIORITY_AVAILABLE=%d\n", privileged, advertised);
   if (privileged != advertised) { close(fd); return 3; }
   if (!params.vm_kernel_min_size || params.vm_end <= params.vm_start ||
       params.vm_kernel_min_size >= params.vm_end - params.vm_start ||
       params.vm_start > UINT64_MAX - 0xffffffffull) { close(fd); return 3; }
   struct drm_asahi_vm_create vm = { .kernel_start = params.vm_end - params.vm_kernel_min_size,
                                     .kernel_end = params.vm_end };
   uint64_t shader_base = (params.vm_start + 0xffffffffull) & ~0xffffffffull;
   if (shader_base >= vm.kernel_start || ioctl(fd, DRM_IOCTL_ASAHI_VM_CREATE, &vm)) { close(fd); return 3; }
   unsigned failures = 0;
   for (uint32_t priority = 0; priority <= 4; priority++) {
      struct drm_asahi_queue_create create = { .vm_id = vm.vm_id, .priority = priority,
                                               .usc_exec_base = shader_base };
      errno = 0;
      int result = ioctl(fd, DRM_IOCTL_ASAHI_QUEUE_CREATE, &create);
      int error = errno;
      printf("ASAHI_OWNER_REAL_QUEUE_CREATE priority=%u result=%d errno=%d native_queue=%u\n",
             priority, result, error, create.queue_id);
      if (priority > DRM_ASAHI_PRIORITY_REALTIME) {
         if (result != -1 || error != EINVAL) failures++;
      } else if (priority >= DRM_ASAHI_PRIORITY_HIGH && !privileged) {
         if (result != -1 || error != EACCES) failures++;
      } else if (result || !create.queue_id) {
         failures++;
      }
      if (!result) {
         struct drm_asahi_queue_destroy destroy = { .queue_id = create.queue_id };
         if (ioctl(fd, DRM_IOCTL_ASAHI_QUEUE_DESTROY, &destroy)) failures++;
      }
   }
   struct drm_asahi_vm_destroy destroy = { .vm_id = vm.vm_id };
   if (ioctl(fd, DRM_IOCTL_ASAHI_VM_DESTROY, &destroy)) failures++;
   close(fd);
   printf("ASAHI_OWNER_PRIORITY_PERMISSIONS_%s failures=%u GPU_SUBMISSIONS=0\n", failures ? "FAIL" : "PASS", failures);
   return failures ? 5 : 0;
}
