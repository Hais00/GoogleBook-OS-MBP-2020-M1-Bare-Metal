# Touch Bar scanout audit

**Historical sequence: kernel22 to kernel23, 17 October 2026.** The final section records the confirmed panel result. See [current status](../status.md) for the broader port.

## Initial observations

The owner reported working touch controls but persistently distorted labels, including while stationary. The initial trial was `trial-native-input-kernel22-c`, kernel22, vendor generation9 / input R3.

The production `Font` class and `rowPixel` function generated readable images on both host and M1. The PGM outputs matched byte for byte, SHA-256 `e5413ed1678168e97f43be2f51e062d60487cc3d2ebb95e670e3d7cf9674e303`; the console transfer was independently hash-checked. The host renderer passed ASan/UBSan.

That test used CPU memory, a 60×2008 logical image, assumed 240-byte pitch, and 2048 allocated rows. It did not read the active framebuffer or validate actual pitch, panel orientation, or ADP alignment. The driver programmed the DMA address and framebuffer pitch directly; shadow helpers alone did not establish that a copy was missing.

The physical distortion still needed classification and actual buffer parameters needed verification. No speculative correction, partition update, or reboot was performed at this point. Touch commands and observed PWM requests remained functional. Complete file logging continued while the UART retained kernel and crash output.

Historical references: `.agent-work/touchbar-render-audit/runtime-result.json` and `.agent-work/touchbar-render-audit/actual-m1-cpu.png`.

## Photograph and alignment test

The reference photograph showed split and repeated letter strokes while cell boundaries remained recognizable. Simulating a 240-byte-pitch buffer read with a 192-byte stride produced similar distortion and horizontal stretching. This supported an alignment hypothesis; it was not a measurement of ADP registers.

A shell attempt to query KMS metadata received errno 13 when opening the ADP card. Permissions were not broadened.

The candidate `kernel-adp-scanout-pitch.patch` used `drm_mode_size_dumb()` with 64-byte row alignment, retained the existing height rounding to 64 rows, and logged allocation dimensions. For a 60×2008 XRGB8888 image, pitch became 256 bytes. The DRM helper handled overflow and page-aligned allocation size; height rounding was checked beforehand. The same renderer at 256-byte pitch passed ASan/UBSan and produced the identical logical image.

Kernel23 was prepared as a RAM trial with the same configuration as kernel22. Vendor generation9 and the installed Touch Bar program were unchanged; only the following physical test could establish panel behavior.

## Confirmed hardware result

Kernel23 logged `scanout allocation 60x2048 pitch=256 bytes size=524288` on M1. Android completed boot and the Touch Bar service was active. The owner confirmed that the distortion was resolved.

The observed defect was therefore corrected by ADP allocation alignment, with vendor generation9 unchanged. Complete logs from kernel22-c had been retrieved and verified before the Android-requested reboot.
