# Native GPU queue priorities

This change coordinates the Asahi kernel driver and Mesa Honeykrisp. It is a local port extension, not a feature attributed to the upstream releases.

## Reproduced failure

The Vulkan driver advertised LOW, MEDIUM, HIGH, and REALTIME priorities but unconditionally rejected HIGH and REALTIME. The kernel also rejected those priorities with EINVAL and carried a TODO for CAP_SYS_NICE authorization. SurfaceFlinger selected REALTIME, received VK_ERROR_NOT_PERMITTED from vkCreateDevice, and restarted.

AHardwareBuffer support and the availability of two queues did not resolve this mismatch between advertised capabilities and queue creation.

## Authorization and discovery

`DRM_ASAHI_FEATURE_PRIVILEGED_PRIORITY`, bit 1 of the Asahi parameters, is **a local ABI extension at the recorded kernel/Mesa revisions**. Its bit assignment must be reconciled with upstream before rebasing onto other versions.

GET_PARAMS sets the bit only when `capable(CAP_SYS_NICE)` authorizes the current caller in the initial user namespace and under the LSM policy. It reports an authorization snapshot, not a permission transferred by a file descriptor. QUEUE_CREATE rechecks current credentials for every HIGH/REALTIME request and returns EACCES when authorization is absent. Out-of-range priorities remain EINVAL.

Mesa exposes HIGH/REALTIME only on the direct DRM path when the kernel reports that bit. Older kernels and unauthorized callers expose LOW/MEDIUM. The virtio transport remains limited to LOW/MEDIUM pending a verified authorization contract for that transport. Single-queue debug mode rejects reuse of a cached queue with a different priority.

Requests retain their actual priority through native queue creation. EACCES and EPERM map to VK_ERROR_NOT_PERMITTED; other creation failures remain errors. A requested priority is not silently downgraded to obtain a successful return value.

| Vulkan priority | DRM value | AGX firmware class |
| --- | --- | --- |
| LOW | 0 | 3 |
| MEDIUM | 1 | 2 |
| HIGH | 2 | 1 |
| REALTIME | 3 | 0 |

These are scheduling classes. REALTIME does not guarantee hard deadlines or complete compute preemption that upstream leaves disabled in some paths.

## Implementation

- **Kernel:** `sources/linux-asahi/drivers/gpu/drm/asahi/file.rs` and the corresponding UAPI header.
- **Mesa:** `sources/mesa/src/asahi/vulkan/hk_queue.c`, `hk_physical_device.c`, `agx_device.c/.h`, and the coordinated UAPI header.
- **Probes:** `scripts/asahi_priority_permissions_probe.c`, `scripts/vulkan_priority_probe.c`, and `scripts/vulkan_android_interop_probe.c`.

SurfaceFlinger already held CAP_SYS_NICE in the observed session. This implementation requires no additional application privileges, permissive SELinux domains, or m1n1 changes.

## Validation

Kernel25 and Mesa built successfully. Their artifacts and local validation are recorded in `tests/results/local-2026-10-17.json`. Kernel25 read and checked the entire compressed vendor filesystem in a VM.

The previous-kernel M1 negative control created actual LOW/MEDIUM queues and returned EINVAL for HIGH/REALTIME. The Vulkan probe reproduced advertisement of four priorities and rejection of the upper two. Public extracts contain probe output only, not complete UART captures.

**The new implementation has not been loaded on M1.** Hardware testing was suspended at the owner’s request. Outstanding checks include new-kernel EACCES enforcement, authorized elevated queue creation, SurfaceFlinger Vulkan execution, multi-client progress and stability, and capability revocation after discovery. Successful compilation does not establish those results.
