# Third party sources and licenses

The port builds on Asahi Linux, Mesa Honeykrisp, AOSP, ChromiumOS minigbm, drm-hwcomposer, ALSA and speakersafetyd. Copyright and SPDX headers in the source files remain authoritative. Exact upstream repositories and revisions are recorded in `manifests/upstreams.json`.

- Linux kernel changes retain the original licenses, including GPL-2.0-only and dual GPL/MIT files. `sources/linux-asahi/COPYING` and the upstream tree define their scope.
- Mesa/Asahi code and the Android native-buffer adaptation retain their original MIT notices, including Google LLC and The Asahi Linux Contributors.
- minigbm and drm-hwcomposer retain their original project and per-file notices.
- speakersafetyd remains GPL-2.0-only and a separate derivative. The change here adapts its runtime paths; the thermal model is retained.
- ALSA-lib retains LGPL-2.1-or-later and its upstream notices.
- AOSP-derived code and probes marked Apache-2.0 retain that license.
- The Asahi AVD firmware source is referenced upstream; no compiled firmware is included.

License texts are in `LICENSES/` and the component COPYING files. The root MIT license covers original port glue and documentation only where a file does not specify or inherit a different upstream license. It does not relicense third party sources. Proprietary Android/Google components and Apple firmware are not included in this repository.
