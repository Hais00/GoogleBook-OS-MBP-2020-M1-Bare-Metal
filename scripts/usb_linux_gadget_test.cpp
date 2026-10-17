// SPDX-License-Identifier: Apache-2.0
#include "usb_linux_gadget.h"
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <unistd.h>
namespace fs=std::filesystem;
using namespace googlebook::usb;
static void put(const fs::path& p,const std::string& text){fs::create_directories(p.parent_path());std::ofstream(p)<<text;}
static void ready(const fs::path& root,const std::string& name,bool value) {
    put(root/"g1/functions"/name/"ready",value?"1":"0");
    auto shortName=name.substr(4);unsigned n=shortName=="adb"?2:3;
    for(unsigned i=1;i<=n;++i)put(root/"ffs"/shortName/("ep"+std::to_string(i)),"");
}
int main() {
    char pattern[]="/tmp/gadget-engine-test-XXXXXX";auto* made=mkdtemp(pattern);assert(made);fs::path root=made;
    GadgetPaths paths{(root/"udc").string(),(root/"g1").string(),true};
    for(const auto& n:{"UDC","idVendor","idProduct","bDeviceClass","bDeviceSubClass","bDeviceProtocol","os_desc/use","configs/b.1/strings/0x409/configuration"})put(root/"g1"/n,"");
    for(const auto& n:{"ffs.adb","ffs.mtp","ffs.ptp","rndis.gs4","ncm.gs6"})fs::create_directories(root/"g1/functions"/n);
    Gadget gadget(paths,(root/"ffs").string());GadgetState state;
    assert(gadget.apply(function::Adb,std::chrono::milliseconds(0))==GadgetResult::NotReady);
    fs::create_directories(root/"drivers/dwc3");fs::create_directories(root/"udc/real.usb/device");
    fs::create_directory_symlink(root/"drivers/dwc3",root/"udc/real.usb/device/driver");
    put(root/"udc/real.usb/current_speed","super-speed");
    ready(root,"ffs.adb",false); // Endpoints surviving alone are not descriptor readiness.
    assert(gadget.apply(function::Adb,std::chrono::milliseconds(0))==GadgetResult::NotReady);
    ready(root,"ffs.adb",true);
    assert(gadget.reconcile()==GadgetResult::Ok);
    assert(gadget.observe(&state)==GadgetResult::Ok && state.functions==0); // No late application after timeout.
    fs::remove(root/"ffs/adb/ep2");
    assert(gadget.apply(function::Adb,std::chrono::milliseconds(0))==GadgetResult::NotReady);
    ready(root,"ffs.adb",true);
    assert(gadget.apply(function::Adb,std::chrono::milliseconds(0))==GadgetResult::Ok);
    assert(gadget.observe(&state)==GadgetResult::Ok && state.applied && state.functions==function::Adb);
    assert(gadget.apply(function::Mtp|function::Ptp,std::chrono::milliseconds(0))==GadgetResult::Unsupported);
    assert(gadget.observe(&state)==GadgetResult::Ok && state.applied && state.functions==function::Adb);
    ready(root,"ffs.adb",false);
    assert(gadget.observe(&state)==GadgetResult::Ok && !state.applied);
    assert(gadget.reconcile()==GadgetResult::NotReady);
    std::string text;assert(GadgetBinding(paths).current(&text)==BindingResult::Ok && text.empty());
    ready(root,"ffs.adb",true);
    assert(gadget.reconcile()==GadgetResult::Ok && gadget.observe(&state)==GadgetResult::Ok && state.applied);
    ready(root,"ffs.mtp",true);
    assert(gadget.apply(function::Mtp|function::Adb,std::chrono::milliseconds(0))==GadgetResult::Ok);
    assert(gadget.observe(&state)==GadgetResult::Ok && state.functions==(function::Mtp|function::Adb) && state.applied);
    Gadget restarted(paths,(root/"ffs").string());assert(restarted.adopt()==GadgetResult::Ok);
    ready(root,"ffs.mtp",false);assert(restarted.reconcile()==GadgetResult::NotReady);
    ready(root,"ffs.mtp",true);assert(restarted.reconcile()==GadgetResult::Ok);
    assert(restarted.reset(std::chrono::milliseconds(0))==GadgetResult::Ok);
    bool sawUnbind=false;
    Gadget descriptorsIgnored(paths,(root/"ffs").string(),[&](const auto& p,const auto& value){
        if(p==paths.gadget+"/bDeviceClass")return true;
        if(p==paths.gadget+"/UDC" && value=="\n")sawUnbind=true;
        put(p,value);return true;
    });
    assert(descriptorsIgnored.apply(function::Ncm,std::chrono::milliseconds(0))==GadgetResult::IoError);
    assert(sawUnbind && GadgetBinding(paths).current(&text)==BindingResult::Ok && text.empty());
    Gadget bindingIgnored(paths,(root/"ffs").string(),[](const auto& p,const auto& value){
        if(p.substr(p.size()-4)=="/UDC" && value!="\n")return true;
        put(p,value);return true;
    });
    assert(bindingIgnored.apply(function::Ncm,std::chrono::milliseconds(0))==GadgetResult::IoError);
    assert(gadget.apply(function::Ncm,std::chrono::milliseconds(0))==GadgetResult::Ok);
    assert(gadget.apply(0,std::chrono::milliseconds(0))==GadgetResult::Ok);
    assert(gadget.observe(&state)==GadgetResult::Ok && state.applied && state.functions==0);
    fs::create_directory_symlink(root/"g1/functions/ncm.gs6",root/"g1/configs/b.1/.hidden");
    assert(gadget.observe(&state)==GadgetResult::Ok && state.functions==function::Ncm && !state.applied);
    fs::create_directories(root/"g1/functions/not-supported");
    fs::create_directory_symlink(root/"g1/functions/not-supported",root/"g1/configs/b.1/f9");
    assert(gadget.observe(&state)==GadgetResult::Unsupported && state.functions==0);
    fs::remove_all(root);
    std::cout<<"GADGET_ENGINE_FIXTURE_PASS: kernel readiness bit, endpoints, exact configuration, observed binding, descriptor failure, daemon restart, timeout, reset and hidden links; no hardware accessed\n";
}
