// SPDX-License-Identifier: Apache-2.0
// Register the image's AOSP software crypto backend with its truthful level.
#include <AndroidKeyMintDevice.h>
#include <AndroidRemotelyProvisionedComponentDevice.h>
#include <AndroidSecureClock.h>
#include <AndroidSharedSecret.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>
#include <android/log.h>
#include <keymaster/soft_keymaster_logger.h>

using namespace aidl::android::hardware::security;

template <class T> static bool publish(const std::shared_ptr<T>& service) {
    const auto name = std::string(T::descriptor) + "/default";
    auto status = AServiceManager_addService(service->asBinder().get(), name.c_str());
    __android_log_print(status == STATUS_OK ? ANDROID_LOG_INFO : ANDROID_LOG_ERROR,
                        "googlebook-keymint", "%s: %d", name.c_str(), status);
    return status == STATUS_OK;
}

int main() {
    keymaster::SoftKeymasterLogger logger;
    ABinderProcess_setThreadPoolMaxThreadCount(4);
    ABinderProcess_startThreadPool();
    // Allocate the KeyMint object in its original library. This preserves the
    // image's concrete class ABI and all cryptographic implementations.
    auto keymint = keymint::CreateKeyMintDevice(keymint::SecurityLevel::SOFTWARE);
    keymint::KeyMintHardwareInfo info;
    if (!keymint || !keymint->getHardwareInfo(&info).isOk() ||
        info.securityLevel != keymint::SecurityLevel::SOFTWARE) {
        __android_log_print(ANDROID_LOG_ERROR, "googlebook-keymint",
                            "Software backend initialization failed");
        return 1;
    }
    __android_log_print(ANDROID_LOG_WARN, "googlebook-keymint",
                        "SOFTWARE security: %s; no hardware TEE or StrongBox", info.keyMintName.c_str());
    auto concrete = std::static_pointer_cast<keymint::AndroidKeyMintDevice>(keymint);
    auto clock = ndk::SharedRefBase::make<secureclock::AndroidSecureClock>(concrete);
    auto secret = ndk::SharedRefBase::make<sharedsecret::AndroidSharedSecret>(concrete);
    auto provisioned = ndk::SharedRefBase::make<keymint::AndroidRemotelyProvisionedComponentDevice>(concrete);
    if (!publish(keymint) || !publish(clock) || !publish(secret) || !publish(provisioned))
        return 1;
    ABinderProcess_joinThreadPool();
    return 1;
}
