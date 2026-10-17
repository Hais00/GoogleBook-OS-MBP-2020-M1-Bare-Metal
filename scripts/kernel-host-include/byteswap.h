/* SPDX-License-Identifier: GPL-2.0 */
/* Modified for GoogleBook OS on 2026-10-17; existing GPL terms retained. */
#ifndef _BYTESWAP_H
#define _BYTESWAP_H

#ifdef __APPLE__
#include <libkern/OSByteOrder.h>
#define bswap_16(x) _OSSwapInt16(x)
#define bswap_32(x) _OSSwapInt32(x)
#define bswap_64(x) _OSSwapInt64(x)
#else
#define bswap_16(x) __builtin_bswap16(x)
#define bswap_32(x) __builtin_bswap32(x)
#define bswap_64(x) __builtin_bswap64(x)
#endif

#endif /* _BYTESWAP_H */
