# Source release scope

This release contains local port code and snapshots of modified upstream files. Complete upstream repositories are referenced as Git submodules at explicit commits. Aggregate patches describe the changes against those commits. A unified procedure that reproduces the complete tested Android system is not yet provided.

## Publication adjustments

The source manifest records both local-origin and exported-file hashes. Private host paths were replaced with schematic paths; machine-specific partition identifiers were replaced with example UUIDs. The functional GPU implementation, including the priority ABI and queue handling, matches the built revision. Published snapshots now additionally carry license identifications and dated modification notices added after the local builds. These source-only publication changes do not constitute a new hardware test. The published GPT matching code is a template and requires installation-specific configuration.

The recipes in `scripts/` still partly depend on the historical dependency layout. Private device/UART reservation tools are omitted. Some historical tests reference those tools and are not a consolidated public test suite. Build and test normalization remains subsequent work.

## Included and external material

Published material consists of source, patches, configuration, documentation, and selected validation reports. Android images, Apple firmware, proprietary Google HALs, compiled binaries, recovery/super/userdata images, keys, credentials, network identifiers, and private UART captures are excluded.

A future full-image distribution requires its own component inventory and corresponding-source assessment. This source release does not establish that such an image is ready for distribution.

## Documentation provenance

Historical engineering reports retain the sequence of candidates, failures, and verified results. Translations and editorial revisions preserve technical identifiers, artifact hashes, measurements, and validation scope. For current status, use `README.md`, `docs/status.md`, and the selected reports under `tests/results/`.

## License audit revision

The current tip includes a per-file license audit, supporting notices, and notice-bearing aggregate patches. See [Licensing scope](../LICENSING.md). Historical/focused patch variants are archived with their own provenance preambles; use the supported aggregate patches for the current publication snapshots.
