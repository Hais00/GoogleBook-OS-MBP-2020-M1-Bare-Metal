#!/usr/bin/env python3
"""The earlier seven-partition image assembler is superseded."""
raise SystemExit(
    "The legacy USB image used system_b and an incompatible partition layout. "
    "Use scripts/build_fixed_super.py and scripts/install_fixed_m1.py for the "
    "checked internal M1 installation. See apple_silicon_boot/BOOT_INSTRUCTIONS.md. "
    "Original assembler: .work/backup-before-repair/scripts/."
)
