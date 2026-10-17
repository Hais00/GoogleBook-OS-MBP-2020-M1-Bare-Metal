/* Check real AOSP enrollment/verification without Binder registration or user data. */
#include <cassert>
#include <algorithm>
#include <cstddef>
#include <cstdio>
#include "GateKeeper.h"
#include "SharedSecret.h"
#include "SoftGateKeeper.h"

int main() {
    namespace ss = aidl::android::hardware::security::sharedsecret;
    namespace gk = aidl::android::hardware::gatekeeper;
    auto secret = ndk::SharedRefBase::make<ss::SoftSharedSecret>();
    ss::SharedSecretParameters params;
    assert(secret->getSharedSecretParameters(&params).isOk());
    ::keymaster::SoftKeymasterEnforcement enforcement(8, 8);
    ::keymaster::HmacSharingParameters km_params;
    assert(enforcement.GetHmacSharingParameters(&km_params) == KM_ERROR_OK);
    ss::SharedSecretParameters km_aidl;
    km_aidl.seed.assign(km_params.seed.data, km_params.seed.data + km_params.seed.data_length);
    km_aidl.nonce.assign(std::begin(km_params.nonce), std::end(km_params.nonce));
    std::vector<ss::SharedSecretParameters> participants = {params, km_aidl};
    std::sort(participants.begin(), participants.end(), [](const auto& a, const auto& b) {
        return a.seed != b.seed ? a.seed < b.seed : a.nonce < b.nonce;
    });
    std::vector<uint8_t> check;
    assert(secret->computeSharedSecret(participants, &check).isOk());
    assert(check.size() == 32);
    ::keymaster::HmacSharingParametersArray km_participants;
    km_participants.num_params = participants.size();
    km_participants.params_array = new ::keymaster::HmacSharingParameters[participants.size()];
    for (size_t i = 0; i < participants.size(); i++) {
        km_participants.params_array[i].seed = ::keymaster::KeymasterBlob(
            participants[i].seed.data(), participants[i].seed.size());
        std::copy(participants[i].nonce.begin(), participants[i].nonce.end(),
                  km_participants.params_array[i].nonce);
    }
    ::keymaster::KeymasterBlob km_check;
    assert(enforcement.ComputeSharedHmac(km_participants, &km_check) == KM_ERROR_OK);
    assert(km_check.data_length == check.size());
    assert(std::equal(check.begin(), check.end(), km_check.data));
    std::puts("GATEKEEPER_SOFTWARE_KEYMINT_SHARED_SECRET_PASS");
    ::gatekeeper::SoftGateKeeper implementation(*secret);
    assert(!implementation.IsHardwareBacked());
    auto device = ndk::SharedRefBase::make<gk::SoftGateKeeperDevice>(implementation);
    gk::GatekeeperEnrollResponse enrolled;
    const std::vector<uint8_t> password = {'t','e','s','t',0,'p','w'};
    assert(device->enroll(12345, {}, {}, password, &enrolled).isOk());
    assert(enrolled.statusCode == 0 && enrolled.secureUserId != 0 && !enrolled.data.empty());
    gk::GatekeeperVerifyResponse verified;
    assert(device->verify(12345, 0x12345678, enrolled.data, password, &verified).isOk());
    assert(verified.statusCode >= 0);
    assert(verified.hardwareAuthToken.challenge == 0x12345678);
    assert(verified.hardwareAuthToken.userId == enrolled.secureUserId);
    assert(verified.hardwareAuthToken.mac.size() == 32);
    assert(!device->verify(12345, 0, enrolled.data, {'w','r','o','n','g'}, &verified).isOk());
    // Fresh verification state exercises scrypt again, without the fast hash cache.
    ::gatekeeper::SoftGateKeeper fresh(*secret);
    auto fresh_device = ndk::SharedRefBase::make<gk::SoftGateKeeperDevice>(fresh);
    auto damaged = enrolled.data;
    damaged.at(offsetof(::gatekeeper::password_handle_t, signature)) ^= 0x80;
    assert(!fresh_device->verify(12345, 0, damaged, password, &verified).isOk());
    assert(fresh_device->verify(12345, 7, enrolled.data, password, &verified).isOk());
    assert(verified.hardwareAuthToken.challenge == 7);
    std::puts("GATEKEEPER_REAL_CREDENTIAL_TEST_PASS: correct password, wrong password, tampered handle, fresh state, signed challenge; hardware_backed=false");
}
