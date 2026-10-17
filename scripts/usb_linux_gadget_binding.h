// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <functional>
#include <string>

namespace googlebook::usb {
enum class BindingResult { Ok, Missing, Invalid, Ambiguous, Unverified, Busy, IoError };
struct GadgetPaths {
    std::string controllers = "/sys/class/udc";
    std::string gadget = "/config/usb_gadget/g1";
    // Only explicit C++ test construction sets this. Production's default
    // paths require the real kernel filesystems; no property can bypass it.
    bool filesystemFixture = false;
};
bool isKernelFilesystem(const std::string& path,unsigned magic);
// Controls only the actual controller binding. Function links and FunctionFS
// readiness must be verified separately before declaring functions applied.
class GadgetBinding {
  public:
    using Writer = std::function<bool(const std::string&, const std::string&)>;
    explicit GadgetBinding(GadgetPaths paths = {}, Writer writer = {});
    BindingResult discover(std::string* controller, const std::string& preferred = "") const;
    BindingResult current(std::string* controller) const;
    BindingResult bind(const std::string& controller);
    BindingResult unbind();
    BindingResult speed(std::string* value) const;
    static bool validName(const std::string& name);
  private:
    GadgetPaths paths_;
    Writer writer_;
    bool eligible(const std::string& controller) const;
    bool read(const std::string& path, std::string* value) const;
    bool write(const std::string& value) const;
};
}  // namespace googlebook::usb
