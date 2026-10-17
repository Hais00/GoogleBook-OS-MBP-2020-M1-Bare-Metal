// SPDX-License-Identifier: Apache-2.0
#pragma once
namespace googlebook {
// EVIOCGKEY returns a byte count. Normalize only validated snapshots to zero;
// negative results preserve the actual kernel error, never a stale errno.
int readInputKeyState(int fd, unsigned key, bool* down, int* copiedBytes = nullptr);
}
