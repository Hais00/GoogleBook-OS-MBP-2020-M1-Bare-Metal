# Validation status

**Recorded: 17 October 2026.** Hardware results apply to the identified historical builds. The new kernel25/Mesa priority pair has only been validated locally.

## Observed on M1

Android completed boot with SELinux Enforcing. Wi-Fi connected to a network. The device owner confirmed Bluetooth headphone playback and, after the primary ALSA corrections, playback through the internal speakers. Touch Bar operation and the icon distortion correction were also confirmed.

The preceding Vulkan driver passed AHardwareBuffer import/export, four swapchain frames, and eight dependency sequences across two native queues. Settings used Skia Vulkan and rendered 97 frames, with visual confirmation from the owner. Those results do not validate the subsequent priority build.

Enabling Vulkan for SurfaceFlinger exposed a priority advertised by the driver but rejected during queue creation. The debug session’s compositor was temporarily returned to OpenGL. The source correction now changes both the kernel and Mesa.

## Local validation of the new build

- Kernel25 and the updated Honeykrisp driver built successfully.
- Kernel and Mesa UAPI headers match. The GPU source changes were checked against the build inputs; aggregate patches were applied to clean upstream files and compared with the published snapshots.
- The new vendor filesystem contains **3,385 entries**, including **2,801 regular files** checked by hash. Ownership, modes, file types, symlinks, and security attributes were verified.
- Kernel25 read and verified every file in the compressed vendor filesystem in a VM.
- The kernel configuration and DTB retain the preceding profile’s identities. Relative to vendor18, vendor19 changes only the Vulkan library and integration manifest.

**Hardware testing is suspended at the owner’s request. The new kernel25/Mesa pair has not been installed or validated on M1.** The active session was not rebooted to test it.

## Outstanding work

- Validate new-kernel priority permissions, capability revocation, elevated queue creation, GPU execution, and progress under concurrent clients.
- Validate SurfaceFlinger and application stability with the new pair.
- Integrate a stateless V4L2 Request Codec2 adapter for AVD; the observed Android codec inventory still selects software components.
- Implement a hardware encoder backend.
- Extend speaker DSP, volume, and thermal-duration validation; integrate Android’s per-keyboard backlight control; validate other untested features.
- Validate direct boot without the debug hypervisor and consolidate a reproducible full-distribution build.

Selected reports publish artifact hashes and test scope without private logs. Vulkan CTS conformance and Android certification are not claimed.
