// SPDX-License-Identifier: Apache-2.0
// Runs real DrmDevice discovery against CPU-only DRM callbacks. No hardware ioctls.
#include "drm/DrmDevice.h"
#include "drm/DrmPlane.h"
#include "drm/DrmFbImporter.h"
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <unistd.h>
#include <vector>

enum class Scenario { NonDesktop, Desktop, Legacy, PropertyFailure, InvalidValue, ModeFailure };
static Scenario scenario;
static bool modes_probed;
static int master_calls;
static std::string fixture;
static std::vector<int> opened;
static void check(bool value, const char* text) {
    if (!value) { fprintf(stderr, "HWC_OWNER_FIXTURE_FAIL %s\n", text); exit(1); }
}
extern "C" int __real_open(const char*, int, ...);
extern "C" int __wrap_open(const char* path, int flags, ...) {
    mode_t mode = 0;
    if (flags & O_CREAT) { va_list args; va_start(args, flags); mode = va_arg(args, int); va_end(args); }
    int fd = flags & O_CREAT ? __real_open(path, flags, mode) : __real_open(path, flags);
    if (path == fixture && fd >= 0) opened.push_back(fd);
    return fd;
}
extern "C" int __wrap_drmSetClientCap(int, uint64_t, uint64_t) { return 0; }
extern "C" int __wrap_drmGetCap(int, uint64_t, uint64_t* value) { *value = 64; return 0; }
extern "C" int __wrap_drmSetMaster(int) { ++master_calls; errno = EACCES; return -1; }
extern "C" int __wrap_drmIsMaster(int) { return 0; }
extern "C" drmModeResPtr __wrap_drmModeGetResources(int) {
    auto* result = static_cast<drmModeResPtr>(calloc(1, sizeof(drmModeRes)));
    result->count_connectors = result->count_encoders = result->count_crtcs = 1;
    result->connectors = static_cast<uint32_t*>(calloc(1, sizeof(uint32_t)));
    result->encoders = static_cast<uint32_t*>(calloc(1, sizeof(uint32_t)));
    result->crtcs = static_cast<uint32_t*>(calloc(1, sizeof(uint32_t)));
    result->connectors[0] = 42;
    return result;
}
extern "C" drmModeConnectorPtr __wrap_drmModeGetConnector(int, uint32_t id) {
    if (scenario == Scenario::ModeFailure) { errno = ENODEV; return nullptr; }
    modes_probed = true;
    auto* value = static_cast<drmModeConnectorPtr>(calloc(1, sizeof(drmModeConnector)));
    value->connector_id = id;
    value->connector_type = DRM_MODE_CONNECTOR_DSI;
    return value;
}
extern "C" drmModeObjectPropertiesPtr __wrap_drmModeObjectGetProperties(int, uint32_t, uint32_t) {
    if (scenario == Scenario::PropertyFailure) { errno = EIO; return nullptr; }
    auto* result = static_cast<drmModeObjectPropertiesPtr>(calloc(1, sizeof(drmModeObjectProperties)));
    if (scenario == Scenario::Legacy) return result;
    result->count_props = 1;
    result->props = static_cast<uint32_t*>(calloc(1, sizeof(uint32_t)));
    result->prop_values = static_cast<uint64_t*>(calloc(1, sizeof(uint64_t)));
    result->props[0] = 7;
    // A panel marks itself non-desktop only when its modes are probed.
    result->prop_values[0] = scenario == Scenario::NonDesktop && modes_probed;
    return result;
}
extern "C" drmModePropertyPtr __wrap_drmModeGetProperty(int, uint32_t id) {
    auto* value = static_cast<drmModePropertyPtr>(calloc(1, sizeof(drmModePropertyRes)));
    value->prop_id = id;
    strcpy(value->name, "non-desktop");
    value->flags = DRM_MODE_PROP_RANGE;
    if (scenario != Scenario::InvalidValue) {
        value->count_values = 2;
        value->values = static_cast<uint64_t*>(calloc(2, sizeof(uint64_t)));
        value->values[1] = 1;
    }
    return value;
}

int main() {
    const char* base = getenv("TMPDIR");
    std::string pattern = std::string(base ? base : "/tmp")+"/hwc-owner-XXXXXX";
    int created = mkstemp(pattern.data()); check(created >= 0, "create fixture"); close(created);
    fixture = pattern;
    for (auto kind : {Scenario::NonDesktop, Scenario::Desktop, Scenario::Legacy,
                      Scenario::PropertyFailure, Scenario::InvalidValue, Scenario::ModeFailure}) {
        scenario = kind; modes_probed = false; master_calls = 0; opened.clear();
        auto device = android::DrmDevice::CreateInstance(fixture, nullptr, 0);
        check(!device, "fixture never grants a DRM master or real display");
        int expected = kind == Scenario::Desktop || kind == Scenario::Legacy ? 1 : 0;
        check(master_calls == expected, "master requested only for proven desktop/legacy outputs");
        if (kind == Scenario::NonDesktop) check(modes_probed, "panel modes probed before property classification");
        check(opened.size() >= 2, "real probe and init file descriptors observed");
        for (int fd : opened) {
            errno = 0;
            check(fcntl(fd, F_GETFD) == -1 && errno == EBADF, "rejected device releases all file descriptors");
        }
    }
    unlink(fixture.c_str());
    puts("HWC_NON_DESKTOP_OWNERSHIP_FIXTURE_PASS: six source-execution cases, modes-before-property, no master takeover, FD release");
    return 0;
}
