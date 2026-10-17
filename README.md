# GoogleBook OS MBP 2020 M1 Bare-Metal

Experimental Android bring-up for the **2020 13-inch MacBook Pro with Apple M1 — MacBookPro17,1 / J293 / t8103**. The port uses native Apple/Asahi drivers and Android integration code for graphics, input, wireless connectivity, and audio.

This repository publishes the port implementations, upstream patches, engineering notes, and selected validation results. **Recorded hardware sessions used the m1n1 debug hypervisor to retain a USB virtual UART. Direct boot without that debug layer has not been validated.** “Bare-Metal” describes the project objective; it is not a claim that the current boot chain runs without a hypervisor.

## Project status

Status as of **17 October 2026**. Results apply to the builds identified in the reports; they do not automatically validate later revisions.

| Component | Validation status |
| --- | --- |
| Android boot | Completed boot and displayed the interface on J293 using an Asahi kernel with 16 KiB pages, under m1n1 debug sessions. |
| Display and OpenGL | Native DRM/HWC, gralloc, and Mesa Asahi paths exercised on the device. |
| Application Vulkan | Honeykrisp passed AHardwareBuffer import/export, eight dependency sequences across two native queues, and four swapchain frames on M1. Settings rendered 97 Skia Vulkan frames; text and icons were visually confirmed. |
| SurfaceFlinger Vulkan | Enabling Vulkan exposed a queue-priority mismatch. The kernel/Mesa correction builds and passes local checks; **the new pair has not been tested on M1**. |
| Wi-Fi | Network connection confirmed on the device. |
| Bluetooth audio | Headphone playback confirmed by the device owner. The integration also depends on audio components supplied by the original Android image. |
| Internal speakers | Playback confirmed with the native ALSA/AIDL service, four physical channels at 48 kHz, and speakersafetyd protection. The digital peak limit remains 0.125; the complete DSP chain and extended thermal operation are not validated. |
| Keyboard and Touch Bar | LED/PWM, ADP, and uinput paths implemented. Touch Bar operation and the icon rendering correction were confirmed. Android’s per-keyboard backlight slider remains a separate integration task. |
| Hardware video codecs | The AVD decoder driver builds and video/media nodes were registered. Android still selects software `c2.android.*` codecs. A stateless V4L2 Request Codec2 adapter and a hardware encoder backend remain outstanding. |

Hardware testing is currently suspended at the device owner’s request. See [Validation status](docs/status.md) for the scope of completed checks and remaining work.

## Recorded boot architecture

```text
Apple boot chain
  → original m1n1 USB proxy
  → m1n1 debug hypervisor with virtual UART
  → Asahi Linux kernel and initramfs loaded into RAM
  → bootstrap and Android partitions on internal NVMe
  → Android init, HAL services, and user interface
```

The development updater verifies the current partition metadata and the rollback copy of any inactive extent selected for reuse. It then writes and reads back the selected payload before updating and checking all four liblp metadata copies. Relevant implementations include [`build_ram_bootstrap.py`](scripts/build_ram_bootstrap.py) and [`m1_ram_image_update.py`](scripts/m1_ram_image_update.py).

Published recipes use schematic `/opt/googlebook/...` paths and example partition UUIDs. Mappings for unnamed `super`, `metadata`, and `userdata` partitions require installation-specific configuration. Private device/UART reservation tooling, backups, and complete session captures are outside this release.

## Implementation overview

- **Kernel integration:** Apple platform profile, 16 KiB pages, Binder and Android dependencies, memfd/ashmem compatibility, Linux partition-name mapping without rewriting GPT, DRM fence fixes, macOS build compatibility, and ADP scanout allocation/pitch correction.
- **Android graphics:** minigbm and drm-hwcomposer adapted to the actual DRM devices, with separate main-display and Touch Bar ownership. Mesa Asahi provides OpenGL; Honeykrisp adds Android native-buffer/AHardwareBuffer integration and presentation synchronization.
- **Vulkan queues:** distinct native queues and submission workers, with real dependencies resolved before taking the shared-heap lock. GPU execution remains serialized to protect shared resources; parallel GPU execution is not claimed.
- **Vulkan priorities:** capability-checked kernel support, caller-scoped discovery, native priority forwarding, and owner-error propagation. See [GPU queue priorities](docs/gpu-priorities.md).
- **Android services:** targeted replacement or removal of Qualcomm-specific paths, Linux wireless/USB integration, and corresponding VINTF and SELinux changes. The reported M1 validation sessions used SELinux Enforcing.
- **Input:** AOSP-compatible Lights service, ADP Touch Bar rendering, uinput events, multitouch state handling, layout transitions, and page-flip completion tracking.
- **Audio:** primary AIDL/ALSA module, AppleJ293 routing at 48 kHz, four-channel mapping, FIR processing, and speaker protection interlocks. Subsequent fixes cover the AIDL port address, XRUN recovery, pause/flush behavior, and observed presentation positions.
- **Debug transport:** m1n1 host-side pipe ownership and 9P EOF handling, preventing indefinite waits when the exporter is rejected.
- **OEM framework:** limited early bring-up adaptations documented in the historical notes. Modified proprietary JARs and other binaries are excluded.
- **AVD preparation:** open-source Asahi firmware build support and a Cortex-M3 linker correction that places the vector table at address zero. Android Codec2 integration is still required.

Software/non-secure KeyMint and Gatekeeper components are bring-up facilities. Their presence does not establish Apple hardware-backed security or Android certification.

## Repository layout

| Path | Contents |
| --- | --- |
| [`sources/`](sources/) | Snapshots of modified upstream files: Linux, Mesa, minigbm, drm-hwcomposer, ALSA, speakersafetyd, and m1n1 host transport. |
| [`scripts/`](scripts/) | Local C/C++ implementations, build/staging recipes, helpers, and tests. |
| [`patches/`](patches/README.md) | Aggregate and focused patches against recorded upstream commits. |
| [`upstream/`](.gitmodules) | Git submodule references to complete upstream repositories at explicit revisions. |
| [`config/kernel25.config`](config/kernel25.config) | Configuration used for the locally built kernel25 artifact. |
| [`manifests/`](manifests/) | Source revisions, hashes, license headers, and publication adjustments. |
| [`docs/`](docs/README.md) | Current technical documentation and historical engineering reports. |
| [`tests/`](tests/README.md) | Validation scope and selected results. |

## Build and distribution scope

This is a source release, not an installable Android distribution. Dependency setup and the historical build recipes have not yet been consolidated into an exact, reproducible full-image build. Complete upstream sources can be fetched with `git submodule update --init`; the kernel repository has a substantial history.

A compatible Android base image and device firmware must be obtained separately. Android/Google binaries, Apple firmware, compiled artifacts, keys, credentials, backups, and private UART captures are not included. The Google Rust desktop audio HAL remains an external binary dependency of the tested image; its implementation is not reproduced here.

## Licensing

Original port glue and documentation are covered by [LICENSE](LICENSE), except where a file specifies or inherits an upstream license. Derived components retain their original terms, including the kernel’s and speakersafetyd’s GPL obligations. See [Third-party notices](THIRD_PARTY_NOTICES.md), component COPYING files, and [`LICENSES/`](LICENSES/).
