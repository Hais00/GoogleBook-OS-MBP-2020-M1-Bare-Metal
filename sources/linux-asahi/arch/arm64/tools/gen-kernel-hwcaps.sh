#!/bin/sh -e
# SPDX-License-Identifier: GPL-2.0
# Modified for GoogleBook OS on 2026-10-17.
# Port integration changes; original copyright and license notices retained.
# See THIRD_PARTY_NOTICES.md and manifests/license-audit.json.
#
# gen-kernel-hwcap.sh - Generate kernel internal hwcap.h definitions
#
# Copyright 2026 Arm, Ltd.

if [ "$1" = "" ]; then
	echo "$0: no filename specified"
	exit 1
fi

echo "#ifndef __ASM_KERNEL_HWCAPS_H"
echo "#define __ASM_KERNEL_HWCAPS_H"
echo ""
echo "/* Generated file - do not edit */"
echo ""

grep -E '^#define HWCAP[0-9]*_[A-Z0-9_]+' $1 | \
	sed 's/.*HWCAP\([0-9]*\)_\([A-Z0-9_][A-Z0-9_]*\).*/#define KERNEL_HWCAP_\2\t__khwcap\1_feature(\2)/'

echo ""
echo "#endif /* __ASM_KERNEL_HWCAPS_H */"
