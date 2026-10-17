// SPDX-License-Identifier: Apache-2.0
#include "usb_linux_gadget_binding.h"
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <unistd.h>
namespace fs=std::filesystem;
using namespace googlebook::usb;
static void put(const fs::path& p,const std::string& value) { fs::create_directories(p.parent_path()); std::ofstream(p)<<value; }
static void device(const fs::path& root,const std::string& name,const std::string& driver) {
    fs::create_directories(root/"drivers"/driver); fs::create_directories(root/"udc"/name/"device");
    fs::create_directory_symlink(root/"drivers"/driver,root/"udc"/name/"device/driver");
    put(root/"udc"/name/"current_speed","super-speed\n");
}
int main() {
    char pattern[]="/tmp/gadget-binding-test-XXXXXX"; auto* made=mkdtemp(pattern); assert(made); fs::path root=made;
    GadgetPaths paths{(root/"udc").string(),(root/"g1").string(),true};
    GadgetPaths checked=paths;checked.filesystemFixture=false;
    std::string rejected;
    assert(GadgetBinding(checked).current(&rejected)==BindingResult::Unverified);
    GadgetBinding gadget(paths); std::string name;
    assert(gadget.discover(&name)==BindingResult::Missing && name.empty());
    device(root,"dummy_udc.0","dummy_udc");
    assert(gadget.discover(&name)==BindingResult::Missing && name.empty());
    device(root,"382000000.usb","dwc3");
    assert(GadgetBinding(checked).discover(&rejected)==BindingResult::Unverified);
    assert(gadget.discover(&name)==BindingResult::Ok && name=="382000000.usb");
    assert(gadget.discover(&name,"dummy_udc.0")==BindingResult::Unverified);
    assert(gadget.discover(&name,"../382000000.usb")==BindingResult::Invalid);
    put(root/"g1/UDC","");
    assert(gadget.bind("dummy_udc.0")==BindingResult::Unverified);
    assert(gadget.bind("382000000.usb")==BindingResult::Ok);
    assert(gadget.current(&name)==BindingResult::Ok && name=="382000000.usb");
    assert(gadget.speed(&name)==BindingResult::Ok && name=="super-speed");
    unsigned writes=0;
    GadgetBinding ignored(paths,[&](const auto&,const auto& value){ ++writes; assert(value=="\n"); return true; });
    assert(ignored.unbind()==BindingResult::IoError && writes==1);
    assert(gadget.unbind()==BindingResult::Ok && gadget.current(&name)==BindingResult::Ok && name.empty());
    assert(gadget.speed(&name)==BindingResult::Missing && name.empty());
    GadgetBinding ignoredBind(paths,[](const auto&,const auto&){return true;});
    assert(ignoredBind.bind("382000000.usb")==BindingResult::IoError);
    device(root,"582000000.usb","dwc3");
    assert(gadget.discover(&name)==BindingResult::Ambiguous && name.empty());
    assert(gadget.discover(&name,"582000000.usb")==BindingResult::Ok && name=="582000000.usb");
    assert(gadget.bind("582000000.usb")==BindingResult::Ok);
    assert(gadget.bind("382000000.usb")==BindingResult::Busy);
    fs::remove_all(root);
    std::cout<<"GADGET_CONFIGFS_BINDING_FIXTURE_PASS: controller selection, dummy rejection, ambiguity, checked bind/unbind and speed; filesystem fixture only, no USB hardware accessed\n";
}
