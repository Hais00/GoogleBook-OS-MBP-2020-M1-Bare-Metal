// SPDX-License-Identifier: Apache-2.0
// Test-only sink for actual liblog datagrams. Does not implement a HAL or logd.
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
int main(void) {
    if (access("/GOS_LOCAL_AUDIO_TEST", F_OK) || access("/dev/snd", F_OK) == 0) return 1;
    setvbuf(stdout, NULL, _IONBF, 0);
    int fd = socket(AF_UNIX, SOCK_DGRAM, 0);
    struct sockaddr_un addr = {0}; addr.sun_family = AF_UNIX;
    strcpy(addr.sun_path, "/dev/socket/logdw");
    if (fd < 0 || bind(fd, (struct sockaddr*)&addr, sizeof(addr))) return 1;
    for (;;) {
        unsigned char bytes[65536];
        ssize_t n = recv(fd, bytes, sizeof(bytes), 0);
        if (n < 0) return 1;
        printf("REAL_LIBLOG_DATAGRAM bytes=%zd text=", n);
        for (ssize_t i = 0; i < n; ++i) {
            unsigned c = bytes[i];
            if (c >= 32 && c < 127) putchar(c);
            else if (c == 0) putchar('|');
            else printf("\\x%02x", c);
        }
        putchar('\n');
    }
}
