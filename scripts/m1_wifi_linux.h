// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstdint>
#include <string>
#include <vector>
namespace googlebook::wifi {
struct Interface { unsigned index=0, phy=0, type=0; std::string name; };
struct Limit { unsigned maximum=0; uint64_t types=0; };
struct Combination { unsigned maximum=0, channels=0; std::vector<Limit> limits; };
struct Channel { unsigned mhz=0; bool disabled=false, noInitiate=false, radar=false; };
struct Phy {
    unsigned index=0; uint64_t types=0; std::vector<Channel> channels;
    std::vector<Combination> combinations;
    std::vector<uint32_t> ciphers, akms;
    std::vector<unsigned char> extendedFeatures;
};
// All errors are negative errno. No sysfs fabrication or firmware-state files.
int interfaces(std::vector<Interface>& out);
int physicalRadio(unsigned index, Phy& out);
int nativeRadio(Interface& primary, Phy& phy);
int createInterface(unsigned phy, const std::string& name, unsigned type);
int deleteInterface(unsigned index);
int setCountry(const char country[2]);
int setInterfaceUp(const std::string& name, bool up);
bool safeName(const std::string& name);
}
