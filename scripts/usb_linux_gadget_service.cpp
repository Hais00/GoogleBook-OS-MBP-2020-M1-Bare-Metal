// SPDX-License-Identifier: Apache-2.0
#define LOG_TAG "googlebook-usb-gadget-linux"
#include "usb_linux_gadget.h"
#include <aidl/android/hardware/usb/gadget/BnUsbGadget.h>
#include <aidl/android/hardware/usb/gadget/GadgetFunction.h>
#include <aidl/android/hardware/usb/gadget/IUsbGadgetCallback.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>
#include <log/log.h>
#include <atomic>
#include <mutex>
#include <thread>

namespace {
using namespace aidl::android::hardware::usb::gadget;
using googlebook::usb::GadgetResult;
using ndk::ScopedAStatus;
static_assert(GadgetFunction::ADB==googlebook::usb::function::Adb);
static_assert(GadgetFunction::MTP==googlebook::usb::function::Mtp);
static_assert(GadgetFunction::PTP==googlebook::usb::function::Ptp);
static_assert(GadgetFunction::RNDIS==googlebook::usb::function::Rndis);
static_assert(GadgetFunction::NCM==googlebook::usb::function::Ncm);
Status status(GadgetResult result) {
    if(result==GadgetResult::Ok)return Status::SUCCESS;
    if(result==GadgetResult::Unsupported)return Status::CONFIGURATION_NOT_SUPPORTED;
    return Status::ERROR;
}
class LinuxGadget final : public BnUsbGadget {
  public:
    explicit LinuxGadget(googlebook::usb::Gadget engine=googlebook::usb::Gadget()) : engine_(std::move(engine)) {
        engine_.adopt();
        monitor_=std::thread([this]{
            GadgetResult last=GadgetResult::Ok;
            while(!stop_) {
                GadgetResult result;
                {std::lock_guard lock(mutex_);result=engine_.reconcile();}
                if(result!=last && result!=GadgetResult::Ok && result!=GadgetResult::NotReady)
                    ALOGE("USB function monitor could not reconcile configfs state");
                last=result;
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
            }
        });
    }
    ~LinuxGadget() override {stop_=true;monitor_.join();}
    ScopedAStatus setCurrentUsbFunctions(int64_t functions,const std::shared_ptr<IUsbGadgetCallback>& callback,
                                        int64_t timeout,int64_t transaction) override {
        if(!callback)return ScopedAStatus::fromExceptionCode(EX_NULL_POINTER);
        GadgetResult result=GadgetResult::Invalid;
        if(functions>=0 && timeout>=0 && timeout<=30000) {
            std::lock_guard lock(mutex_);
            result=engine_.apply(static_cast<uint64_t>(functions),std::chrono::milliseconds(timeout));
        }
        return callback->setCurrentUsbFunctionsCb(functions,status(result),transaction);
    }
    ScopedAStatus getCurrentUsbFunctions(const std::shared_ptr<IUsbGadgetCallback>& callback,
                                        int64_t transaction) override {
        if(!callback)return ScopedAStatus::fromExceptionCode(EX_NULL_POINTER);
        googlebook::usb::GadgetState state;GadgetResult result;
        {std::lock_guard lock(mutex_);result=engine_.observe(&state);}
        Status observed=result!=GadgetResult::Ok?Status::ERROR:
                        state.applied?Status::FUNCTIONS_APPLIED:Status::FUNCTIONS_NOT_APPLIED;
        return callback->getCurrentUsbFunctionsCb(state.functions,observed,transaction);
    }
    ScopedAStatus getUsbSpeed(const std::shared_ptr<IUsbGadgetCallback>& callback,int64_t transaction) override {
        if(!callback)return ScopedAStatus::fromExceptionCode(EX_NULL_POINTER);
        UsbSpeed speed=UsbSpeed::UNKNOWN;std::string value;
        {
            std::lock_guard lock(mutex_);
            if(engine_.speed(&value)==googlebook::usb::BindingResult::Ok) {
                if(value=="low-speed")speed=UsbSpeed::LOWSPEED;
                else if(value=="full-speed")speed=UsbSpeed::FULLSPEED;
                else if(value=="high-speed")speed=UsbSpeed::HIGHSPEED;
                else if(value=="super-speed")speed=UsbSpeed::SUPERSPEED;
                else if(value=="super-speed-plus")speed=UsbSpeed::SUPERSPEED_10Gb;
            }
        }
        return callback->getUsbSpeedCb(speed,transaction);
    }
    ScopedAStatus reset(const std::shared_ptr<IUsbGadgetCallback>& callback,int64_t transaction) override {
        if(!callback)return ScopedAStatus::fromExceptionCode(EX_NULL_POINTER);
        GadgetResult result;
        {std::lock_guard lock(mutex_);result=engine_.reset(std::chrono::seconds(3));}
        return callback->resetCb(status(result),transaction);
    }
  private:
    googlebook::usb::Gadget engine_;
    std::mutex mutex_;
    std::atomic<bool> stop_{false};
    std::thread monitor_;
};
}
#ifndef GOOGLEBOOK_GADGET_UNIT_TEST
int main() {
    ABinderProcess_setThreadPoolMaxThreadCount(4);
    auto service=ndk::SharedRefBase::make<LinuxGadget>();
    const std::string instance=std::string(aidl::android::hardware::usb::gadget::BnUsbGadget::descriptor)+"/default";
    if(AServiceManager_addService(service->asBinder().get(),instance.c_str())!=STATUS_OK)return 1;
    ABinderProcess_joinThreadPool();return 1;
}
#endif
