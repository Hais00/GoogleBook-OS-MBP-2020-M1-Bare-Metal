# Third-party notices

This independent downstream project contains code and patches derived from the projects below. Names identify origin and technical compatibility; they do not imply endorsement by Apple, Google, Asahi Linux, Mesa, or other upstream contributors. Product names and trademarks are not licensed by the code licenses.

## Linux Asahi

Pinned source and changed paths are recorded in [`manifests/upstreams.json`](manifests/upstreams.json). The kernel as a whole uses GPL version 2, while individual files retain their own grants:

- GPL-2.0-only, including legacy `GPL-2.0` SPDX spelling.
- GPL-2.0-or-later where the file explicitly says so.
- `GPL-2.0-only OR MIT` for the Asahi Rust file.
- MIT for the Asahi UAPI header.
- HPND-sell-variant for `drivers/gpu/drm/drm_crtc.c`, retaining its complete permission and copyright notice.

The kernel syscall exception is not a blanket exception for all kernel code. It applies where the relevant UAPI grant provides it. The Asahi UAPI header published here is explicitly MIT.

The CRTC notice requires the copyright and permission text in supporting documentation and restricts use of copyright-holder names in advertising. A verbatim copy is in [`notices/linux-drm-crtc-original-notice.txt`](notices/linux-drm-crtc-original-notice.txt) and incorporated into the repository `NOTICE`.

AOSP memfd/ashmem shim files retain Google LLC’s GPL-2.0 headers and the recorded Android kernel origin; they are not relicensed as Apache-2.0 or MIT.

## Mesa and Honeykrisp

The exported Mesa source files use MIT notices, including the existing Valve, Alyssa Rosenzweig, Collabora, Red Hat, Intel, AMD, Google LLC, and other notices present in individual files. Mesa as a whole contains multiple licenses; this statement is limited to the files published here.

The Android native-buffer adaptation is derived from Google LLC’s MIT-licensed PanVK Android code at the recorded Mesa revision. Copyright and license headers are retained. Per-file evidence is in the audit inventory.

## ChromiumOS minigbm

The exported files refer to the component’s BSD-3-Clause license. [`sources/minigbm/LICENSE`](sources/minigbm/LICENSE) is preserved verbatim, together with per-file Chromium OS copyright notices. Source redistribution retains the notice, conditions, and disclaimer; binary redistribution additionally carries them in its accompanying material. The Google/contributor non-endorsement condition remains applicable.

## drm-hwcomposer

`drm/ResourceManager.cpp` retains its 2018 Android Open Source Project copyright and Apache-2.0 grant. The pinned upstream `NOTICE` is preserved verbatim in [`sources/drm-hwcomposer/NOTICE`](sources/drm-hwcomposer/NOTICE) and [`notices/upstream/drm-hwcomposer/NOTICE`](notices/upstream/drm-hwcomposer/NOTICE). Modified source carries a downstream change notice.

## speakersafetyd

The exported `src/main.rs` is explicitly GPL-2.0-only. Its Asahi Linux copyright and GPL terms are retained. The pinned README describes a historical transition: releases through 2.0.2 were MIT; code checked in afterward is GPL version 2. The retained legacy `LICENCE.MIT` does **not** make the exported GPL-only file dual-licensed.

Both upstream license documents are retained under [`notices/upstream/speakersafetyd/`](notices/upstream/speakersafetyd/). The downstream modification changes runtime paths; it does not claim a new license for the thermal model.

## ALSA-lib

The exported `configure.ac` has no per-file license header. The package’s exact LGPL version 2.1 `COPYING` text is retained in [`sources/alsa-lib/COPYING`](sources/alsa-lib/COPYING) and [`LICENSES/LicenseRef-ALSA-Package-LGPL-2.1.txt`](LICENSES/LicenseRef-ALSA-Package-LGPL-2.1.txt).

Other ALSA library files explicitly permit LGPL-2.1-or-later; that is not used to invent a file-specific grant for this untagged build input. The inventory records the package evidence and this limit. The project MIT grant does not apply to it. The upstream tree also includes a separate `aserver/COPYING`; this is not a blanket LGPL label for every ALSA-tree file.

## m1n1

The exported Python host transport file is MIT-licensed. The Asahi Linux copyright and full MIT grant are retained in [`sources/m1n1/LICENSE`](sources/m1n1/LICENSE).

A complete m1n1 firmware build contains additional components, including BSD-licensed code, zlib-licensed tinf, CC0/public-domain material, the OFL-1.1 Source Code Pro font, and Rust crates. The upstream README and `3rdparty_licenses`/vendor trees define their terms. This repository does not ship a compiled m1n1 firmware or those assets; its single host-file license must not be generalized to a full firmware distribution.

## Asahi AVD firmware

The complete source is referenced at its pinned upstream revision. The MIT grant is retained in [`notices/upstream/avd-fw/LICENSE`](notices/upstream/avd-fw/LICENSE). The local build/linker recipe is included; no compiled firmware is published here. This grant does not cover proprietary Apple firmware used by other devices.

## SwiftShader

The historical Android adaptation patch targets `cddb5c91b23ff70a1f607ea31610aa0d7f4b5ad5`. Its affected upstream code uses Apache-2.0 and The SwiftShader Authors’ notices. A new original port linker/export fragment is recorded separately under the project MIT declaration; it is not automatically relicensed as Apache. The full package license is retained in [`notices/upstream/swiftshader/LICENSE.txt`](notices/upstream/swiftshader/LICENSE.txt). Original headers for the affected upstream files are reproduced in `notices/upstream/swiftshader/modified-file-notices.txt`. No SwiftShader binary or bundled dependency tree is distributed here.

## AOSP and port-specific files

AOSP is not universally Apache-2.0: Android kernel imports can be GPL, and other projects contain their own licenses. Existing Apache-2.0 declarations in port sources remain Apache-2.0; original untagged port glue is identified separately as project-declared MIT. The full Apache license is supplied, along with applicable upstream notices and modification notices for the copied, changed source files.

Linked libraries, Android images, Apple firmware, NDK/toolchain binaries, fonts, and other build inputs that are not included here are outside this source snapshot’s redistribution inventory. A future binary/image release requires its own complete dependency and corresponding-source review.
