# Android boot integration on J293

## Boot and storage

m1n1 transfers the kernel and initramfs into RAM. Android uses its partitions on internal NVMe. The Linux profile retains the required Apple drivers, disables unrelated platform components, and uses 16 KiB pages.

The original installation contained GPT partitions without the names required by Android. The port assigns `super`, `metadata`, and `userdata` names during Linux partition discovery using explicit partition matches; it does not rename the on-disk GPT entries. The published UUIDs are examples and require installation-specific configuration.

The bootstrap transports firmware once and retains a manifest of the original payloads. The updater operates on the planned areas within `super`: it verifies the active layout, protects historical extents, requires a complete rollback copy before reusing an inactive extent, and verifies payloads and liblp metadata before continuing into Android.

The kernel also provides the memfd/ashmem behavior required by this userspace. Host build adaptations for macOS are separable from changes needed for operation on M1.

## Graphics and synchronization

Asahi/DRM controls the physical GPU. DCP handles the main display; ADP handles the Touch Bar display. minigbm and drm-hwcomposer are adapted to actual device discovery, buffer layout, and fence behavior. DRM CRTC fence lifetime and race fixes retain their upstream provenance.

Honeykrisp adds Android native-buffer/AHardwareBuffer import and the acquire/release path. Imports use observed layouts and strides; synchronization uses actual fence events. Two native queues use separate submission workers, while shared heaps are protected by observed GPU completion. The subsequent priority changes are documented in [GPU queue priorities](gpu-priorities.md).

## HAL services, input, and audio

The Android base product contained Qualcomm-specific services and paths that do not match Apple hardware. Staging recipes select the applicable components and install the local implementations. SELinux changes are targeted; the reported M1 sessions retained Enforcing mode.

Wi-Fi connects the Linux backend to the product HAL interface. Bluetooth connects the Linux controller transport and the audio factory already present in the image. The Lights service exposes the AOSP interface versions required by the actual compatibility matrix. Main-display, keyboard, and Touch Bar failures remain independent.

The Touch Bar daemon uses ADP, KMS buffers, and page-flip completion events with corrected rotation and pitch. It observes the actual touch device and emits uinput events, including explicit handling of multitouch slots, releases, layout transitions, and synchronization loss.

The primary audio service exposes a stereo PCM16 Android port at 48 kHz and drives the AppleJ293 S32_LE four-channel PCM. It preserves FIR processing, physical channel mapping, the digital peak limit, and the speaker interlock. speakersafetyd retains its thermal model and voltage/current monitoring. Fixes to the AIDL port address, XRUN recovery, and pause/flush/standby handling preceded the owner’s confirmation of speaker playback.

## Video and diagnostics

The open-source AVD firmware linker was corrected to place the Cortex-M3 vector table at address zero. The driver is available, but Android still selects software codecs because a stateless V4L2 Request Codec2 adapter has not been integrated. Hardware encoding remains unimplemented.

Debug sessions used the m1n1 hypervisor and its USB virtual UART. Initial output was captured before `/data` became available. Complete logcat output then moved to an on-device file, with timestamp overlap at logger transitions and SHA-256 verification during retrieval. Private captures and the physical-session coordinator are excluded from this source release.

The m1n1 host transport also closes inherited child-only pipe ends and detects EOF while reading 9P responses, allowing exporter rejection to be observed instead of leaving the parent waiting indefinitely.
