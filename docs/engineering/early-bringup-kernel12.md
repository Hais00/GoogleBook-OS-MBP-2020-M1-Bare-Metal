# Early Android bring-up through kernel12

**Historical checkpoint: kernel12, 16 October 2026.** Target: MacBookPro17,1 / J293 / t8103. This report preserves the early diagnostic state and subsequent USB findings. It is not the current installation procedure. See [project overview](../../README.md) and [validation status](../status.md).

Paths are schematic, and partition identifiers are examples. Several private operator tools and result files named below are outside the public release.

At preparation time, Android had not completed a stable QEMU boot and AGX/DCP graphics had not been validated on M1. Actual writes, readback hashes, and backup locations were recorded separately in `.work/installed-manifest.json`.

## 1. Boot chain and installation boundaries

The recorded chain was Apple boot → m1n1 → U-Boot → GRUB or extlinux → Android kernel/initrd. The Apple stub, m1n1 stage1, the UEFI-associated ESP on `disk0s4`, and its stage2 were outside this installation’s update scope.

| Target | Example GPT UUID | Recorded size in bytes | Installer action |
| --- | --- | ---: | --- |
| `disk0s7`, EFI-GOS | `00000000-0000-4000-8000-000000000002` | 999997440 | Update selected boot files and documentation. |
| `disk0s8`, super | `00000000-0000-4000-8000-000000000001` | 8899264512 | Replace selected Android images while preserving existing logical state. |
| `disk0s9`, metadata | `00000000-0000-4000-8000-000000000004` | 63963136 | No installer write. |
| `disk0s10`, userdata | `00000000-0000-4000-8000-000000000005` | 321589870592 | No installer write or formatting. |

The installer did not modify GPT, other operating systems, recovery, or free space outside the Android allocation. Android could subsequently write its metadata and userdata filesystems normally.

EFI-GOS used FAT with 4096-byte sectors. GRUB located it by filesystem UUID rather than unstable `nvme0/1/2` numbering; the public example is `ABCD-1234`. `EFI/debian/grub.cfg` forwarded to `boot/grub`. The displayed 2.06 version belonged to GRUB.

## 2. Kernel and build environment

| Item | Recorded value |
| --- | --- |
| Kernel | Asahi Linux `7.1.13-googlebook-m1+`, build12 |
| Base commit | `94fb23346d522edf53722357c426a3e58030beea` |
| Source layout | `/opt/googlebook/build/linux-asahi` |
| Configuration | `scripts/kernel-googlebook.config`; effective checkpoint at `.work/kernel-native-usb-input-checkpoint/config` |
| Configuration delta | `.work/kernel6-to-kernel12-config.diff` |
| Host/partition adaptations | `scripts/kernel-macos-m1.patch` and `scripts/kernel-host-include` |
| Build recipe | `scripts/build_kernel.sh`, running `olddefconfig` before `Image dtbs` |
| Toolchain | LLVM19, Rust1.85.0, bindgen0.73.2, GNU make/sed; Android NDK r28, API34 for ARM64 userspace |

Userspace ELF alignment supported 16 KiB pages. `/opt/googlebook/build` was an image-backed volume from `.work/GOSBuild.sparseimage`; ownership support was enabled on that image volume to retain Android UID/GID during system EROFS reconstruction.

### Inherited kernel6 configuration

The preceding kernel already included ARM64 16 KiB pages, Binder/BinderFS, SELinux, `SECURITY_NETWORK`, SELinux in `CONFIG_LSM`, cpuset v1, `PROC_PID_CPUSET`, NVMe, security-labelled EROFS/ext4, built-in Asahi AGX and Apple DCP, and Samsung UART/earlycon support. Linux naming for super/metadata/userdata matched only the identified partitions and did not rename physical GPT entries.

### Additions through kernel12

| Area | Configuration and purpose |
| --- | --- |
| ext4 quota | `QFMT_V2=y`, `QUOTA_TREE=y` for vold’s quota mount requirements. |
| Filesystems | `FS_ENCRYPTION=y`, `FS_VERITY=y`, `UNICODE=y`, and related algorithms. |
| ART | `USERFAULTFD=y` and architecture support. |
| Android networking | Legacy IPv4/IPv6 iptables, netfilter/conntrack/NAT, policy routing, filters, tunnels/IPsec, BPF classifier/action, and VETH. |
| Scheduling | `UCLAMP_TASK=y`, `UCLAMP_TASK_GROUP=y`, `PM_WAKELOCKS=y`. |
| VM/IPC | Built-in VSOCKETS, VIRTIO_VSOCKETS, VHOST_VSOCK, TAP/MACVTAP, and VHOST_NET. |
| Apple input/USB | APPLE_TUNABLE, HID_MULTITOUCH, PHY_APPLE_ATC, TYPEC_TPS6598X, and TYPEC_DP_ALTMODE promoted from modules to built-ins. |
| QEMU | Built-in DRM_VIRTIO_GPU, virtio DMA shared buffers, and SND_VIRTIO. |
| ALSA | Built-in SOUND, SND, SND_PCM, and SND_TIMER; Apple audio remained disabled at this checkpoint. |
| Unneeded access | DEVMEM and MTD_SPI_NOR disabled. |

These changes did not enable Apple MCA/codec audio. ALSA/virtio sound supported tests, not speaker playback. No new DCP/AGX format patch was applied at this stage.

## 3. Android images and mounts

The system was derived from the original `android-desktop_signed_recovery_image.bin`. `system_a` was the bootable system; `system_b`/system-other was not treated as an equivalent root.

`build_fixed_super.py` replaced system_a, vendor_a, and system_ext_a, preserved product_a, and updated and verified every liblp metadata copy. New regions remained inside the existing super size with checksum, bounds, and overlap checks.

Writable logical regions were added: `misc` at 4 MiB, `desktop_security_storage` at 32 MiB, and `desktop_security_persist` at 16 MiB. The installer preserved their contents when present. They were absent from the physical kernel6 installation inspected before the update.

The initrd/vendor fstab used:

```text
system_a /system erofs ro wait,logical,first_stage_mount
vendor_a /vendor erofs ro wait,logical,first_stage_mount
product_a /product erofs ro wait,logical,first_stage_mount
system_ext_a /system_ext erofs ro wait,logical,first_stage_mount
/dev/block/by-name/metadata /metadata ext4 noatime,nosuid,nodev wait,first_stage_mount,formattable
/dev/block/by-name/userdata /data ext4 noatime,nosuid,nodev wait,check,formattable,quota,latemount
/dev/block/mapper/misc /misc emmc defaults defaults
```

`formattable` is an Android init option, not an installer operation. The installer did not format those filesystems. File-based encryption was not required in this configuration: `/data` remained unencrypted. Building fscrypt support did not change that state or convert existing data.

## 4. Apple graphics and the QEMU path

The installable candidate used `prepare_m1_install.py --profile m1` without `--trace-drm`.

- Mesa25.3.6 Honeykrisp/Asahi Vulkan: `ro.hardware.vulkan=asahi`.
- ANGLE EGL/GLES: `ro.hardware.egl=angle`.
- minigbm/CrOS gralloc: `ro.hardware.gralloc=cros`, AIDL allocator V2, stable-C mapper V5.
- The allocator’s `apple` backend used linear DMA buffers and PRIME import/export. DCP pitch was aligned to 64 bytes and allocation size to 16 KiB.
- The original desktop composer used its generic DRM backend. `libm1gate.so` returned the SDM backend as unavailable through `sdm::GetSDMInterfaceFactory()`, using an explicit ELF dependency rather than LD_PRELOAD.
- Compression/UBWC and overlays were disabled in the initial profile; SDR/WCG composition requested RGBA8888 (`pixel_format=1`).
- `gosModeAddFB2*` replacement tracing was a QEMU diagnostic facility, not enabled in the M1 HWC executable.

| Android format | DRM FOURCC on little-endian ARM | DCP handling |
| --- | --- | --- |
| RGBA8888 | ABGR8888 | Accepted as DCP_FORMAT_RGBA. |
| BGRA8888 | ARGB8888 | Accepted as DCP_FORMAT_BGRA. |
| RGBX8888 | XBGR8888 | Accepted as an opaque surface. |

References included `minigbm/cros_gralloc/cros_gralloc_helpers.cc`, `minigbm/dumb_driver.c`, and kernel `drivers/gpu/drm/apple/{plane.c,apple_drv.c}`. Surfaces required linear layout and 64-byte-aligned pitch; plane operations remained subject to driver geometry constraints.

The kernel6 hypervisor log showed only simpledrm on the boot framebuffer, without observed DCP/AGX activation. simpledrm exposed the native framebuffer format and emulated XRGB8888, but the allocator had no simpledrm backend. Driver binding therefore required a separate physical check.

The `virt` profile used SwiftShader (`vulkan.pastel.so`) and did not validate Apple GPU execution. SwiftShader revision `cddb5c91b23ff70a1f607ea31610aa0d7f4b5ad5` used `scripts/swiftshader-android.patch` to correct Android JIT memory handling where policy denied execution from memfd. HAL loading, allocation, and a CPU Vulkan job ran under Android/QEMU. Graphical startup still failed because virtio rejected ABGR; the BGRA property alone did not change every compositor buffer request. The proposed subsequent virtio kernel patch was not applied.

## 5. Vendor, init, and SELinux integration

`prepare_m1_install.py` performed the staging changes:

- VINTF XML and init RC files used `vendor_configs_file` labels.
- gralloc/mapper/GBM/Vulkan libraries used `same_process_hal_file`.
- Allocator and audio executables retained their appropriate HAL labels.
- Disabled files were moved outside scanned init/VINTF directories; a `.disabled` suffix alone did not prevent parsing.
- Permissions covered DRM nodes and the new logical security-storage regions.
- Device firmware was placed in initrd and vendor/firmware while retaining SELinux types.
- Google firmware roll-forward was excluded from this Apple profile.
- A vendor precompiled policy inconsistent with modified CIL was removed so init compiled the actual policy instead of using a stale cache.

Target SELinux remained Enforcing. The CIL retained `(allow bootanim self (process (execmem)))` for software-renderer JIT. Later USB findings added specific Apple uevent genfscon labels and diagnostic-shell read access to `sysfs_gpu` as described in section13. Graphics clients used existing GPU permissions. Earlier experimental ptrace/Trusty debug options were not enabled.

## 6. BootControl, security, and initial audio behavior

`bootcontrol_m1.cpp` implemented a single-slot service with a standard bootloader_control record in logical `misc`; it did not open the Mac’s GPT. `ro.build.ab_update=false` and disabled Virtual A/B/snapshot properties matched this model.

StrongBox GSC/Titan was excluded from APEX scanning, gscd was disabled, and the Secretkeeper VM was not advertised on this hardware. `keymint_software.cpp` used the image’s AOSP `libkeymint_fake_latest.so` implementation, explicitly requested `SecurityLevel::SOFTWARE`, and checked the returned level. KeyMint, secure clock, shared secret, and RKP were exposed as software implementations, without a TEE/StrongBox/SEP or hardware-certification claim.

Keymaster headers were pinned at `cabf20e824b15ea48a95f770ada21777c1e32d8e`; build metadata was recorded in `.work/software-keymint-build.json`. Keystore2 registration, shared-secret behavior, and odsign operations were observed in QEMU. Non-secure Trusty used one CPU, CID200, and RPC/VSOCK services. Gatekeeper/PIN and the complete protected-storage path were not validated. RPMB mock storage used the stated logical regions without hardware-protection claims.

Initial audio selected the supplied Nothing module through `vendor.audio.dras.default_nothing=true`. A copy of DRAS loaded `libgosagmservice.so` instead of `libagmipcservice.so`; the adapter returned `-ENODEV` to avoid the Qualcomm AGM retry path. The service retained its audio HAL domain. Nothing HAL startup without an ALSA card was observed in QEMU, but this checkpoint provided neither audio output nor Apple speaker drive.

## 7. Limited OEM framework adaptation

`prepare_system_m1.py` changed only the bodies of public `onStart()` and `onBootPhase(int)` in `com.android.server.desktop.repairmode.DesktopRepairModeService`, inside `desktop-services.jar`.

The watchdog had shown the main thread blocked on GSC manufacturing data during phase520. The service could also manage or remove an OEM repair partition that did not apply to the Mac layout. Those two hooks were made inert; remaining DEX contents and ZIP offsets were retained and checksums recomputed. Only stale associated odex/vdex and fs-verity metadata were removed.

System was rebuilt from the original extraction with Android UID/GID, modes, capabilities, and SELinux attributes preserved. Complete EROFS validation passed; `.work/system-m1-repair-policy.json` recorded the check. Runtime progress beyond that phase still required validation after display initialization was resolved.

## 8. Logging and planned device checks

`scripts/boot_config.py` defined UART, earlycon, a 4 MiB kernel log buffer, `printk.devkmsg=on`, `panic=0`, and `enforcing=1`. Verified Boot state was explicitly orange/unlocked with verity disabled; the modified payload was not represented as a locked verified image.

`androidboot.googlebook.debug=1` enabled a development console as UID2000 in the shell domain, with log access rather than a root shell. Disabling it required removing that argument and regenerating the configurations. logd requested 16 MiB using `ro.logd.size` and `persist.logd.size` after persistent-property loading; the effective device value remained a check.

The earlier `/metadata/googlebook-logs` logger failed under release policy and was removed from the evidence path. The historical installed-boot plan selected UEFI in Apple’s boot options, then GoogleBook OS. A static DTB was not to replace the dynamically completed m1n1/U-Boot tree, which carries firmware information and runtime memory reservations.

The historical USB debug bundle used these operator commands:

```sh
python3 capture_uart.py /dev/cu.usbmodemP_03 --commands-file android_hardware_watch.sh
python3 boot_usb_debug.py /path/to/your/m1n1 --device /dev/cu.usbmodemP_01
```

Port names were examples. Capture used the secondary UART independently of the primary proxy, sent diagnostics after GOS_CONSOLE_READY, and retained raw output on the receiving host. Dependencies included Python/pyserial and the m1n1 environment with construct. These automation changes initially lacked physical-UART validation.

The wrapper loaded a prebuilt compatible m1n1 into RAM without updating on-disk stage2. Hypervisor behavior could differ from direct boot. The earlier U-Boot guest could instead read replacement files from NVMe partition7; the old Image6 was not a substitute for the prepared kernel.

The next capture was intended to establish the kernel12 banner, apexd-bootstrap completion, actual DRM driver identities, allocator/mapper/HWC registration, SystemServer progress beyond phases100/520, stable `sys.boot_completed=1`, a visible frame, input behavior, and finally actual GPU execution.

## 9. Historical build and installation procedure

These commands record the checkpoint workflow. They are not a current, portable installation guide. Compiled graphics components were retained under `/opt/googlebook/build/graphics-out`.

```sh
python3 scripts/build_graphics.py core
python3 scripts/build_graphics.py common
python3 scripts/build_graphics.py mapper
python3 scripts/build_graphics.py legacy
python3 scripts/build_graphics.py allocator
python3 scripts/build_graphics.py backend_gate
python3 scripts/build_graphics.py bootcontrol
python3 scripts/build_graphics.py software-keymint
python3 scripts/build_graphics.py audio-no-agm
python3 scripts/build_graphics.py label-probe
python3 scripts/build_graphics.py native-vkprobe
python3 scripts/prepare_system_ext_m1.py --software-keymint --one-cpu --software-vulkan
sudo -n python3 scripts/prepare_system_m1.py
python3 scripts/prepare_m1_install.py --profile m1
mkfs.erofs --quiet -b4096 -zlz4hc,12 --workers=4 --all-root extracted_partitions/vendor_m1_fixed.img vendor_work
mkfs.erofs --quiet -b4096 -zlz4hc,12 --workers=4 --all-root extracted_partitions/system_ext_m1_fixed.img /opt/googlebook/build/system-ext-work
python3 scripts/validate_vendor_image.py extracted_partitions/vendor_m1_fixed.img --profile m1
python3 scripts/build_fixed_super.py
```

System used its dedicated ownership-preserving builder rather than `--all-root`. Image/DTB came from the tested kernel checkpoint, and the smoke result was updated before installation.

The installer normally required a complete QEMU boot. The explicitly requested historical device trial used diagnostic hardware bring-up mode:

```sh
sudo -n diskutil mount disk0s7
sudo -n python3 scripts/install_fixed_m1.py --hardware-bringup
```

That mode recorded the diagnostic exception rather than manufacturing a positive QEMU result. UUID, size, GPT, Apple-profile, vendor-label, source-integrity, and kernel smoke checks remained mandatory.

Before the first write, the installer preserved complete super contents, current EFI files, primary/secondary GPT, and the previous manifest in private `.work/backup-before-hardware-*` storage. The sparse super backup retained its full logical size and passed SHA-256 readback. Existing writable logical regions were also preserved by `android_lp_state.py`.

The installer wrote only super and the listed EFI-GOS files, verified complete super and file readbacks, then rechecked both GPTs. Restore was defined against the same UUID-identified partitions using that backup, not a whole-disk image. `dist/googlebook_os_m1.img` was obsolete for this checkpoint. Private backups are not included in the source release.

## 10. Evidence and checkpoint limitations

- `.work/selinux-smoke-results-kernel12.json` covered SELinux Enforcing mount, Binder, cpuset v1 task assignment, kmsg bursts, ext4 quota, and filesystem behavior.
- Loading the original Android policy was tested separately in a permissive VM; that did not validate every runtime access.
- Enforcing Android/QEMU boots reached several services, software KeyMint, and CPU rendering, but not a stable desktop.
- `test_android_lp_state.py` covered state preservation, older-layout migration, backup permissions, and corrupt-metadata rejection.
- `.work/vendor-vintf-label-validation.json` covered EROFS extraction, actual labels, the m1 profile, RGBA composition, and absence of diagnostic HWC imports.
- The earlier kernel6 hardware capture was retained privately as `M1-Linux-kernel-6-logs-2026-10-16`.

DCP/AGX binding was observed only in the later USB trial described below. GPU execution, buffer import/presentation, complete boot, acceleration, full input, credentials/TEE, and audio remained outstanding at the initial checkpoint. This was a development configuration with software KeyMint, unencrypted data, and a diagnostic console.

## 11. Recorded artifact identities

Hashes identify the original checkpoint artifacts. Published paths and UUIDs are schematic and do not establish exact image reproduction.

### Kernel command line

```text
earlycon console=tty0 console=ttySAC0,115200n8 ignore_loglevel loglevel=8 log_buf_len=4M printk.devkmsg=on panic=0 enforcing=1 root=/dev/ram0 init=/init androidboot.hardware=android-desktop androidboot.slot_suffix=_a androidboot.super_partition=super androidboot.boot_part_uuid=00000000-0000-4000-8000-000000000002 androidboot.verifiedbootstate=orange androidboot.vbmeta.device_state=unlocked androidboot.flash.locked=0 androidboot.veritymode=disabled androidboot.force_normal_boot=1 androidboot.googlebook.debug=1 androidboot.serialconsole=1 androidboot.console=console clk_ignore_unused pd_ignore_unused
```

### Boot files

| File | SHA-256 |
| --- | --- |
| `Image` | `dbe1df9b603be472c2ebb7b65cab2a34a132336cb017c30d2842ce8b70ed3503` |
| `initrd.img` | `390f328d57e2b62036867005da29d455b60302646e143a39dbefc9f2b5934197` |
| `t8103-j293.dtb` | `ea32173df3b0f782bf610f38fb390f90a777c16d4a4b2822c58b924bc6088328` |

### Logical images in the super template

| Partition | Bytes | Offset within super | Template SHA-256 |
| --- | ---: | ---: | --- |
| `system_a` | 1105584128 | 1048576 | `ff1461e6f30fdfafef274f3b4b1b7faf09ee8edec279321355917090f3edeecc` |
| `vendor_a` | 457269248 | 1107296256 | `fb86109758e96c5da9d8889df7ce15abd416838be44342c72a4a2680cd88a1b1` |
| `system_ext_a` | 202010624 | 6814695424 | `65ea181bf2f0851993f1a0c33d34b6d8c00c6c95d81503a331a237b8c5834814` |
| `misc` | 4194304 | 7017070592 | `cd287c86034d9e78c5328ce074944f50dacae623ff49e56e9f5ab446fe6cfd84` |
| `desktop_security_storage` | 33554432 | 7021264896 | `83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302` |
| `desktop_security_persist` | 16777216 | 7054819328 | `080acf35a507ac9849cfcba47dc2ad83e01b75663a516279c8b9d243b719643e` |

Writable-state hashes may change during boot.

## 12. Kernel12 capture and console correction

Historical capture: `/opt/googlebook/host/M1-Linux-kernel-12-logs-2026-10-16/`; structured diagnosis: `.work/kernel12-hardware-diagnosis.json`.

The correct kernel12 and apexd-bootstrap started. The 157-second capture contained no kernel panic or automatic reboot. SurfaceFlinger terminated with SIGABRT 26 times; the allocator exited with status1 27 times. Graphics failures recurred at roughly five-second intervals. Internal abort details were unavailable because logcat had not reached the UART.

The GPU modalias contained only `apple,agx-g13g`, while this Asahi driver required `apple,agx-t8103`. The prepared DTB included both, plus `apple,dcp` and `apple,display-subsystem`. The older m1n1/U-Boot guest was therefore passing a different tree: loading Image12 from NVMe did not replace the bootloader-supplied DT. The capture showed simpledrm without observed DCP/AGX activation. Lack of a simpledrm allocator backend was a separate graphics obstacle from uevent SELinux denials and the still-unavailable abort details.

Console startup had been requested at 2.850169 s, before coldboot completed at 2.940660 s. The service was moved to the init phase after `wait_for_coldboot_done`, matching the original Android console. That removed a possible device-node race; missing console output alone did not establish it as the sole cause. `androidboot.serialconsole=1` and `androidboot.console=console` were made explicit.

The following trial was to use matched kernel/DTB RAM loading through `boot_usb_debug.py`, allowing m1n1 to apply runtime fixups. It did not reuse the old `uboot-hv-cb1024.raw`, update on-disk stage2, or force a static DTB through GRUB.

Reference: [AOSP init service implementation](https://android.googlesource.com/platform/system/core/+/refs/heads/main/init/service.cpp).

The console correction passed a QEMU check: coldboot completed at 8.643586 s and the UID2000 shell started at 10.760373 s; command execution was confirmed in `.work/console-coldboot-validation.json`. This did not establish physical UART availability or complete Android boot.

## 13. Matched-DTB USB trial and DRM labels

Historical capture: `/opt/googlebook/host/M1-GoogleBook-USB-Debug-logs-2026-10-16/`; diagnosis: `.work/usb-hardware-graphics-diagnosis.json`.

The kernel12 image was unchanged. With the matched DTB, Asahi initialized as DRM minor1 and Apple DCP as minor3. The UID2000 console and SELinux Enforcing were observed. This established driver binding, not GPU execution.

logcat then showed Vulkan/ANGLE initialization failure and SurfaceFlinger aborting without an EGLConfig. Two blockers were identified:

1. DCP’s `/dev/dri/card3` carried the generic SELinux `device` type because the original mapping covered only card0/card1. The allocator was denied read/write access. Patterns for card[0-9]+ and renderD[0-9]+ were added using the existing Android `gpu_device` type instead of fixed indices.
2. The GPU uevent remained generic sysfs. libdrm requires OF_FULLNAME/OF_COMPATIBLE from that file to discover the Vulkan device. Four targeted genfscon entries covered GPU `206400000.gpu` and DCP `soc:display-subsystem` uevents across the two platform-parent layouts. The `sysfs_gpu` type already allowed graphics-client access; the diagnostic shell received only read/open/getattr permissions for that type.

`apple_graphics_policy.py` centralized these rules without generic sysfs access or permissive mode. Physical genfs labels still required the next capture.

Under enforcing Android/QEMU with the actual images, `googlebook-labelprobe` used libselinux to resolve card0/card1/card3/card137/renderD128/renderD130 contexts and query loaded-policy access for SurfaceFlinger, gpuservice, allocator, and composer. All checks passed. `.work/graphics-selinux-validation.json` was bound to kernel/vendor/system_ext hashes and required by the installer, including bring-up mode. The check did not emulate AGX work or validate physical genfs paths.

A one-shot native Vulkan probe was prepared for debug=1 and `ro.hardware.vulkan=asahi`. It ran as gpu_service UID1072 in the original gpuservice domain through `gpuservice_exec`, logged under `googlebook-vulkan`, and had an init timeout of 25 seconds. Its domain was checked in QEMU, where absence of an Apple device was reported normally.

The probe required integrated-GPU type and MESA_HONEYKRISP driverID26, rejecting CPU SwiftShader as Apple GPU evidence. It created a Vulkan device/queue, allocated a buffer, submitted vkCmdFillBuffer, waited for completion, and checked the resulting data. Honeykrisp reports Mesa vendorID `0x10005`; the check therefore used driverID and device type rather than Apple PCI vendorID. Only a matching VULKAN_SMOKE_PASS could establish that job. EGL, AHardwareBuffer import, and DCP presentation remained separate checks.

`android_hardware_watch.sh` was extended to collect DRM labels, canonical uevent paths and labels, matcher/policy results, the Vulkan probe tag, logcat, and boot status. The matched-DTB USB path and paired on-disk stage2 were preserved; the planned update covered vendor/system_ext within super and EFI-GOS documentation, with backups and verified readback. Complete Android boot was not claimed before the following trial.
