"""Shared boot arguments for the installed M1 system and USB diagnostics."""

BOOT_ARGS = (
    "earlycon console=tty0 console=ttySAC0,115200n8 ignore_loglevel loglevel=8 "
    "log_buf_len=4M printk.devkmsg=on panic=0 enforcing=1 root=/dev/ram0 init=/init "
    "androidboot.hardware=android-desktop androidboot.slot_suffix=_a "
    "androidboot.super_partition=super "
    "androidboot.boot_part_uuid=00000000-0000-4000-8000-000000000002 "
    "androidboot.verifiedbootstate=orange androidboot.vbmeta.device_state=unlocked "
    "androidboot.flash.locked=0 androidboot.veritymode=disabled "
    "androidboot.force_normal_boot=1 androidboot.googlebook.debug=1 "
    "androidboot.serialconsole=1 androidboot.console=console "
    "clk_ignore_unused pd_ignore_unused"
)
