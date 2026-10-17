// SPDX-License-Identifier: Apache-2.0
#include "m1_lights_service.h"
#include <android/binder_manager.h>
#include <android/binder_process.h>
#include <cerrno>
#include <cstdio>

using aidl::android::hardware::light::HwLight;
using aidl::android::hardware::light::HwLightState;
using aidl::android::hardware::light::LightType;
using aidl::android::hardware::light::FlashMode;
using aidl::android::hardware::light::BrightnessMode;
using aidl::android::hardware::light::ILights;

namespace googlebook {
ndk::ScopedAStatus M1LightsService::getLights(std::vector<HwLight>* result) {
    std::vector<M1Light> lights;
    int error = owner_->enumerate(&lights);
    if (error) return ndk::ScopedAStatus::fromServiceSpecificError(-error);
    result->clear();
    for (const auto& node : lights) {
        HwLight light;
        light.id = node.id;
        light.ordinal = 0;
        light.type = static_cast<LightType>(node.type);
        result->push_back(light);
    }
    return ndk::ScopedAStatus::ok();
}

ndk::ScopedAStatus M1LightsService::setLightState(int32_t id, const HwLightState& state) {
    if (id < 0 || id > 2) return ndk::ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
    if (state.flashMode != FlashMode::NONE ||
        (state.brightnessMode != BrightnessMode::USER && state.brightnessMode != BrightnessMode::SENSOR))
        return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
    int error = owner_->set(id, static_cast<unsigned>(state.color));
    return error ? ndk::ScopedAStatus::fromServiceSpecificError(-error) : ndk::ScopedAStatus::ok();
}

binder_status_t M1LightsService::dump(int fd, const char**, uint32_t) {
    std::vector<M1Light> lights;
    std::map<int, int> issues;
    int result = owner_->enumerate(&lights, &issues);
    dprintf(fd, "M1 native lights: discovery=%d; sysfs request/readback interface\n", result);
    for (const auto& light : lights)
        dprintf(fd, "id=%d type=%d maximum=%d controller=%s\n", light.id, light.type,
                light.maximum, light.directory.c_str());
    for (const auto& [id, error] : issues)
        dprintf(fd, "id=%d unavailable errno=%d\n", id, -error);
    return STATUS_OK;
}
}

#ifndef GOS_LIGHTS_TEST_LIBRARY
int main() {
    if (!ABinderProcess_setThreadPoolMaxThreadCount(4)) return 1;
    ABinderProcess_startThreadPool();
    auto service = ndk::SharedRefBase::make<googlebook::M1LightsService>(std::make_shared<googlebook::M1Lights>());
    std::string name = std::string(ILights::descriptor)+"/default";
    if (AServiceManager_addService(service->asBinder().get(), name.c_str()) != STATUS_OK) return 2;
    puts("GOOGLEBOOK_M1_LIGHTS_REGISTERED: real sysfs controllers only");
    ABinderProcess_joinThreadPool();
    return 3;
}
#endif
