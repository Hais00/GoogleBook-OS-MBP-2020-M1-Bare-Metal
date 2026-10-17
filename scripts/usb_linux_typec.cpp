// SPDX-License-Identifier: Apache-2.0
#include "usb_linux_typec.h"
#include <algorithm>
#include <cerrno>
#include <climits>
#include <dirent.h>
#include <fcntl.h>
#include <sstream>
#include <sys/stat.h>
#include <thread>
#include <unistd.h>

namespace googlebook::usb {
namespace {
bool contains(const std::vector<std::string>& values, const std::string& value) {
    return std::find(values.begin(), values.end(), value) != values.end();
}
bool readFile(const std::string& path, std::string* value) {
    int fd = open(path.c_str(), O_RDONLY | O_CLOEXEC);
    if (fd < 0) return false;
    char data[1025]; ssize_t count;
    do { count = ::read(fd, data, sizeof(data)); } while (count < 0 && errno == EINTR);
    int error = errno; close(fd); errno = error;
    if (count <= 0 || count == static_cast<ssize_t>(sizeof(data))) return false;
    value->assign(data, count);
    return true;
}
}

Typec::Typec(std::string root, Writer writer) : root_(std::move(root)), writer_(std::move(writer)) {}

bool Typec::validPortName(const std::string& name) {
    if (name.size() < 5 || name.compare(0, 4, "port") != 0) return false;
    if (name.size() > 5 && name[4] == '0') return false;
    unsigned number = 0;
    for (size_t i = 4; i < name.size(); ++i) {
        unsigned digit = static_cast<unsigned char>(name[i]) - '0';
        if (digit > 9 || number > (INT_MAX - digit) / 10) return false;
        number = number * 10 + digit;
    }
    return true;
}

bool Typec::parseChoices(const std::string& text, Choices* choices) {
    *choices = {};
    std::istringstream input(text); std::string token; unsigned selected = 0;
    while (input >> token) {
        bool bracketed = token.front() == '[' && token.back() == ']';
        if (bracketed) token = token.substr(1, token.size() - 2);
        if (token.empty() || token.find_first_of("[]") != std::string::npos ||
            contains(choices->available, token)) return false;
        choices->available.push_back(token);
        if (bracketed) { choices->selected = token; ++selected; }
    }
    if (selected == 0 && choices->available.size() == 1) {
        choices->selected = choices->available[0]; selected = 1;
    }
    return selected == 1;
}

bool Typec::read(const std::string& name, const std::string& file, std::string* value) const {
    return validPortName(name) && readFile(root_ + "/" + name + "/" + file, value);
}

bool Typec::writable(const std::string& path) const {
    struct stat info;
    // Root's DAC override must not turn a kernel read-only attribute into a
    // claimed switching capability. Type-C removes write bits for absent ops.
    return stat(path.c_str(), &info) == 0 &&
           (info.st_mode & (S_IWUSR | S_IWGRP | S_IWOTH)) && access(path.c_str(), W_OK) == 0;
}

bool Typec::write(const std::string& path, const std::string& value) const {
    if (writer_) return writer_(path, value);
    int fd = open(path.c_str(), O_WRONLY | O_CLOEXEC | O_TRUNC);
    if (fd < 0) return false;
    ssize_t count;
    do { count = ::write(fd, value.data(), value.size()); } while (count < 0 && errno == EINTR);
    int error = errno; int closed = close(fd); errno = error;
    return count == static_cast<ssize_t>(value.size()) && closed == 0;
}

Result Typec::connected(const std::string& name, bool* state) const {
    if (!validPortName(name)) return Result::Invalid;
    struct stat info;
    if (stat((root_ + "/" + name + "-partner").c_str(), &info) == 0) {
        *state = S_ISDIR(info.st_mode); return *state ? Result::Ok : Result::IoError;
    }
    if (errno != ENOENT) return Result::IoError;
    *state = false; return Result::Ok;
}

Result Typec::names(std::vector<std::string>* output) const {
    output->clear(); DIR* directory = opendir(root_.c_str());
    if (!directory) return errno == ENOENT ? Result::Missing : Result::IoError;
    errno = 0;
    while (auto* entry = readdir(directory)) {
        if (!validPortName(entry->d_name)) continue;
        struct stat info;
        if (stat((root_ + "/" + entry->d_name).c_str(), &info) != 0) {
            closedir(directory); return Result::IoError;
        }
        if (S_ISDIR(info.st_mode)) output->emplace_back(entry->d_name);
        errno = 0;
    }
    int error = errno; closedir(directory);
    if (error) return Result::IoError;
    std::sort(output->begin(), output->end(), [](const auto& a, const auto& b) {
        return a.size() != b.size() ? a.size() < b.size() : a < b;
    });
    return Result::Ok;
}

Result Typec::snapshot(const std::string& name, Port* port) const {
    *port = {}; port->name = name;
    auto result = connected(name, &port->connected);
    if (result != Result::Ok) return result;
    std::string text; Choices data, power, mode;
    if (!read(name, "data_role", &text) || !parseChoices(text, &data) ||
        !read(name, "power_role", &text) || !parseChoices(text, &power) ||
        !read(name, "port_type", &text) || !parseChoices(text, &mode)) return Result::IoError;
    for (const auto& value : data.available)
        if (value != "host" && value != "device") return Result::Invalid;
    for (const auto& value : power.available)
        if (value != "source" && value != "sink") return Result::Invalid;
    for (const auto& value : mode.available)
        if (value != "source" && value != "sink" && value != "dual") return Result::Invalid;
    port->dataModes = data.available;
    port->changeMode = mode.available.size() > 1 && writable(root_ + "/" + name + "/port_type");
    port->changeData = port->connected && data.available.size() > 1 &&
                       writable(root_ + "/" + name + "/data_role");
    port->changePower = port->connected && power.available.size() > 1 &&
                        writable(root_ + "/" + name + "/power_role");
    if (read(name, "supported_accessory_modes", &text)) {
        std::istringstream input(text); std::string accessory;
        while (input >> accessory) {
            if (accessory == "analog_audio" || accessory == "debug") port->accessories.push_back(accessory);
            else if (accessory != "none") return Result::Invalid;
        }
    }
    if (port->connected) {
        port->power = power.selected; port->data = data.selected;
        if (!readFile(root_ + "/" + name + "-partner/accessory_mode", &text)) return Result::IoError;
        Choices accessory;
        if (!parseChoices(text, &accessory)) return Result::Invalid;
        if (accessory.selected == "analog_audio" || accessory.selected == "debug")
            port->mode = accessory.selected;
        else if (accessory.selected == "none") port->mode = data.selected;
        else return Result::Invalid;
    }
    bool after;
    if (connected(name, &after) != Result::Ok || after != port->connected) return Result::IoError;
    return Result::Ok;
}

Result Typec::query(std::vector<Port>* ports) const {
    ports->clear(); std::vector<std::string> before, after;
    auto result = names(&before);
    if (result != Result::Ok) return result;
    for (const auto& name : before) {
        Port port; result = snapshot(name, &port);
        if (result != Result::Ok) { ports->clear(); return result; }
        ports->push_back(std::move(port));
    }
    if (names(&after) != Result::Ok || before != after) { ports->clear(); return Result::IoError; }
    return Result::Ok;
}

Result Typec::switchRole(const std::string& name, Role role, const std::string& value,
                         std::chrono::milliseconds timeout) {
    if (!validPortName(name) || timeout.count() < 0) return Result::Invalid;
    if (role != Role::Power && role != Role::Data && role != Role::Mode) return Result::Invalid;
    const char* file = role == Role::Power ? "power_role" : role == Role::Data ? "data_role" : "port_type";
    if ((role == Role::Power && value != "source" && value != "sink") ||
        (role == Role::Data && value != "host" && value != "device") ||
        (role == Role::Mode && value != "source" && value != "sink" && value != "dual")) return Result::Invalid;
    std::vector<std::string> ports;
    auto result = names(&ports);
    if (result != Result::Ok) return result;
    if (!contains(ports, name)) return Result::Missing;
    std::string text; Choices choices;
    if (!read(name, file, &text) || !parseChoices(text, &choices)) return Result::IoError;
    if (!contains(choices.available, value)) return Result::Unsupported;
    const std::string path = root_ + "/" + name + "/" + file;
    auto matches = [&]() {
        std::string now; Choices current;
        if (!read(name, file, &now) || !parseChoices(now, &current) || current.selected != value) return false;
        if (role == Role::Mode && value == "dual") return true;
        bool linked;
        if (connected(name, &linked) != Result::Ok || !linked) return false;
        if (role == Role::Mode) {
            if (!read(name, "data_role", &now) || !parseChoices(now, &current)) return false;
            return current.selected == (value == "source" ? "host" : "device");
        }
        return true;
    };
    if (matches()) return Result::Ok;
    if (!writable(path)) return Result::Unsupported;
    if (!write(path, value)) return Result::IoError;
    const auto deadline = std::chrono::steady_clock::now() + timeout;
    do {
        if (matches()) return Result::Ok;
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    } while (std::chrono::steady_clock::now() < deadline);
    // Restore only the previous mode setting, rather than forcing every
    // disconnected port to DRP as a side effect of an unrelated hotplug.
    if (role == Role::Mode) write(path, choices.selected);
    return Result::Timeout;
}
}  // namespace googlebook::usb
