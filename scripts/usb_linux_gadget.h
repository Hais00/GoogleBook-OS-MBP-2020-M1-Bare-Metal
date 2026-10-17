// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "usb_linux_gadget_binding.h"
#include <chrono>
#include <cstdint>
#include <string>
#include <vector>

namespace googlebook::usb {
namespace function {
constexpr uint64_t Adb=1, Mtp=4, Ptp=16, Rndis=32, Ncm=1024;
}
enum class GadgetResult { Ok, Unsupported, Invalid, NotReady, IoError };
struct GadgetState { uint64_t functions{}; bool applied{}; };
struct FunctionConfig {
    uint64_t functions{};
    unsigned product{};
    bool network{};
    std::string description;
    std::vector<std::string> instances;
};
class Gadget {
  public:
    explicit Gadget(GadgetPaths paths={}, std::string ffs="/dev/usb-ffs",
                    GadgetBinding::Writer writer={});
    static bool configuration(uint64_t functions,FunctionConfig* result);
    GadgetResult apply(uint64_t functions,std::chrono::milliseconds timeout);
    GadgetResult reset(std::chrono::milliseconds timeout);
    GadgetResult observe(GadgetState* state) const;
    GadgetResult adopt();
    // Retains a successful request across a FunctionFS daemon restart.
    // It never applies a previously failed/timed-out request later.
    GadgetResult reconcile();
    BindingResult speed(std::string* value) const { return binding_.speed(value); }
  private:
    GadgetPaths paths_;
    std::string ffs_;
    GadgetBinding::Writer writer_;
    GadgetBinding binding_;
    bool live_{};
    uint64_t desired_{};
    std::string controller_;
    bool write(const std::string& path,const std::string& value) const;
    bool read(const std::string& path,std::string* value) const;
    bool integer(const std::string& path,unsigned value) const;
    bool links(std::vector<std::string>* names) const;
    bool clearLinks() const;
    bool installLinks(const FunctionConfig& config) const;
    bool endpointsReady(const FunctionConfig& config) const;
    GadgetResult waitAndBind(const FunctionConfig& config,std::chrono::milliseconds timeout);
};
}  // namespace googlebook::usb
