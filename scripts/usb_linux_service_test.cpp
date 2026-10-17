// SPDX-License-Identifier: Apache-2.0
#define GOOGLEBOOK_USB_UNIT_TEST
#include "usb_linux_service.cpp"
#include <aidl/android/hardware/usb/BnUsbCallback.h>
#include <cassert>
#include <cstdio>
#include <filesystem>
#include <fstream>

namespace fs = std::filesystem;
struct Callback final : aidl::android::hardware::usb::BnUsbCallback {
    Status last{Status::ERROR}, query{Status::ERROR}, portStatus{Status::ERROR};
    bool boolean{}, unregisterOnce{};
    int64_t transaction{};
    std::vector<PortStatus> ports;
    std::weak_ptr<LinuxUsb> service;
    ScopedAStatus notifyPortStatusChange(const std::vector<PortStatus>& p, Status s) override {
        ports=p; portStatus=s;
        if (unregisterOnce) { unregisterOnce=false; assert(service.lock()->setCallback(nullptr).isOk()); }
        return ScopedAStatus::ok();
    }
    ScopedAStatus notifyRoleSwitchStatus(const std::string&, const PortRole&, Status s, int64_t t) override {
        last=s; transaction=t; return ScopedAStatus::ok();
    }
    ScopedAStatus notifyEnableUsbDataStatus(const std::string&, bool b, Status s, int64_t t) override {
        boolean=b; last=s; transaction=t; return ScopedAStatus::ok();
    }
    ScopedAStatus notifyEnableUsbDataWhileDockedStatus(const std::string&, Status s, int64_t t) override {
        last=s; transaction=t; return ScopedAStatus::ok();
    }
    ScopedAStatus notifyContaminantEnabledStatus(const std::string&, bool b, Status s, int64_t t) override {
        boolean=b; last=s; transaction=t; return ScopedAStatus::ok();
    }
    ScopedAStatus notifyQueryPortStatus(const std::string&, Status s, int64_t t) override {
        query=s; transaction=t; return ScopedAStatus::ok();
    }
    ScopedAStatus notifyLimitPowerTransferStatus(const std::string&, bool b, Status s, int64_t t) override {
        boolean=b; last=s; transaction=t; return ScopedAStatus::ok();
    }
    ScopedAStatus notifyResetUsbPortStatus(const std::string&, Status s, int64_t t) override {
        last=s; transaction=t; return ScopedAStatus::ok();
    }
};
static void put(const fs::path& p,const std::string& v) { fs::create_directories(p.parent_path()); std::ofstream(p)<<v; }
int main() {
    char pattern[]="/tmp/usb-aidl-test-XXXXXX"; char* made=mkdtemp(pattern); assert(made);
    fs::path root=made;
    put(root/"port2/data_role","[host] device"); put(root/"port2/power_role","[source] sink");
    put(root/"port2/port_type","source sink [dual]"); put(root/"port2-partner/accessory_mode","none");
    auto service=ndk::SharedRefBase::make<LinuxUsb>(googlebook::usb::Typec(root.string()));
    assert(service->ready());
    assert(!service->queryPortStatus(0).isOk());
    auto cb=ndk::SharedRefBase::make<Callback>(); cb->service=service; cb->unregisterOnce=true;
    assert(service->setCallback(cb).isOk()); // Reentrant unregister must not deadlock.
    assert(!service->queryPortStatus(1).isOk());
    assert(service->setCallback(cb).isOk());
    assert(service->queryPortStatus(2).isOk() && cb->query==Status::SUCCESS && cb->transaction==2);
    assert(cb->ports.size()==1 && cb->ports[0].portName=="port2");
    assert(cb->ports[0].usbDataStatus==std::vector<UsbDataStatus>{UsbDataStatus::UNKNOWN});
    assert(service->enableUsbData("port2",true,3).isOk() && cb->last==Status::NOT_SUPPORTED && cb->boolean);
    assert(service->enableUsbData("port2",false,4).isOk() && cb->last==Status::NOT_SUPPORTED && !cb->boolean);
    assert(service->resetUsbPort("port2",5).isOk() && cb->last==Status::NOT_SUPPORTED);
    assert(service->limitPowerTransfer("port2",true,6).isOk() && cb->last==Status::NOT_SUPPORTED && cb->boolean);
    assert(service->enableContaminantPresenceDetection("port2",false,7).isOk() && cb->last==Status::NOT_SUPPORTED);
    assert(service->enableUsbDataWhileDocked("port2",8).isOk() && cb->last==Status::NOT_SUPPORTED);
    PortRole role; role.set<PortRole::powerRole>(PortPowerRole::SINK);
    assert(service->switchRole("../port2",role,9).isOk() && cb->last!=Status::SUCCESS);
    assert(service->switchRole("port2",role,10).isOk() && cb->last==Status::SUCCESS && cb->transaction==10);
    fs::remove(root/"port2/power_role");
    assert(service->queryPortStatus(11).isOk() && cb->query==Status::ERROR && cb->ports.empty());
    assert(service->setCallback(nullptr).isOk());
    service.reset(); fs::remove_all(root);
    puts("USB_AIDL_BINDER_CALLBACK_TEST_PASS: real frozen V3 types, reentrant unregister, request correlation, explicit unsupported controls, failed query, observed role completion");
}
