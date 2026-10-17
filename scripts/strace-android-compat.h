#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
/* Bionic puts this POSIX typedef in its sanitized linux/in.h.
 * strace uses upstream bundled UAPI, which intentionally omits libc typedefs. */
#ifdef __ANDROID__
#include <stdint.h>
typedef uint32_t in_addr_t;
/* Bionic does not expose this unlocked stdio entry point. */
#define fputs_unlocked fputs
#endif
