# Licensing scope

This repository is a **multi-license collection**. The project MIT text in `LICENSES/MIT-Project.txt` applies to original port documentation and original port files identified as MIT in the inventory; it does not relicense Linux, ALSA, speakersafetyd, Apache-licensed code, or other third-party material. The top-level `LICENSE` is an index, not a repository-wide MIT grant.

Use these records together:

- [Third-party notices](THIRD_PARTY_NOTICES.md): component-specific grants and retained notices.
- [License audit](docs/license-audit.md): evidence, obligations, contribution policies, and distribution boundaries.
- [`manifests/license-audit.json`](manifests/license-audit.json): file and patch-member conclusions, their basis, and publication adjustments.
- [`LICENSES/`](LICENSES/): license/exception texts; [`notices/`](notices/) retains exact component grants and supporting notices.
- Source-file copyright and license notices, including any broader or alternative grant, remain authoritative.

## Classification rules

1. A file’s explicit license and retained upstream notice take precedence over the project MIT grant.
2. An untagged upstream file is evaluated using its component’s pinned licensing evidence, never automatically assigned MIT.
3. Original port glue without a separate header is covered by the project maintainer’s MIT declaration. That classification is a project declaration, not an independent proof of authorship or a guarantee about AI-output copyrightability.
4. Patch files contain material from their target files. Their scope is recorded per member; an aggregate patch is not automatically MIT because the repository has a project MIT file.
5. License texts and verbatim upstream notices retain their own copying conditions. A code-license label is not applied to the legal text itself.

`LicenseRef-ALSA-Package-LGPL-2.1` identifies the exact ALSA `COPYING` text retained for the untagged `configure.ac`. It adds no terms, removes no broader upstream grant, and does not infer an “or later” permission for that file from a different ALSA source file.

The modification notices dated 2026-10-17 record downstream publication/notice changes and the included port modifications. They do not assign new upstream authorship dates. Historical Git revisions remain available; their original per-file third-party terms are not superseded by the project MIT grant.
