// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <aidl/android/hardware/light/BnLights.h>
#include "m1_lights.h"

namespace googlebook {
class M1LightsService final : public aidl::android::hardware::light::BnLights {
public:
    explicit M1LightsService(std::shared_ptr<M1Lights> owner) : owner_(std::move(owner)) {}
    ndk::ScopedAStatus getLights(std::vector<aidl::android::hardware::light::HwLight>* result) override;
    ndk::ScopedAStatus setLightState(int32_t id, const aidl::android::hardware::light::HwLightState& state) override;
    binder_status_t dump(int fd, const char** args, uint32_t numArgs) override;
private:
    std::shared_ptr<M1Lights> owner_;
};
}
