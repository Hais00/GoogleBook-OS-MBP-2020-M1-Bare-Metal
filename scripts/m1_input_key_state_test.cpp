// SPDX-License-Identifier: Apache-2.0
// CPU-only syscall callback fixture: no input device is opened or controlled.
#include "m1_input_key_state.h"
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <linux/input.h>
#include <sys/ioctl.h>
static int resultBytes, kernelError, calls;
static bool held;
static void check(bool value, const char* text) { if (!value) { fprintf(stderr,"INPUT_SNAPSHOT_FIXTURE_FAIL: %s\n",text); exit(1); } }
extern "C" int __wrap_ioctl(int fd, unsigned long request, ...) {
    check(fd==42 && _IOC_TYPE(request)=='E' && _IOC_NR(request)==0x18, "exact EVIOCGKEY request");
    ++calls; va_list arguments; va_start(arguments,request); auto* output=va_arg(arguments,unsigned char*); va_end(arguments);
    const unsigned bytes=_IOC_SIZE(request); check(bytes==(KEY_MAX+8)/8, "kernel bitmap buffer length");
    memset(output,0,bytes);
    if (held) output[KEY_FN/8] |= 1u<<(KEY_FN%8);
    errno=kernelError; return resultBytes;
}
int main() {
    bool down=false; int copied=-1;
    resultBytes=(KEY_MAX+8)/8; kernelError=EINVAL; held=true;
    check(googlebook::readInputKeyState(42,KEY_FN,&down,&copied)==0 && down && copied==resultBytes,
          "positive byte count is a valid state snapshot despite stale errno");
    held=false;
    check(googlebook::readInputKeyState(42,KEY_FN,&down,&copied)==0 && !down, "released key is an actual zero bit");
    down=true; copied=-1; resultBytes=KEY_FN/8;
    check(googlebook::readInputKeyState(42,KEY_FN,&down,&copied)==-ENODATA && down && copied==-1,
          "truncated bitmap cannot acknowledge an unobserved Fn bit");
    resultBytes=0; check(googlebook::readInputKeyState(42,KEY_FN,&down)==-ENODATA, "zero copied bytes are not a state snapshot");
    resultBytes=(KEY_MAX+8)/8+1; check(googlebook::readInputKeyState(42,KEY_FN,&down)==-EOVERFLOW, "oversized kernel result rejected");
    resultBytes=-1; kernelError=EIO;
    check(googlebook::readInputKeyState(42,KEY_FN,&down)==-EIO && down, "real kernel error preserved without mutating state");
    int before=calls;
    check(googlebook::readInputKeyState(42,KEY_MAX+1,&down)==-EINVAL && googlebook::readInputKeyState(42,KEY_FN,nullptr)==-EINVAL && calls==before,
          "invalid callers never issue ioctl");
    puts("M1_INPUT_KEY_SNAPSHOT_BIONIC_FIXTURE_PASS: positive byte counts, stale errno, released key, bounds and actual errors");
}
