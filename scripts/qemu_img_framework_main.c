// SPDX-License-Identifier: MIT
// Call the qemu-img CLI entry point packaged as a macOS UTM framework.
#include <dlfcn.h>
#include <stdio.h>

int main(int argc, char **argv) {
    if (argc < 2) return 2;
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "dlopen: %s\n", dlerror()); return 2; }
    int (*entry)(int, char **) = dlsym(library, "main");
    if (!entry) { fprintf(stderr, "dlsym: %s\n", dlerror()); return 2; }
    return entry(argc - 1, argv + 1);
}
