// SPDX-License-Identifier: Apache-2.0
#include "core-impl/Configuration.h"
namespace aidl::android::hardware::audio::core::internal {
// Native configuration is supplied only after real ALSA qualification. Do not
// fall back to the example/emulator's invented speaker or telephony profiles.
std::unique_ptr<Module::Configuration> getConfiguration(Module::Type) {
 return std::make_unique<Module::Configuration>();
}
std::vector<aidl::android::media::audio::common::AudioProfile> getStandard16And24BitPcmAudioProfiles() {return {};}
}
