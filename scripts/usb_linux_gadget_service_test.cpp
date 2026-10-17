// SPDX-License-Identifier: Apache-2.0
#define GOOGLEBOOK_GADGET_UNIT_TEST
#include "usb_linux_gadget_service.cpp"
#include <aidl/android/hardware/usb/gadget/BnUsbGadgetCallback.h>
#include <cassert>
#include <filesystem>
#include <fstream>
#include <cstdio>
namespace fs=std::filesystem;
struct Callback final : aidl::android::hardware::usb::gadget::BnUsbGadgetCallback {
    Status last{Status::ERROR};UsbSpeed speed{UsbSpeed::UNKNOWN};int64_t functions{},transaction{};
    ScopedAStatus setCurrentUsbFunctionsCb(int64_t f,Status s,int64_t t) override {
        functions=f;last=s;transaction=t;return ScopedAStatus::ok();
    }
    ScopedAStatus getCurrentUsbFunctionsCb(int64_t f,Status s,int64_t t) override {
        functions=f;last=s;transaction=t;return ScopedAStatus::ok();
    }
    ScopedAStatus getUsbSpeedCb(UsbSpeed s,int64_t t) override {speed=s;transaction=t;return ScopedAStatus::ok();}
    ScopedAStatus resetCb(Status s,int64_t t) override {last=s;transaction=t;return ScopedAStatus::ok();}
};
static void put(const fs::path& p,const std::string& v){fs::create_directories(p.parent_path());std::ofstream(p)<<v;}
int main() {
    char pattern[]="/tmp/usb-gadget-aidl-test-XXXXXX";auto* made=mkdtemp(pattern);assert(made);fs::path root=made;
    googlebook::usb::GadgetPaths paths{(root/"udc").string(),(root/"g1").string(),true};
    for(const auto* n:{"UDC","idVendor","idProduct","bDeviceClass","bDeviceSubClass","bDeviceProtocol","os_desc/use","configs/b.1/strings/0x409/configuration"})put(root/"g1"/n,"");
    put(root/"g1/functions/ffs.adb/ready","0");
    put(root/"ffs/adb/ep1","");put(root/"ffs/adb/ep2","");
    auto cb=ndk::SharedRefBase::make<Callback>();
    auto service=ndk::SharedRefBase::make<LinuxGadget>(googlebook::usb::Gadget(paths,(root/"ffs").string()));
    assert(!service->getCurrentUsbFunctions(nullptr,0).isOk());
    assert(service->setCurrentUsbFunctions(GadgetFunction::ADB,cb,0,1).isOk() && cb->last==Status::ERROR);
    fs::create_directories(root/"drivers/dwc3");fs::create_directories(root/"udc/real.usb/device");
    fs::create_directory_symlink(root/"drivers/dwc3",root/"udc/real.usb/device/driver");
    put(root/"udc/real.usb/current_speed","high-speed");
    assert(service->setCurrentUsbFunctions(GadgetFunction::ADB,cb,0,2).isOk() && cb->last==Status::ERROR);
    put(root/"g1/functions/ffs.adb/ready","1");
    assert(service->setCurrentUsbFunctions(GadgetFunction::ADB,cb,0,3).isOk() && cb->last==Status::SUCCESS && cb->transaction==3);
    assert(service->getCurrentUsbFunctions(cb,4).isOk() && cb->last==Status::FUNCTIONS_APPLIED && cb->functions==GadgetFunction::ADB);
    assert(service->getUsbSpeed(cb,5).isOk() && cb->speed==UsbSpeed::HIGHSPEED && cb->transaction==5);
    assert(service->setCurrentUsbFunctions(GadgetFunction::MIDI,cb,0,6).isOk() && cb->last==Status::CONFIGURATION_NOT_SUPPORTED);
    assert(service->setCurrentUsbFunctions(GadgetFunction::ADB,cb,-1,7).isOk() && cb->last==Status::ERROR);
    assert(service->reset(cb,8).isOk() && cb->last==Status::SUCCESS);
    put(root/"g1/functions/ffs.adb/ready","0");
    assert(service->getCurrentUsbFunctions(cb,9).isOk() && cb->last==Status::FUNCTIONS_NOT_APPLIED);
    std::string current;
    auto binding=googlebook::usb::GadgetBinding(paths);
    auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(2);
    while(binding.current(&current)==googlebook::usb::BindingResult::Ok && !current.empty() && std::chrono::steady_clock::now()<deadline)
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    assert(current.empty());
    put(root/"g1/functions/ffs.adb/ready","1");
    deadline=std::chrono::steady_clock::now()+std::chrono::seconds(2);
    while(binding.current(&current)==googlebook::usb::BindingResult::Ok && current.empty() && std::chrono::steady_clock::now()<deadline)
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    assert(current=="real.usb");
    assert(service->setCurrentUsbFunctions(0,cb,0,10).isOk() && cb->last==Status::SUCCESS);
    service.reset();
    paths.filesystemFixture=false;
    auto guarded=ndk::SharedRefBase::make<LinuxGadget>(googlebook::usb::Gadget(paths,(root/"ffs").string()));
    assert(guarded->setCurrentUsbFunctions(GadgetFunction::ADB,cb,0,11).isOk() && cb->last!=Status::SUCCESS);
    assert(guarded->getCurrentUsbFunctions(cb,12).isOk() && cb->last==Status::ERROR);
    guarded.reset();fs::remove_all(root);
    puts("GADGET_AIDL_CALLBACK_FIXTURE_PASS: real frozen V1 callback types, absent controller, stale endpoints, kernel ready bit, apply/query/speed/reset, daemon restart, timeout and ordinary-filesystem rejection; no USB hardware accessed");
}
