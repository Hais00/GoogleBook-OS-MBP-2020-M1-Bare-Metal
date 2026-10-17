# Bluetooth audio integration

**Historical checkpoints: 17 October 2026.** This report records the route from the initial Bluetooth configuration to the primary-output failure. Subsequent headphone and speaker results are documented in [Native primary audio integration](m1-native-primary-audio-20261017.md). See [current status](../status.md) for the project summary.

## Initial diagnosis

The original C++ `dras.core-cpp.audio` service was present in the audio APEX and already started on M1, but initially published only `IModule/r_submix`. Its software Bluetooth branch and configuration were disabled.

The original binary’s desktop `ModuleBluetooth` constructor obtains `com.android.desktop.audio.IDesktopAudioFactory/default` from the Rust process and registers the Bluetooth audio factory. This existing Binder relationship allows the image’s Rust software providers to be used without introducing a second, independent session owner.

## Configuration candidate

The candidate stage, `.agent-work/vendor-audio-stage`, was derived from the validated Wi-Fi vendor10 image. It enabled the software HFP branch needed by the C++ service to construct its Bluetooth module, disabled Qualcomm A2DP/LE offload, added external SCO ports and A2DP routes, normalized XML list syntax, and declared `IModule/bluetooth` V4 through init and VINTF.

`/dev/rfkill` was assigned to `bluetooth:bluetooth`, mode 0660, with the existing `bt_device` SELinux type. This stage added no allow rules or CIL changes.

No ELF payload changed relative to vendor10. The Google APEX remained unchanged. The installed Rust binary retained the earlier `libagmipcservice.so` to `libgosagmservice.so` adaptation; this stage did not extend it. `vendor.audio.dras.default_nothing=true` remained selected and did not provide a native internal-speaker HAL.

## Local Binder validation

The test used the production kernel23 in a VM with no physical disks, radios, or audio devices attached. Bionic, Binder, and the supplied audio processes ran directly.

- **Positive control:** four services were available: `IModule/default`, `IModule/a2dp`, `IDesktopAudioFactory/default`, and `IModule/r_submix`. The V6 factory exposed one software A2DP capability; a remote provider opened and answered a Binder ping.
- **Negative control:** disabling the software HFP branch left the same four services available but prevented Bluetooth factory registration.

These checks did not transfer PCM or validate the physical controller, pairing, headphones, microphone, HFP audio, or enforcing policy on M1. Only this isolated fixture used the saved Android policy in permissive mode with processes in the kernel context. Its programs and helpers were not added to the vendor stage.

Historical result references:

- `/opt/googlebook/external/googlebook-bringup-20261016/audio-software-local-runtime-r11/result.json`
- `/opt/googlebook/external/googlebook-bringup-20261016/audio-software-local-runtime-negative/result.json`

## Filesystem and installation checks

The final vendor11 candidate was built on ext4 in a disposable local virtual disk, using sequential archive input with `--sort=none`. Earlier packaging attempts, including a temporary 2 TiB sparse file on APFS and tmpfs-based builds, were not accepted for installation.

The final filesystem contained 3,273 entries and 2,699 regular files. Payloads, UID/GID, modes, types, symlink targets, and security attributes matched the archive. An initial scanner had observed an empty directory through a nonrecursive bind and was rejected as evidence; the explicit complete readback was used instead.

Artifact: `vendor-generation11-btaudio-r2.erofs`, 402,702,336 bytes, SHA-256 `e9cb0d86f4716b37ab0e506a152306b72fdeda5acb76c5a81428dea12b9c0b9e`.

The update plan preserved active vendor10. Reuse of inactive generation7 required a complete rollback archive and matching on-device digest before opening the target for writing. GPT, macOS, ESP, and userdata were outside the update scope. Planned M1 checks included full logs, Enforcing mode, rfkill access, controller state, factory version, pairing, routing, session behavior, and playback. Internal amplifier unlock remained dependent on Asahi protection.

## First M1 trial and HCI correction

Vendor11 installed with verified rollback archive, payload readback, and liblp commit. Android completed boot with SELinux Enforcing. `/dev/rfkill` had the intended ownership, mode, and type; the factory and `IModule/bluetooth` were present.

Bluetooth then terminated because the AOSP15 transport called `rfkill(1)` before binding HCI USER. The kernel returned `Operation not possible due to RF-kill`. This was an observed transport failure, not evidence of a defective radio.

AOSP revision `aa229558cbf04bc997ed27465c5e7ad497123d1b`, in `bluetooth/aidl/default/net_bluetooth_mgmt.cpp`, already contained the correction: `rfkill(0)` before binding and `rfkill(1)` after closing. The builder verified that only those calls and comments differed, retained the older header, and preserved the frozen Binder V1 interface. Error results were not converted into success.

Vendor12 changed only the HCI binary relative to vendor11:

| Artifact | Identity |
| --- | --- |
| HCI binary | SHA-256 `4e568427111954444798ba849e37ce23075f84de741b6c6ac7893e179d718bc0` |
| Vendor image | 402,702,336 bytes; SHA-256 `1716fccb526416830f11d047ed5db6fd3c042cc5d10cfbc015878adc1b900015` |

All 3,273 entries were compared, and kernel23 read every payload. The plan preserved vendor11 and Wi-Fi vendor10; inactive vendor9 was archived and checked before reuse. After the Android-requested reboot, the physical metadata prefix matched the expected state. RUN11 was sealed, and the preceding complete Wi-Fi log was also recovered: 48,074,752 bytes.

## Connected headphones and the primary-output failure

Vendor12 completed boot. Bluetooth remained ON without new crashes, HCI initialized, and the headphones connected through HEADSET and A2DP. Wi-Fi remained VALIDATED and SELinux remained Enforcing.

Playback was still unavailable. AudioPolicy reported `AudioPolicyManager: 0x0`; audioserver logged `The policy configuration does not declare a primary output`; the Rust service reported `Using nothing HAL`.

The legacy XML additions could not create a primary output inside the AIDL Nothing module. A real primary service with ALSA ports, routes, and streams was required. Pairing alone, or the reported 48 kHz speaker rate, could not establish playback.

Evidence references: `trial-native-btaudio-kernel23-v12-r3/audio-routing-diagnosis.json` and the complete `android-full-b21b2a7dac.log`, 16,003,072 bytes, SHA-256 `bc63646dd32b4b78cef84c3874f4408ce04910b55694369cbf04fe54efb784a7`. After retrieval, complete file logging resumed while kernel UART capture continued.

## Preparation of the native primary service

The subsequent local work established the dependencies for a separate native implementation:

- `build_m1_speakersafetyd.py` built the GPL Asahi protector for Bionic, retaining the model, V/I sensors, control ownership, and keepalive. Its boot-state flag moved from `/run` to an init-created `/dev/speakersafetyd` tmpfs directory.
- `test_m1_speaker_dependency_runtime.py` ran version/help under kernel23 and Bionic and rejected missing hardware before accessing controls. No physical audio device or disk was exposed; this was dependency validation, not thermal or playback validation.
- `fetch_m1_native_audio_references.py` and `build_m1_native_audio_abi.py` pinned AOSP sources and generated eight Binder libraries from frozen snapshots, including core V3 and common types V4. Original Google libraries and interface version/hash metadata were preserved.

At that checkpoint, the ALSA primary service, real PCM positions and drain behavior, J293 routing, protector init/SELinux integration, and hardware playback still remained to be implemented. The subsequent implementation and acoustic results are recorded in the [primary audio report](m1-native-primary-audio-20261017.md).
