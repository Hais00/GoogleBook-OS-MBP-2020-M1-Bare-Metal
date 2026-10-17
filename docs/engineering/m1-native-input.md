# Keyboard illumination and Touch Bar integration

**Historical scope: initial kernel22/vendor8 candidate.** This report records the source implementation and early local validation. Later panel validation is documented in the [Touch Bar scanout audit](m1-touchbar-visual-audit-20261017.md); the [status page](../status.md) is the current summary.

## Device ownership

Kernel22 built DRM_PANEL_SUMMIT and INPUT_UINPUT into the image, alongside ADP, PWM, LED, and evdev dependencies.

`android.hardware.lights-service.m1` implemented canonical frozen ILights V2, accepted by the system’s 202604 matrix. It did not substitute the provided private V3 interface hash.

The Lights service discovers `apple-panel-bl`, the actual DT-labelled `kbd_backlight` PWM LED, and the Summit-compatible backlight. Main-display, keyboard, and Touch Bar failures are independent. Writes use kernel brightness interfaces and verify requested-value readback; readback alone does not establish optical brightness.

`m1-touchbar` selects the ADP platform driver before opening a DRM device and requires an actual non-desktop connector and its portrait mode. It does not open DCP/Asahi cards. KMS master contention is reported normally. Two CPU-rendered GEM buffers are reused only after actual page-flip completion; a missing completion stops the service.

Android’s `excluded-input-devices.xml` excludes the physical Touch Bar sensor from direct handling. The daemon grabs that sensor only, observes the Apple SPI keyboard without grabbing it, and emits genuine transitions through a BUS_VIRTUAL uinput device.

The control row provides display/keyboard brightness, media, volume, and function keys. Physical Fn or the row’s Fn cell selects F1–F12. Keyboard brightness requests go through ILights; the daemon has read-only PWM-state access. The row is event-driven and dims after inactivity.

## Input and failure handling

The implementation queries evdev axis extents, multitouch slot count, and initial per-slot coordinates. Coordinates remain cached when an axis is unchanged. Retiring and reusing a slot within one frame preserves the release before a new press. Dragging away releases the original key and cannot activate another until lift.

Brightness and Fn actions require a completed tap. Multiple fingers are tracked independently; key reference counts prevent one contact from releasing another’s key. Layout changes release held keys. SYN_DROPPED, hotplug loss, and output failure disconnect/restart the service and require a fresh kernel contact census.

The initial panel mapping rotated the horizontal row clockwise into the kernel’s portrait scanout. Physical orientation remained a device check at this checkpoint. Android’s separate per-InputDevice keyboard-backlight slider was not qualified by the global ILights implementation.

## Candidate and local validation

The input-only stage independently cloned installed generation7. Broader USB/audio/power/QTI candidates were kept separate. Full SELinux compilation retained neverallow checks. The row had a dedicated vendor domain, input/graphics groups, and bounded ioctl families. PWM/backlight writes remained with the Lights HAL; no permissive domain or DAC override was introduced. A vendor Roboto asset avoided generic system-file access.

Completed checks included:

- All 3,268 EROFS entries, including 2,694 file hashes, ownership, modes, security attributes, and symlinks.
- Kernel22 first-stage Android boot and comparison of all 387 reconstructed original Android/firmware entries after transport deduplication.
- Bionic callback tests, ASan/UBSan input-model tests, actual vendor linker namespaces, and HWC discovery code tested against its pinned pre-fix negative control.
- Rejection of three controls covering drag behavior, same-frame slot reuse, and persistent-axis loss.

These checks did not establish physical Touch Bar or keyboard illumination behavior.

The vendor8 R2 image was 467,214,336 bytes, SHA-256 `04c2e312cfd31f2ccdbf2fbc85ec8dcce925750cbdc44af97acdc548150d7e88`. Its planned free `super` extent began at 8002732032, preserving generations0–7. Generation7 stayed active until verified installation and metadata commit.

## Host 9P correction

The first trial registered ADP but stopped at the host 9P mount before the installer; no vendor8 write began. The launcher selected a frozen generation directory while the exporter wrapper accepted only the previous default inbox. Inherited pipe ends left in the parent hid EOF when the child rejected that request.

The wrapper was changed to admit the exact selected directory under `maintenance/shared` only when its update plan matched the launcher’s SHA-256. Existing symlink and pipe-only/no-listener restrictions remained. The transport closed child-only pipe ends immediately. Before Serial access or physical-session reservation, preflight performed actual 9P2000 version/attach and a walk to `update-plan.json`.

Guard negative controls and a deliberately retained pipe write end demonstrated both rejection behavior and observable EOF. Later physical checks needed to establish ADP ownership, page-flip completion, input routing, and visible illumination; subsequent scanout results are in the linked audit.
