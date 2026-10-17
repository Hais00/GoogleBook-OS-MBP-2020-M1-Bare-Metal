# License and provenance audit

**Audit date: 17 October 2026.** Scope: the source/configuration files, patches, notices, Git references, and documentation published in this repository. This is a documented technical review of license evidence and implemented publication controls, not an independent legal clearance or a binary-distribution certification.

## Findings and corrections

- Replaced blanket repository-level assumptions with file-level and patch-member records.
- Identified the CRTC permission notice as HPND-sell-variant and supplied the copyright/permission text in supporting documentation.
- Added prominent downstream modification notices dated 2026-10-17 to changed upstream snapshots, preserving their original copyright and license notices.
- Regenerated the supported aggregate patches so they reproduce the notice-bearing snapshots. Historical/focused patch payloads retain a separate dated publication preamble and per-member license scope.
- Removed Linux-specific usage-guidance metadata from shared license files without changing the actual license/exception bodies. In particular, kernel guidance on dual-licensing Apache-2.0 is not imposed on independent Apache-licensed userspace.
- Preserved speakersafetyd’s GPL-only current file and its legacy MIT history separately.
- Stopped asserting an unproven per-file “or later” grant for ALSA’s untagged `configure.ac`; retained and identified the exact package COPYING text.
- Added the previously omitted SwiftShader patch origin and its Apache license.
- Recorded AI assistance and upstream submission restrictions without representing license permissions as contribution approval.

## Evidence reviewed

License and contribution documents were inspected at the recorded source revisions. Current organization/project contribution policies were checked separately because they may change after a source tag.

| Project | Pinned evidence and published scope | Treatment |
| --- | --- | --- |
| Linux Asahi | COPYING, license-rules, submitting-patches, and changed-file headers at `94fb23346d522edf53722357c426a3e58030beea`. | GPL-2.0 kernel default; retain explicit alternatives/exceptions and the CRTC custom notice. |
| Mesa | `docs/license.rst`, `docs/submittingpatches.rst`, and exported file notices at `06f9e28304d5d3f109c33535c1c25b9df5769af2`. | Exported files use MIT; do not label every upstream Mesa component MIT. |
| minigbm | LICENSE and per-file references at `a2d42f09d696b04e6ded5ad38596d8554ffd8988`. | BSD-3-Clause, including source/binary notice and non-endorsement requirements. |
| drm-hwcomposer | NOTICE, README, and ResourceManager.cpp at `a87112ca8e78a5d401368bd44672bd73f79fe9af`. | Apache-2.0; retain NOTICE and attribution, mark changes. |
| speakersafetyd | LICENSE, LICENCE.MIT, README license history, and main.rs at `615674e75dc68639d550171e33ba3946538d03b0`. | Exported main.rs is GPL-2.0-only; historical MIT is not a replacement grant. |
| ALSA-lib | Package COPYING, untagged configure.ac, README contribution notes, and library license boilerplate at `a47c8bc3fef190e7eb463283230263c82208597a`. | Preserve package LGPL-2.1 text; avoid inferring the untagged file’s optional later-version grant from another file. |
| m1n1 | LICENSE, README third-party list, and host virtio.py at `809541515659bf4e504807fd72bc0a539be5eee7` / v1.9.9. | Host file MIT; a full firmware has additional licenses/assets. |
| AVD firmware | LICENSE at `220b1e70c9d7dcccbf66d5194e372300aa3c5a32`. | MIT source reference; no compiled firmware or Apple firmware grant. |
| SwiftShader | LICENSE.txt, CONTRIBUTING.txt, and affected source headers at `cddb5c91b23ff70a1f607ea31610aa0d7f4b5ad5`. | Apache-2.0 patch material; package notice retained. |
| AOSP references | Recorded Android kernel and hardware-interface revisions, retained GPL/Apache headers, and AOSP licensing guidance. | File-specific terms; the Android origin alone does not select a license. |

The machine-readable record is [`manifests/license-audit.json`](../manifests/license-audit.json). A project-original MIT declaration is identified as such; it is not presented as independently proven third-party authorship. Untagged upstream material is never assigned project MIT by default.

## Redistribution controls

For source redistribution, retain copyright, license, disclaimer, attribution, and applicable NOTICE text. Modified GPL/LGPL snapshots carry dated change notices; changed Apache source carries a modification notice. Do not remove a dual-license option or apply an exception to files that do not provide it.

Patch archives are also derivative source material. Their target-file licenses remain relevant. The supported component aggregate patches include current publication notices; review-only/historical variants do not imply that reconstructed sources have already completed the current publication checks.

U-Boot and GRUB are referenced in historical boot notes but their code and binaries are not included in this release. Build/runtime tools and libraries not copied here also remain outside this redistribution inventory. Their exact-version licenses must be reviewed if they are included in a future release.

No compiled program, firmware blob, Android partition image, or complete dependency bundle is published in this repository. Therefore this audit does not claim that an executable release has met all corresponding-source or linking obligations. Before such a release:

- Inventory the exact kernel, daemon, library, Rust crate, firmware, font, and other dependency versions actually shipped.
- For GPL-covered binaries, provide complete corresponding source and required build/install material through an applicable license-permitted method. A set of partial snapshots and upstream links is not automatically a complete source offer.
- For LGPL libraries and linked applications, review the selected license version, library modifications, relinking/replacement mechanisms, and permitted reverse engineering for debugging modifications. Dynamic linking alone is not a blanket compliance certificate for an Android image.
- Include required Apache/BSD/MIT/HPND notices and preserve patent/trademark limits. A source license does not grant rights to redistribute proprietary Google/Apple components.

## Contribution policies and AI disclosure

Port-specific code, analysis, documentation, and publication work in this downstream repository used generative-AI assistance, including OpenAI Codex. Upstream code retains its original attribution. Human review, ownership/rights assessment, and any required certification remain responsibilities of the actual submitter. No upstream submission, CLA signature, DCO certification, or maintainer endorsement is claimed.

- **Asahi Linux:** its current [generative-AI policy](https://asahilinux.org/llm-policy/) broadly prohibits material AI-assisted contributions. These downstream changes must not be represented or submitted as policy-compliant Asahi contributions. This policy review is distinct from identifying the existing code-license texts.
- **Mesa:** its current [submission rules](https://docs.mesa3d.org/submittingpatches.html) require submitter understanding/responsibility, disclosure of creative AI assistance, human oversight of submissions, and direct human-authored upstream communication. Individual maintainers may impose additional requirements. This fork does not establish eligibility for a Mesa MR.
- **Linux and drm-hwcomposer:** follow their submission procedures and DCO requirements when contributing upstream. A Signed-off-by line must be an actual contributor’s certification, never an automatically invented assertion.
- **SwiftShader and AOSP:** their upstream contribution procedures require appropriate contributor agreements/review. No agreement is signed or inferred merely by publishing this independent fork.
- **ALSA:** the pinned README describes alsa-devel email and GitHub PR submission routes. No general AI permission or approval is inferred from the absence of a policy in that README.

This audit updates the current repository tip without rewriting published history. Original per-file license grants continue to govern historical revisions; the project MIT grant does not supersede them.

## Primary references

- [Linux kernel licensing rules](https://docs.kernel.org/process/license-rules.html)
- [GNU GPL version 2](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html) and [LGPL version 2.1](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html)
- [Apache License 2.0, section 4](https://www.apache.org/licenses/LICENSE-2.0)
- [SPDX HPND-sell-variant](https://spdx.org/licenses/HPND-sell-variant.html)
- [Mesa license documentation](https://docs.mesa3d.org/license.html)
- [AOSP contributor agreements and license headers](https://source.android.com/docs/setup/contribute/licenses)
- Pinned repository URLs and commits in [`manifests/upstreams.json`](../manifests/upstreams.json); exact grants under [`notices/upstream/`](../notices/upstream/).

## Local publication check

Run `python3 tools/check_license_inventory.py` before publishing source updates. It rejects unclassified code/config files, stale hashes, header/inventory license conflicts, absent license texts, and changed retained notices. It does not determine authorship, copyrightability, binary compliance, or upstream acceptance.

The recorded [publication checks](../tests/results/license-audit-checks.json) include clean application of seven aggregate patches, exact snapshot comparison, preservation of 24 pinned evidence-document hashes, and negative controls that reject false MIT relabeling and newly unclassified code. They do not execute device code.
