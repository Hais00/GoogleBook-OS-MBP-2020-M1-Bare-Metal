// SPDX-License-Identifier: Apache-2.0
// Register the existing Android Bluetooth audio implementation through its
// public AOSP C entry point (bluetooth/audio/aidl/default/service.cpp).
#include <android/binder_process.h>
#include <android/binder_status.h>
#include <android/log.h>

extern binder_status_t createIBluetoothAudioProviderFactory(void);

int main(void) {
    if (!ABinderProcess_setThreadPoolMaxThreadCount(4)) {
        __android_log_print(ANDROID_LOG_ERROR, "M1BluetoothAudio", "Binder pool configuration failed");
        return 1;
    }
    binder_status_t status = createIBluetoothAudioProviderFactory();
    if (status != STATUS_OK) {
        __android_log_print(ANDROID_LOG_ERROR, "M1BluetoothAudio", "Audio factory registration failed: %d", status);
        return 1;
    }
    __android_log_print(ANDROID_LOG_INFO, "M1BluetoothAudio", "Existing Bluetooth audio factory registered");
    ABinderProcess_joinThreadPool();
    return 1; // A service owner must not report success after its Binder loop exits.
}
