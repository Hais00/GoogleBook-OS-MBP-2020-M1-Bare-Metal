# Validation evidence

`results/local-2026-10-17.json` records actual local build and filesystem checks and selected earlier M1 results. Baseline probe extracts reproduce the old priority failure. The new kernel/Mesa priority pair has not been hardware tested.

Probe sources are in `scripts/`: `asahi_priority_permissions_probe.c` tests real owner ioctl results, including EACCES and invalid-priority EINVAL without GPU submissions; `vulkan_priority_probe.c` reproduces the compositor's advertised-maximum selection; `vulkan_android_interop_probe.c` verifies real GPU dependencies, AHardwareBuffer import/export and four native-window frames.

The original Vulkan priority probe is a strict baseline diagnostic: an unprivileged caller can legitimately receive NOT_PERMITTED for elevated priorities after discovery under other implementations. For this port the kernel reports caller-scoped availability, and the separate owner probe checks the actual permission boundary. No privileged result should be inferred from a shell-only run.

The historical tests include local dependencies not consolidated into a public test runner. Syntax and patch-application audits of this source export are recorded separately. No script in the release audit operates the M1.
