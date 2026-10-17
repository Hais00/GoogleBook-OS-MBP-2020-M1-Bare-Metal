// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <chrono>
#include <functional>
#include <string>
#include <vector>

namespace googlebook::usb {
enum class Result { Ok, Missing, Invalid, Unsupported, IoError, Timeout };
enum class Role { Power, Data, Mode };
struct Choices {
    std::string selected;
    std::vector<std::string> available;
};
struct Port {
    std::string name, power, data, mode;
    bool connected{}, changePower{}, changeData{}, changeMode{};
    std::vector<std::string> dataModes, accessories;
};
class Typec {
  public:
    using Writer = std::function<bool(const std::string&, const std::string&)>;
    // Production uses the kernel-owned class. A separate root/writer is only
    // supplied by test programs; there is no property/environment override.
    explicit Typec(std::string root = "/sys/class/typec", Writer writer = {});
    Result query(std::vector<Port>* ports) const;
    Result switchRole(const std::string& port, Role role, const std::string& value,
                      std::chrono::milliseconds timeout = std::chrono::seconds(8));
    static bool validPortName(const std::string& name);
    static bool parseChoices(const std::string& text, Choices* choices);
  private:
    std::string root_;
    Writer writer_;
    Result names(std::vector<std::string>* names) const;
    Result snapshot(const std::string& name, Port* port) const;
    Result connected(const std::string& name, bool* state) const;
    bool read(const std::string& name, const std::string& file, std::string* value) const;
    bool writable(const std::string& path) const;
    bool write(const std::string& path, const std::string& value) const;
};
}  // namespace googlebook::usb
