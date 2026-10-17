# Patch sets

Each component’s `googlebook-port.patch` is the aggregate diff against the commit recorded in `manifests/upstreams.json`. The corresponding files under `sources/` provide readable snapshots. Partition UUIDs in the published kernel are examples.

## Check and apply

Confirm the recorded upstream revision before checking a patch:

```sh
git -C /path/to/linux-asahi apply --check /path/to/repo/patches/linux-asahi/googlebook-port.patch
git -C /path/to/mesa apply --check /path/to/repo/patches/mesa/googlebook-port.patch
```

After the checks pass, apply the selected patch using the same command without `--check`.

## Aggregate and focused patches

The `privileged-priority.patch` files isolate the new GPU priority work for review. The focused Mesa patch assumes that the Android/two-queue integration is already present. The aggregate Mesa patch starts from the recorded upstream revision.

`android-vulkan-full.patch` contains the Vulkan integration without the pre-existing host compiler adaptations. These variants serve different review and composition needs; they are not a sequence to apply cumulatively to the same tree.

Original DRM fence patches and references are retained for provenance. The aggregate kernel patch already includes them. Rebasing the local priority UAPI extension requires coordinated kernel and Mesa review.

## License notices

The supported aggregate patches reproduce dated downstream notices in each modified upstream snapshot. Historical/focused variants retain their source payloads and a publication preamble; their target-file licenses are recorded per member in `manifests/license-audit.json`. They are not collectively relicensed under project MIT. Verbatim upstream fence patches retain their original author/date metadata.
