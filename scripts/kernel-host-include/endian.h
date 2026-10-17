#ifndef _ENDIAN_H
#define _ENDIAN_H

#include <machine/endian.h>
#include <libkern/OSByteOrder.h>

#ifndef BYTE_ORDER
#define BYTE_ORDER __DARWIN_BYTE_ORDER
#endif
#ifndef LITTLE_ENDIAN
#define LITTLE_ENDIAN __DARWIN_LITTLE_ENDIAN
#endif
#ifndef BIG_ENDIAN
#define BIG_ENDIAN __DARWIN_BIG_ENDIAN
#endif

#ifndef htobe16
#define htobe16(x) OSSwapHostToBigInt16(x)
#endif
#ifndef htole16
#define htole16(x) OSSwapHostToLittleInt16(x)
#endif
#ifndef be16toh
#define be16toh(x) OSSwapBigToHostInt16(x)
#endif
#ifndef le16toh
#define le16toh(x) OSSwapLittleToHostInt16(x)
#endif

#ifndef htobe32
#define htobe32(x) OSSwapHostToBigInt32(x)
#endif
#ifndef htole32
#define htole32(x) OSSwapHostToLittleInt32(x)
#endif
#ifndef be32toh
#define be32toh(x) OSSwapBigToHostInt32(x)
#endif
#ifndef le32toh
#define le32toh(x) OSSwapLittleToHostInt32(x)
#endif

#ifndef htobe64
#define htobe64(x) OSSwapHostToBigInt64(x)
#endif
#ifndef htole64
#define htole64(x) OSSwapHostToLittleInt64(x)
#endif
#ifndef be64toh
#define be64toh(x) OSSwapBigToHostInt64(x)
#endif
#ifndef le64toh
#define le64toh(x) OSSwapLittleToHostInt64(x)
#endif

#endif /* _ENDIAN_H */
