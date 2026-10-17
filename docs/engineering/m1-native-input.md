> Historical engineering notes. The current status is in ../../README.md and ../../docs/status.md; earlier candidate/pending sections describe their original phase.

# Native M1 J293 keyboard illumination and function row

Status: implemented and staged; physical qualification remains pending. The first kernel22 trial registered ADP successfully, but stopped at the host9P mount before the installer. No vendor8 image write began. That host export/pipe failure has been corrected and regression-tested; the next run awaits a fresh physical proxy boot.

## Owners

* Kernel22 builds DRM_PANEL_SUMMIT and INPUT_UINPUT into the kernel; ADP/PWM/LED/evdev drivers are also built in.
* android.hardware.lights-service.m1 implements canonical frozen ILights V2, accepted by this system’s 202604 matrix. The provided private V3 hash is not impersonated.
* The lights owner discovers apple-panel-bl, the actual DT-labelled kbd_backlight PWM LED, and the Summit-compatible backlight. Main-screen, keyboard and Touch Bar errors are independent; every write uses the kernel brightness interface and checks its requested-value readback. Readback does not prove optical brightness.
* m1-touchbar selects the platform driver adp before opening a DRM device, then requires an actual non-desktop connector and its real portrait mode. It never opens DCP/Asahi cards. KMS master contention fails normally. Two CPU-rendered GEM buffers are reused only after real page-flip events; missing completion stops the owner.
* The physical Touch Bar sensor is excluded through Android’s supported excluded-input-devices.xml. The daemon grabs only that sensor, observes the Apple SPI keyboard without grabbing it, and emits genuine key transitions on a truthfully named BUS_VIRTUAL uinput device.
* The controls row provides screen/keyboard brightness, media, volume and function keys. Physical Fn or the row’s Fn cell selects F1–F12. Keyboard brightness changes go through ILights; the daemon has only read access to PWM state. The row is event driven and dims after inactivity.

## Input and failure semantics

Actual evdev X/Y extents and multitouch slot count are queried. Initial per-slot coordinates are queried from the kernel; unchanged axes remain cached across contacts. Retiring and reusing one slot within a frame preserves the old release before the new press. Dragging away releases the original key and cannot press a different key until lift. Local brightness/Fn actions require a completed tap. Multiple fingers are tracked independently; key reference counts prevent one finger releasing another’s key. Layout changes release held keys. SYN_DROPPED, hotplug loss and output failure disconnect/restart the native owner and require a fresh kernel contact census, avoiding manufactured presses.

The panel rotation currently maps the horizontal row clockwise into the kernel’s portrait scanout. Its physical orientation must be checked on the M1. The global ILights implementation does not qualify Android’s separate per-InputDevice keyboard-backlight slider; that integration remains a distinct gap.

## Candidate and validation

The input-only vendor-input-stage is an independent clone of installed generation7. Broader USB/audio/power/QTI cleanup candidates are not mixed into it. Full Android SELinux compilation retains neverallow checks. The row has its own vendor domain, input/graphics groups and bounded ioctl families. PWM/backlight writes remain with the existing light HAL role; no permissive domain or DAC override is introduced. A provided Roboto asset lives in the vendor partition, avoiding forbidden generic system-file access.

Verified artifacts: all3268 EROFS entries, including2694 file hashes, owners/modes/security xattrs/symlinks; the kernel22 first-stage Android boot; all387 reconstructed original Android+firmware entries after transport deduplication; real Bionic callback tests, ASan/UBSan input-model tests with three rejected controls (drag, same-frame slot reuse and persistent-axis loss), actual vendor linker namespaces, and actual HWC discovery code versus its pinned pre-fix negative control. These are not physical Touch Bar/keyboard qualification.

The immutable vendor8 r2 image is467214336 bytes, SHA256 04c2e312cfd31f2ccdbf2fbc85ec8dcce925750cbdc44af97acdc548150d7e88. Its planned free super extent starts at8002732032, preserving all gen0–7 payloads. Old installed generation7 remains active until a successful verified installer commit.

## Host9P correction

The first input trial exposed a launcher/exporter mismatch: an immutable generation directory was passed to a wrapper accepting only the old default inbox. The rejected child left inherited pipe ends in its parent, hiding EOF. The wrapper now admits only the exact selected directory under maintenance/shared when its update plan matches the launcher’s SHA256. Existing symlink and pipe-only/no-listener restrictions remain. The transport closes child-only pipe ends immediately. Before opening Serial or acquiring a physical lease, the launcher performs real 9P2000 version/attach and a walk to update-plan.json. Actual guard negatives and a deliberately retained write-end control demonstrate that refusal fails and EOF is observable.

## Physical closure still required

Boot the corrected host pipeline from a fresh proxy, verify the bounded installer readback/LP commit, and observe Android boot. Confirm the light HAL lists the three actual controllers, the function-row daemon owns ADP and receives real flip completions, the main display remains normal, the raw sensor is excluded, the uinput keys reach InputReader, and keyboard/Touch Bar illumination changes visibly. Capture all kernel/HV logs and retrieve every full on-device logcat segment before another reboot. Reboots use Android whenever it is running.
