# Native primary audio integration

**Historical checkpoints: 17 October 2026.** This report follows the native primary service from local validation through confirmed speaker playback. Current limitations remain summarized in [validation status](../status.md).

## Service and data path

The standalone `android.hardware.audio.core.IModule/m1` service implements the canonical frozen AOSP V3 interface, hash `eb5f1f5af402830af56b50eb66bdd60fd8cc774e`. Original Google services and libraries used by Bluetooth remain unchanged. Microphone, MMAP, offload, and other unimplemented paths are not advertised.

The service identifies the ALSA card as `AppleJ293`/`macaudio`, queries the PCM for S32_LE, four channels, and 48 kHz, applies the Secondary route defined by the Asahi UCM, and publishes a primary stereo PCM16 port at 48 kHz. This allows Android to construct a valid AudioPolicyManager and manage Bluetooth outputs as well.

AOSP Binder/FMQ workers feed actual ALSA writes. Nonblocking drain is requested once; repeating the request would append silence in the hardware plugin. Completion is rechecked through the kernel DRAINING → SETUP transition. Errors and timeouts remain errors. Presentation positions use submitted frames and ALSA delay; discarded frames are not counted as presented.

FIR processing maps stereo input to physical FL/FR/RL/RR channels using the J293 front/rear responses at 48 kHz. This integration limits digital peaks to **0.125, approximately −18 dBFS**. The complete PipeWire/LSP effects and compression chain has not been ported or validated, and original maximum-volume equivalence is not claimed.

## Speaker protection

`speakersafetyd` remains a separate GPL dependency with retained source, license, and patches. It uses the original J293 profile, eight PCM2 voltage/current channels, thermal model, control locks, and keepalive protocol. Android adaptations change the boot flag to `/dev/speakersafetyd` and use the direct sysfs path for the same device-tree `compatible` property.

The HAL does not write the unlock magic or amplifier gains. Before accepting client samples, it checks the actual kernel `Speaker Volume Unlock` control. When necessary, it starts the clock using silence within a timeout. Loss of the unlock closes the PCM and returns an error. The kernel’s original clamp remains in place.

SELinux policy adds specific labels for the compatible property and temporary flag, with targeted audio-domain access. No permissive target domain or audio-device DAC override was introduced. Wi-Fi and Touch Bar components were preserved.

## Initial local validation

Completed checks included:

- Bionic service/protector compilation, AArch64 ELF validation, and 16 KiB-compatible alignment.
- A kernel23 VM test using remote Binder V3, FMQ, and real ALSA loopback: 19,200 frames accepted and presented after drain, with four-channel sample comparison. Loopback belongs only to the CPU fixture.
- Protector version/help execution and rejection of missing hardware before control access. This does not validate the physical thermal model.
- Full policy compilation using secilc with neverallow checks enabled: RC0.
- EROFS comparison of 3,380 entries and 2,797 regular payloads, covering ownership, modes, links, types, and security attributes, followed by complete kernel23 readback.

The R2 image was `vendor-generation13-native-audio-r2.erofs`, 404,697,088 bytes, SHA-256 `0fbc54ccfe5bec06756a13ac537654e6ac37057b5e38b640d79077164382b815`.

At the initial preparation checkpoint, the preceding connection had ended at 13:28:35 Europe/Rome with USB ENODEV. No reboot had been requested; the cause was not established. Initial Android, UART, and hypervisor logs were retained, while retrieval of `/data/local/tmp/gos-audio13-preparation-full.log` was still outstanding.

Hardware admission required a fresh original proxy check and an exact current NVMe metadata match. The inactive vendor11 rollback archive had to match the device before writing, while active vendor12 and stable vendor10 remained protected.

### R2 API behavior

Master mute and volume are not implemented as hardware controls. The service explicitly returns unsupported so AudioFlinger can use its software mixer. Remote checks cover the unsupported results; R8 reconfirmed 19,200 actual frames and four-channel sample comparison. R1 was never installed.

All local R2 checks passed. The plan was frozen and checked on a private sparse-file fixture; hardware admission stayed false until a physical metadata read. At one subsequent readiness report, the host still did not enumerate the proxy’s USB ports, so no device write was attributed to that report.

## Vendor14 routing correction

The first vendor13 hardware trial exposed an address-conversion mismatch. A speaker `alsa(card,device)` AIDL address became a legacy Android `id` address and no longer matched the published port. Vendor14 used the canonical AOSP internal `id("")` address while retaining actual ALSA card/PCM selection in the backend. The framework and original Google libraries were not replaced.

Installed image: `vendor-generation14-native-audio-r1.erofs`, 404,701,184 bytes, SHA-256 `8c688b41ec297f31cf0f1f536756f14ffd2a17fc0cf52d91a58f480142e89fc8`.

On M1, the vendor12 rollback archive matched the device, the new payload read back correctly, and all four liblp metadata copies committed successfully. Previous vendor13 and stable vendor10 were preserved. Android’s `/system/bin/reboot` was used for the transition; the proxy was not reset.

Android completed boot with SELinux Enforcing. The framework opened the m1 primary at 48 kHz; the speaker port was ID4 and primary I/O was 13. An AAudio probe selected and rechecked ID4, accepted 48,000 stereo frames at 48 kHz, and exited with code 0. AudioFlinger subsequently reported 69,632 frames written, no mixer underrun, and a return to standby. The HAL and protector remained active in the audio domain, and the kernel recorded the actual speaker unlock.

Evidence reference: `trial-native-audio-kernel23-v14-r1/hardware-audio-result.json`. The complete 5,607,424-byte Android log was retrieved and SHA-256 verified as `5aa1b8ed4f498232fd305622b94b49e620edbd3d6b5cf3ae6315a1bd3e8f7c26`. A replacement full logger used timestamp overlap.

These digital observations did not establish audible output. At that checkpoint the headphones were paired but not connected during the trial; playback and acoustic confirmation remained separate checks. The peak limit and incomplete LSP-chain validation were unchanged.

## XRUN and MCA pause correction

The owner subsequently confirmed Spotify playback through the Bluetooth headphones, while the selected internal-speaker route remained silent. The verified `android-full-8d3b7e655e.log` recorded `write failed: -32` at 14:47:10.063 and rejection of standby from ERROR at 14:47:11.528. Frames accepted before the failure did not establish stable playback.

The correction handles a real XRUN through ALSA prepare and rechecks protection before sending client samples. Other errors remain errors. It conservatively retains the last observed presentation position across PCM reset.

MCA does not advertise INFO_PAUSE. Pause therefore performs a real stop, freezes position accounting, and retains pending data in a bounded queue. Flush discards that queue; resume replays it only after protection checks. Read-only diagnostics expose controls, ownership/locks, PCM state, recovery counts, and peaks.

The Bionic/Binder/FMQ fixture with actual snd-aloop reproduced EPIPE and ERROR with the old binary. R9 then passed 220 ms starvation, an empty burst, sample-checked recovery, pause with backpressure, resume, drain, standby/reopen, and the Android pause → flush → standby sequence. `native-primary-audio-local-runtime-r9-xrun-pause/result.json` passed. This remained CPU validation rather than acoustic or physical thermal validation.

## Vendor15 acoustic result

Vendor15 installed with the vendor13 rollback archive verified on the device, complete image readback, and all liblp copies passing. Android reported `boot_completed=1` with SELinux Enforcing.

The owner confirmed that Spotify played through the internal speakers. Bluetooth headphone playback had already been confirmed on vendor14. The digital peak limit and protector remained unchanged. This establishes the observed playback result; it does not validate the full DSP chain, original maximum volume, or extended thermal operation.
