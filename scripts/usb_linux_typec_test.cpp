// SPDX-License-Identifier: Apache-2.0
#include "usb_linux_typec.h"
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sys/stat.h>
#include <unistd.h>

using namespace googlebook::usb;
namespace fs = std::filesystem;
static void put(const fs::path& path, const std::string& text) {
    fs::create_directories(path.parent_path()); std::ofstream(path) << text;
}
static void port(const fs::path& root, const std::string& name, bool connected) {
    put(root/name/"data_role", "[host] device\n");
    put(root/name/"power_role", "[source] sink\n");
    put(root/name/"port_type", "source sink [dual]\n");
    put(root/name/"supported_accessory_modes", "analog_audio debug\n");
    if (connected) put(root/(name+"-partner")/"accessory_mode", "none\n");
}
int main() {
    char pattern[] = "/tmp/googlebook-typec-test-XXXXXX";
    const fs::path root = mkdtemp(pattern); assert(!root.empty());
    for (const auto& name : {"port0", "port2", "port2147483647"}) assert(Typec::validPortName(name));
    for (const auto& name : {"", "port", "port00", "port-1", "port2147483648", "port0/../../x", "port2-partner", "port0-cable", "port0.0"})
        assert(!Typec::validPortName(name));
    Choices choices;
    assert(Typec::parseChoices("source [sink]", &choices) && choices.selected=="sink");
    for (const auto& value : {"", "source sink", "[source] [sink]", "[]", "[host", "[host] host"})
        assert(!Typec::parseChoices(value, &choices));
    Typec missing((root/"absent").string()); std::vector<Port> values;
    assert(missing.query(&values)==Result::Missing && values.empty());
    port(root,"port2",true); port(root,"port10",false); port(root,"port4",false);
    fs::create_directories(root/"port2-cable"); fs::create_directories(root/"port2.0");
    Typec backend(root.string());
    assert(backend.query(&values)==Result::Ok && values.size()==3);
    assert(values[0].name=="port2" && values[1].name=="port4" && values[2].name=="port10");
    assert(values[0].connected && values[0].data=="host" && values[0].power=="source");
    assert(values[0].changeData && values[0].changePower && values[0].changeMode);
    assert(!values[1].connected && values[1].data.empty() && !values[1].changeData);
    chmod((root/"port2/data_role").c_str(),0444);
    assert(backend.query(&values)==Result::Ok && !values[0].changeData);
    chmod((root/"port2/data_role").c_str(),0644);
    unsigned writes=0;
    Typec unapplied(root.string(),[&](const auto&,const auto&){ ++writes; return true; });
    assert(unapplied.switchRole("../port2",Role::Power,"sink")==Result::Invalid && writes==0);
    assert(unapplied.switchRole("port2",Role::Power,"none")==Result::Invalid && writes==0);
    assert(unapplied.switchRole("port9",Role::Power,"sink")==Result::Missing && writes==0);
    assert(unapplied.switchRole("port2",Role::Power,"sink",std::chrono::milliseconds(30))==Result::Timeout);
    assert(writes==1); // An accepted store is not proof of a completed switch.
    Typec failed(root.string(),[](const auto&,const auto&){ return false; });
    assert(failed.switchRole("port2",Role::Power,"sink")==Result::IoError);
    Typec otherPartner(root.string(),[&](const auto&,const auto&){
        put(root/"port10-partner/accessory_mode","none\n"); return true;
    });
    assert(otherPartner.switchRole("port2",Role::Mode,"source",std::chrono::milliseconds(30))==Result::Timeout);
    Typec applied(root.string(),[&](const auto& path,const auto& value){
        if (path==(root/"port2/power_role").string()) put(path,value=="sink"?"source [sink]":"[source] sink");
        else return false;
        return true;
    });
    assert(applied.switchRole("port2",Role::Power,"sink")==Result::Ok);
    assert(applied.query(&values)==Result::Ok && values[0].power=="sink");
    put(root/"port2/data_role","host device\n");
    assert(backend.query(&values)==Result::IoError && values.empty());
    fs::remove_all(root);
    std::cout << "TYPEC_OWNER_READBACK_TEST_PASS: actual ports, capabilities, invalid paths, failed/unchanged stores, unrelated events, confirmed transition\n";
}
