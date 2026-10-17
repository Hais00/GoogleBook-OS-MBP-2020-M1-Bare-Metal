// SPDX-License-Identifier: Apache-2.0
// Linux Type-C AIDL bridge. Protocol definitions come from frozen AOSP USB V3.
#define LOG_TAG "googlebook-usb-linux"
#include "usb_linux_typec.h"
#include <aidl/android/hardware/usb/BnUsb.h>
#include <aidl/android/hardware/usb/IUsbCallback.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>
#include <cutils/uevent.h>
#include <log/log.h>
#include <atomic>
#include <cerrno>
#include <mutex>
#include <poll.h>
#include <sys/eventfd.h>
#include <thread>
#include <unistd.h>

namespace {
namespace aidlusb = aidl::android::hardware::usb;
using namespace aidlusb;
using googlebook::usb::Result;
using googlebook::usb::Role;
using ndk::ScopedAStatus;

Status status(Result value) {
    if (value == Result::Ok) return Status::SUCCESS;
    if (value == Result::Unsupported) return Status::NOT_SUPPORTED;
    if (value == Result::Invalid) return Status::UNRECOGNIZED_ROLE;
    return Status::ERROR;
}

class LinuxUsb final : public BnUsb {
  public:
    explicit LinuxUsb(googlebook::usb::Typec typec = googlebook::usb::Typec()) : typec_(std::move(typec)) {
        stop_ = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
        events_ = uevent_open_socket(128 * 1024, true);
        if (stop_ >= 0 && events_ >= 0) {
            monitoring_ = true;
            worker_ = std::thread([this] { monitor(); });
        }
        else ALOGE("Type-C uevent listener unavailable: %s", strerror(errno));
    }
    ~LinuxUsb() override {
        if (worker_.joinable()) {
            uint64_t one = 1; (void)::write(stop_, &one, sizeof(one));
            worker_.join();
        }
        if (events_ >= 0) close(events_);
        if (stop_ >= 0) close(stop_);
    }
    bool ready() const { return monitoring_.load(); }
    ScopedAStatus setCallback(const std::shared_ptr<IUsbCallback>& value) override {
        if (value && !monitoring_) return ScopedAStatus::fromExceptionCode(EX_ILLEGAL_STATE);
        { std::lock_guard lock(callbackMutex_); callback_ = value; }
        // Keep one monitor for the service lifetime. Unregistering a callback
        // must not join a thread that is delivering that callback.
        if (value) notify(value);
        return ScopedAStatus::ok();
    }
    ScopedAStatus queryPortStatus(int64_t transaction) override {
        auto target = callback();
        if (!target) return ScopedAStatus::fromExceptionCode(EX_ILLEGAL_STATE);
        Status result = notify(target);
        return target->notifyQueryPortStatus("all", result, transaction);
    }
    ScopedAStatus switchRole(const std::string& port, const PortRole& requested, int64_t transaction) override {
        auto target = callback();
        if (!target) return ScopedAStatus::fromExceptionCode(EX_ILLEGAL_STATE);
        Role kind = Role::Mode; std::string value;
        switch (requested.getTag()) {
          case PortRole::powerRole:
            kind = Role::Power;
            if (requested.get<PortRole::powerRole>() == PortPowerRole::SOURCE) value = "source";
            if (requested.get<PortRole::powerRole>() == PortPowerRole::SINK) value = "sink";
            break;
          case PortRole::dataRole:
            kind = Role::Data;
            if (requested.get<PortRole::dataRole>() == PortDataRole::HOST) value = "host";
            if (requested.get<PortRole::dataRole>() == PortDataRole::DEVICE) value = "device";
            break;
          case PortRole::mode:
            if (requested.get<PortRole::mode>() == PortMode::UFP) value = "sink";
            if (requested.get<PortRole::mode>() == PortMode::DFP) value = "source";
            if (requested.get<PortRole::mode>() == PortMode::DRP) value = "dual";
            break;
        }
        Result result = Result::Invalid;
        {
            std::lock_guard lock(roleMutex_);
            if (!value.empty()) result = typec_.switchRole(port, kind, value);
        }
        auto reply = target->notifyRoleSwitchStatus(port, requested, status(result), transaction);
        notify(target);
        return reply;
    }
    ScopedAStatus enableUsbData(const std::string& port, bool enable, int64_t transaction) override {
        auto target = callback();
        if (!target) return ScopedAStatus::fromExceptionCode(EX_ILLEGAL_STATE);
        // No port-to-controller role-switch mapping has been qualified for
        // data gating. A successful store must never be fabricated here.
        return target->notifyEnableUsbDataStatus(port, enable, Status::NOT_SUPPORTED, transaction);
    }
    ScopedAStatus enableUsbDataWhileDocked(const std::string& port, int64_t transaction) override {
        auto target = callback();
        return target ? target->notifyEnableUsbDataWhileDockedStatus(port, Status::NOT_SUPPORTED, transaction)
                      : ScopedAStatus::fromExceptionCode(EX_ILLEGAL_STATE);
    }
    ScopedAStatus resetUsbPort(const std::string& port, int64_t transaction) override {
        auto target = callback();
        return target ? target->notifyResetUsbPortStatus(port, Status::NOT_SUPPORTED, transaction)
                      : ScopedAStatus::fromExceptionCode(EX_ILLEGAL_STATE);
    }
    ScopedAStatus limitPowerTransfer(const std::string& port, bool limit, int64_t transaction) override {
        auto target = callback();
        return target ? target->notifyLimitPowerTransferStatus(port, limit, Status::NOT_SUPPORTED, transaction)
                      : ScopedAStatus::fromExceptionCode(EX_ILLEGAL_STATE);
    }
    ScopedAStatus enableContaminantPresenceDetection(const std::string& port, bool enable, int64_t transaction) override {
        auto target = callback();
        return target ? target->notifyContaminantEnabledStatus(port, enable, Status::NOT_SUPPORTED, transaction)
                      : ScopedAStatus::fromExceptionCode(EX_ILLEGAL_STATE);
    }
  private:
    googlebook::usb::Typec typec_;
    std::mutex callbackMutex_, roleMutex_;
    std::shared_ptr<IUsbCallback> callback_;
    int events_{-1}, stop_{-1};
    std::atomic<bool> monitoring_{false};
    std::thread worker_;

    std::shared_ptr<IUsbCallback> callback() {
        std::lock_guard lock(callbackMutex_); return callback_;
    }
    Status notify(const std::shared_ptr<IUsbCallback>& target) {
        std::vector<googlebook::usb::Port> observed;
        Result result;
        { std::lock_guard lock(roleMutex_); result = typec_.query(&observed); }
        std::vector<PortStatus> output;
        if (result == Result::Ok) {
            for (const auto& port : observed) {
                PortStatus entry;
                entry.portName = port.name;
                entry.currentPowerRole = port.power == "source" ? PortPowerRole::SOURCE :
                                         port.power == "sink" ? PortPowerRole::SINK : PortPowerRole::NONE;
                entry.currentDataRole = port.data == "host" ? PortDataRole::HOST :
                                        port.data == "device" ? PortDataRole::DEVICE : PortDataRole::NONE;
                entry.currentMode = port.mode == "host" ? PortMode::DFP : port.mode == "device" ? PortMode::UFP :
                                    port.mode == "analog_audio" ? PortMode::AUDIO_ACCESSORY :
                                    port.mode == "debug" ? PortMode::DEBUG_ACCESSORY : PortMode::NONE;
                entry.canChangeMode = port.changeMode; entry.canChangeDataRole = port.changeData;
                entry.canChangePowerRole = port.changePower;
                if (port.dataModes.size() == 2) entry.supportedModes.push_back(PortMode::DRP);
                else entry.supportedModes.push_back(port.dataModes[0] == "host" ? PortMode::DFP : PortMode::UFP);
                for (const auto& accessory : port.accessories)
                    entry.supportedModes.push_back(accessory == "debug" ? PortMode::DEBUG_ACCESSORY : PortMode::AUDIO_ACCESSORY);
                entry.usbDataStatus = {UsbDataStatus::UNKNOWN};
                entry.supportedContaminantProtectionModes = {ContaminantProtectionMode::NONE};
                entry.contaminantProtectionStatus = ContaminantProtectionStatus::NONE;
                entry.contaminantDetectionStatus = ContaminantDetectionStatus::NOT_SUPPORTED;
                entry.supportsEnableContaminantPresenceDetection = false;
                entry.supportsEnableContaminantPresenceProtection = false;
                entry.supportsComplianceWarnings = false;
                output.push_back(std::move(entry));
            }
        }
        auto reply = target->notifyPortStatusChange(output, status(result));
        if (!reply.isOk()) ALOGE("Type-C callback failed: %s", reply.getDescription().c_str());
        return status(result);
    }
    void monitor() {
        pollfd fds[2] = {{stop_, POLLIN, 0}, {events_, POLLIN, 0}};
        for (;;) {
            int result = poll(fds, 2, -1);
            if (result < 0 && errno == EINTR) continue;
            if (fds[0].revents) { monitoring_ = false; return; }
            if (result <= 0 || (fds[1].revents & (POLLERR|POLLHUP|POLLNVAL))) {
                monitoring_ = false;
                auto target = callback();
                if (target) target->notifyPortStatusChange({}, Status::ERROR);
                ALOGE("Type-C uevent monitor stopped with an error");
                // Restart through init rather than retaining a registered
                // HAL that can no longer deliver kernel hotplug events.
                _exit(1);
            }
            if (!(fds[1].revents & POLLIN)) continue;
            char buffer[4096];
            ssize_t count = uevent_kernel_multicast_recv(events_, buffer, sizeof(buffer));
            if (count <= 0 || count == static_cast<ssize_t>(sizeof(buffer))) continue;
            std::string event(buffer, count);
            if (event.find("SUBSYSTEM=typec") == std::string::npos) continue;
            auto target = callback();
            if (target) notify(target);
        }
    }
};
}  // namespace

#ifndef GOOGLEBOOK_USB_UNIT_TEST
int main() {
    ABinderProcess_setThreadPoolMaxThreadCount(4);
    auto service = ndk::SharedRefBase::make<LinuxUsb>();
    if (!service->ready()) return 1;
    const std::string instance = std::string(aidl::android::hardware::usb::BnUsb::descriptor) + "/default";
    auto result = AServiceManager_addService(service->asBinder().get(), instance.c_str());
    if (result != STATUS_OK) { ALOGE("Cannot register USB service: %d", result); return 1; }
    ABinderProcess_joinThreadPool();
    return 1;
}
#endif
