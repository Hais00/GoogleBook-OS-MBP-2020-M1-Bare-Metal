// SPDX-License-Identifier: Apache-2.0
#include "m1_lights.h"
#include <cerrno>
#include <climits>
#include <cctype>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <dirent.h>
#include <fcntl.h>
#include <linux/magic.h>
#include <sys/vfs.h>
#include <unistd.h>

namespace googlebook {
int M1Lights::read(const std::string& path, std::string* value) const {
    int fd = open(path.c_str(), O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -errno;
    struct statfs fs{};
    if (!testFilesystem_) {
        if (fstatfs(fd, &fs)) { int error = errno; close(fd); return -error; }
        if (fs.f_type != SYSFS_MAGIC) { close(fd); return -ENODEV; }
    }
    char buffer[1024];
    ssize_t n;
    do { n = ::read(fd, buffer, sizeof(buffer)); } while (n < 0 && errno == EINTR);
    int error = errno;
    close(fd);
    if (n < 0) return -error;
    if (!n || n == static_cast<ssize_t>(sizeof(buffer))) return -ENODATA;
    value->assign(buffer, static_cast<size_t>(n));
    return 0;
}

int M1Lights::number(const std::string& path, int* value) const {
    std::string text;
    int result = read(path, &text);
    if (result) return result;
    errno = 0;
    char* end = nullptr;
    long n = strtol(text.c_str(), &end, 10);
    if (errno || end == text.c_str() || n < 0 || n > INT_MAX) return -ERANGE;
    while (*end && std::isspace(static_cast<unsigned char>(*end))) ++end;
    if (*end) return -EINVAL;
    *value = static_cast<int>(n);
    return 0;
}

int M1Lights::add(std::vector<M1Light>* lights, int id, int type, const std::string& directory) {
    int dir = open(directory.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (dir < 0) return -errno;
    close(dir);
    int maximum, brightness;
    int result = number(directory+"/max_brightness", &maximum);
    if (result) return result;
    result = number(directory+"/brightness", &brightness);
    if (result) return result;
    if (!maximum || brightness > maximum) return -ERANGE;
    lights->push_back({id, type, directory, maximum});
    return 0;
}

int M1Lights::discover(std::vector<M1Light>* lights) {
    lights->clear();
    issues_.clear();
    if (!testFilesystem_) {
        int fd = open(root_.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        if (fd < 0) return -errno;
        struct statfs fs{};
        int stat_error = fstatfs(fd, &fs) ? errno : 0;
        close(fd);
        if (stat_error) return -stat_error;
        if (fs.f_type != SYSFS_MAGIC) return -ENODEV;
    }
    int result = add(lights, 0, 0, root_+"/class/backlight/apple-panel-bl");
    if (result) issues_[0] = result;
    // This label is declared by the actual J293 PWM LED device tree.
    result = add(lights, 1, 1, root_+"/class/leds/kbd_backlight");
    if (result) issues_[1] = result;
    std::string base = root_+"/class/backlight";
    DIR* directory = opendir(base.c_str());
    if (!directory) { issues_[2] = -errno; return 0; }
    int found = 0;
    result = 0;
    for (;;) {
        errno = 0;
        dirent* entry = readdir(directory);
        if (!entry) { if (errno) issues_[2] = -errno; break; }
        if (entry->d_name[0] == '.') continue;
        std::string path = base+"/"+entry->d_name;
        if (path == root_+"/class/backlight/apple-panel-bl") continue;
        // The kernel's bound driver is the owner identity. Reading the
        // device-tree SoC subtree is unnecessary for this backlight API.
        char driver[4096];
        ssize_t length = readlink((path+"/device/driver").c_str(), driver, sizeof(driver));
        if (length < 0) {
            if (errno == ENOENT) continue;
            issues_[2] = -errno; break;
        }
        if (length == static_cast<ssize_t>(sizeof(driver))) { issues_[2] = -ENAMETOOLONG; break; }
        std::string binding(driver, static_cast<size_t>(length));
        bool summit = binding.substr(binding.find_last_of('/')+1) == "panel-summit";
        if (summit) {
            if (++found > 1) { issues_[2] = -EEXIST; break; }
            result = add(lights, 2, 2, path);
            if (result) { issues_[2] = result; break; }
        }
    }
    closedir(directory);
    if (!found && !issues_.count(2)) issues_[2] = -ENOENT;
    if (issues_.count(2)) {
        for (auto it = lights->begin(); it != lights->end();) {
            if (it->id == 2) it = lights->erase(it);
            else ++it;
        }
    }
    return 0;
}

int M1Lights::enumerate(std::vector<M1Light>* lights, std::map<int, int>* issues) {
    if (!lights) return -EINVAL;
    std::lock_guard<std::mutex> lock(mutex_);
    int result = discover(lights);
    if (result) lights->clear();
    if (issues) *issues = issues_;
    return result;
}

int M1Lights::set(int id, unsigned color) {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<M1Light> lights;
    int result = discover(&lights);
    if (result) return result;
    for (const auto& light : lights) {
        if (light.id != id) continue;
        unsigned brightness = (77*((color>>16)&255)+150*((color>>8)&255)+29*(color&255))>>8;
        int requested = static_cast<int>((uint64_t(brightness)*light.maximum+127)/255);
        std::string path = light.directory+"/brightness";
        int fd = open(path.c_str(), O_WRONLY | O_CLOEXEC | (testFilesystem_ ? O_TRUNC : 0));
        if (fd < 0) return -errno;
        struct statfs fs{};
        if (!testFilesystem_) {
            if (fstatfs(fd, &fs)) { int error = errno; close(fd); return -error; }
            if (fs.f_type != SYSFS_MAGIC) { close(fd); return -ENODEV; }
        }
        std::string value = std::to_string(requested)+"\n";
        ssize_t written;
        do { written = write(fd, value.data(), value.size()); } while (written < 0 && errno == EINTR);
        int error = errno;
        close(fd);
        if (written < 0) return -error;
        if (static_cast<size_t>(written) != value.size()) return -EIO;
        int observed;
        result = number(path, &observed);
        if (result) return result;
        return observed == requested ? 0 : -EIO;
    }
    auto issue = issues_.find(id);
    return issue == issues_.end() ? -ENOENT : issue->second;
}
}
