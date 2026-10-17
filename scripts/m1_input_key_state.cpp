// SPDX-License-Identifier: Apache-2.0
#include "m1_input_key_state.h"
#include <array>
#include <cerrno>
#include <linux/input.h>
#include <sys/ioctl.h>
namespace googlebook {
int readInputKeyState(int fd, unsigned key, bool* down, int* copiedBytes) {
    if (!down || key > KEY_MAX) return -EINVAL;
    std::array<unsigned char, (KEY_MAX+8)/8> keys{};
    int copied = ioctl(fd, EVIOCGKEY(keys.size()), keys.data());
    if (copied < 0) return -errno;
    if (copied > static_cast<int>(keys.size())) return -EOVERFLOW;
    if (copied <= static_cast<int>(key/8)) return -ENODATA;
    *down = (keys[key/8] >> (key%8)) & 1;
    if (copiedBytes) *copiedBytes = copied;
    return 0;
}
}
