// SPDX-License-Identifier: Apache-2.0
// A client of the real Google processes in the diskless CPU fixture.
// No HAL service or successful completion is synthesized by this test.
#include <android/binder_ibinder.h>
#include <android/binder_manager.h>
#include <android/binder_parcel.h>
#include <android/binder_process.h>
#include <android/binder_status.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/system_properties.h>

static void* unused_create(void* p) { return p; }
static void unused_destroy(void* p) { (void)p; }
static binder_status_t unused_transact(AIBinder* b, transaction_code_t t,
                                       const AParcel* in, AParcel* out) {
    (void)b; (void)t; (void)in; (void)out;
    return STATUS_UNKNOWN_TRANSACTION;
}

static int call(AIBinder* binder, transaction_code_t code, int arg,
                AParcel** response) {
    AParcel* request = NULL;
    binder_status_t status = AIBinder_prepareTransaction(binder, &request);
    if (status == STATUS_OK && arg >= 0) status = AParcel_writeInt32(request, arg);
    if (status != STATUS_OK) { AParcel_delete(request); return 1; }
    status = AIBinder_transact(binder, code, &request, response, 0);
    if (status != STATUS_OK) { fprintf(stderr, "Transaction failed: %d\n", status); return 1; }
    AStatus* result = NULL;
    status = AParcel_readStatusHeader(*response, &result);
    int failed = status != STATUS_OK || !AStatus_isOk(result);
    if (result) {
        if (failed) fprintf(stderr, "Remote status: %d\n", AStatus_getExceptionCode(result));
        AStatus_delete(result);
    }
    return failed;
}

int main(int argc, char** argv) {
    if (access("/GOS_LOCAL_AUDIO_TEST", F_OK) || access("/dev/snd", F_OK) == 0) return 1;
    char property[PROP_VALUE_MAX] = {};
    __system_property_get("vendor.audio.dras.default_nothing", property);
    printf("LOCAL_FRESH_PROCESS_NOTHING_PROPERTY=%s\n", property);
    fflush(stdout);
    if (!ABinderProcess_setThreadPoolMaxThreadCount(2)) return 1;
    ABinderProcess_startThreadPool();
    if (argc == 2 && !strcmp(argv[1], "--owners")) {
        const char* owners[] = {
            "android.hardware.audio.core.IModule/default",
            "android.hardware.audio.core.IModule/a2dp",
            "com.android.desktop.audio.IDesktopAudioFactory/default",
            "android.hardware.audio.core.IModule/r_submix"
        };
        for (unsigned i = 0; i < sizeof(owners)/sizeof(owners[0]); ++i) {
            AIBinder* b = AServiceManager_checkService(owners[i]);
            if (!b || AIBinder_ping(b) != STATUS_OK) {
                fprintf(stderr, "Missing real owner: %s\n", owners[i]); return 1;
            }
            printf("LOCAL_REAL_OWNER_READY=%s\n", owners[i]);
            AIBinder_decStrong(b);
        }
        return 0;
    }
    const char* name = "android.hardware.bluetooth.audio.IBluetoothAudioProviderFactory/default";
    AIBinder* factory = AServiceManager_checkService(name);
    if (argc == 2 && !strcmp(argv[1], "--expect-absent")) {
        if (factory) { AIBinder_decStrong(factory); return 1; }
        puts("LOCAL_FACTORY_ABSENT_NEGATIVE_CONTROL_PASS"); return 0;
    }
    if (!factory) { fputs("Real factory not registered\n", stderr); return 1; }
    const AIBinder_Class* clazz = AIBinder_Class_define(
        "android.hardware.bluetooth.audio.IBluetoothAudioProviderFactory",
        unused_create, unused_destroy, unused_transact);
    if (!clazz || !AIBinder_associateClass(factory, clazz) || !AIBinder_isRemote(factory)) return 1;
    AParcel* response = NULL;
    // Stable AIDL compiler-reserved version transaction; verified against the
    // compiler's actual NDK output in this checkout.
    if (call(factory, FIRST_CALL_TRANSACTION + 16777214, -1, &response)) return 1;
    int32_t version = 0;
    if (AParcel_readInt32(response, &version) != STATUS_OK || version != 6) return 1;
    AParcel_delete(response); response = NULL;
    printf("LOCAL_REAL_FACTORY_VERSION=%d\n", version);
    // Factory method order and SessionType value come from the pinned public
    // IBluetoothAudioProviderFactory.aidl and SessionType.aidl (A2DP software=1).
    if (call(factory, FIRST_CALL_TRANSACTION, 1, &response)) return 1;
    int32_t capabilities = 0;
    if (AParcel_readInt32(response, &capabilities) != STATUS_OK || capabilities <= 0) return 1;
    AParcel_delete(response); response = NULL;
    printf("LOCAL_REAL_A2DP_CAPABILITY_COUNT=%d\n", capabilities);
    if (call(factory, FIRST_CALL_TRANSACTION + 1, 1, &response)) return 1;
    AIBinder* provider = NULL;
    if (AParcel_readStrongBinder(response, &provider) != STATUS_OK || !provider ||
        !AIBinder_isRemote(provider) || AIBinder_ping(provider) != STATUS_OK) return 1;
    AIBinder_decStrong(provider); AParcel_delete(response);
    AIBinder_decStrong(factory);
    puts("LOCAL_REAL_A2DP_PROVIDER_OPEN_PASS");
    return 0;
}
