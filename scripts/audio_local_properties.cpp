// SPDX-License-Identifier: Apache-2.0
// CPU fixture only. Never install this property-area initializer on Android.
#include <property_info_serializer/property_info_serializer.h>
#include <sys/stat.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

extern "C" int __system_property_area_init();
extern "C" int __system_property_add(const char*, unsigned, const char*, unsigned);
extern "C" const void* __system_property_find(const char*);
extern "C" int __system_property_update(void*, const char*, unsigned);

static bool read_all(int fd, void* p, size_t n) {
    while (n) {
        ssize_t got = read(fd, p, n);
        if (got <= 0) return false;
        p = static_cast<char*>(p) + got; n -= got;
    }
    return true;
}

int main(int argc, char** argv) {
    if (access("/GOS_LOCAL_AUDIO_TEST", F_OK) || access("/dev/snd", F_OK) == 0) {
        std::fputs("Refusing property fixture outside diskless audio test\n", stderr);
        return 1;
    }
    mkdir("/dev/__properties__", 0711);
    std::string trie, error;
    if (!android::properties::BuildTrie({}, "u:object_r:default_prop:s0", "string", &trie, &error)) {
        std::fprintf(stderr, "%s\n", error.c_str()); return 1;
    }
    {
        std::ofstream file("/dev/__properties__/property_info", std::ios::binary);
        file.write(trie.data(), trie.size());
        if (!file) return 1;
    }
    // A diskless VM with SELinux disabled cannot label the new tmpfs files.
    // Bionic still initializes the real area; the actual adds below must work.
    int rc = __system_property_area_init();
    std::printf("LOCAL_PROPERTY_AREA_INIT=%d (SELinux labeling unqualified)\n", rc);
    bool serve = false;
    for (int i = 1; i < argc; ++i) {
        if (!std::strcmp(argv[i], "--serve")) { serve = true; continue; }
        const char* eq = std::strchr(argv[i], '=');
        if (!eq) return 1;
        // Bionic uses the NUL-terminated name for trie lookup as well as the
        // explicit length. Never pass the original "name=value" argument.
        std::string name(argv[i], eq - argv[i]);
        if (__system_property_add(name.c_str(), name.size(), eq + 1, std::strlen(eq + 1))) {
            std::fprintf(stderr, "Property add failed: %s\n", argv[i]); return 1;
        }
    }
    std::puts("LOCAL_REAL_BIONIC_PROPERTIES_READY");
    std::fflush(stdout);
    if (!serve) return 0;
    // Minimal legacy property transport for the real service manager's own
    // readiness publication. No ready state is synthesized by this fixture.
    // Version2 is deliberately not advertised; Bionic selects its legacy
    // fixed-size prop_msg protocol, as in property_service.h.
    int listener = socket(AF_UNIX, SOCK_STREAM, 0);
    sockaddr_un address{}; address.sun_family = AF_UNIX;
    std::strcpy(address.sun_path, "/dev/socket/property_service");
    if (listener < 0 || bind(listener, reinterpret_cast<sockaddr*>(&address), sizeof(address)) || listen(listener, 8)) return 1;
    for (;;) {
        int fd = accept(listener, nullptr, nullptr);
        if (fd < 0) return 1;
        struct { unsigned command; char name[32]; char value[92]; } message{};
        if (read_all(fd, &message, sizeof(message)) && message.command == 1 &&
            memchr(message.name, 0, sizeof(message.name)) && memchr(message.value, 0, sizeof(message.value)) &&
            (!std::strcmp(message.name, "servicemanager.ready") || !std::strcmp(message.name, "logd.ready"))) {
            const void* old = __system_property_find(message.name);
            int status = old ? __system_property_update(const_cast<void*>(old), message.value, std::strlen(message.value)) :
                __system_property_add(message.name, std::strlen(message.name), message.value, std::strlen(message.value));
            std::printf("LOCAL_REAL_READINESS_PUBLICATION=%s=%s status=%d\n", message.name, message.value, status);
            std::fflush(stdout);
        }
        close(fd);
    }
}
