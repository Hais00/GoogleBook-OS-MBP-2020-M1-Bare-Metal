# Changelog

## Initial public source snapshot 17 October 2026

- Published port implementations, changed upstream sources, patches, build/staging recipes and engineering notes for J293 Android bring-up.
- Added capability-checked native HIGH/REALTIME GPU queue creation, caller-scoped discovery, coordinated Mesa support and actual owner-error propagation.
- Preserved old-kernel/unprivileged/virtio LOW/MEDIUM fallback and rejected debug queue reuse with a different priority.
- Recorded successful local kernel/Mesa builds and full vendor filesystem tests. New priority hardware qualification is deferred at the owner's request.
- Documented earlier working boot, Wi-Fi, Bluetooth/headphone playback, speaker playback, Touch Bar and app Vulkan evidence, plus remaining media, compositor and direct-boot work.
- Replaced host-specific paths and partition identifiers in the public export. No proprietary images, firmware blobs, binaries or private captures were published.

## License and provenance audit 17 October 2026

- Added per-file and per-patch-member licensing records, dated modification notices, supporting CRTC notices, and exact upstream license copies.
- Distinguished GPL-only speakersafetyd from its legacy MIT history, package-level ALSA evidence, and the separate SwiftShader patch origin.
- Removed kernel-specific usage guidance from general license texts without altering their terms.
- Disclosed AI assistance and documented upstream contribution restrictions.
- Regenerated aggregate patches for notice-bearing snapshots; runtime implementation and hardware-test status remain unchanged.
