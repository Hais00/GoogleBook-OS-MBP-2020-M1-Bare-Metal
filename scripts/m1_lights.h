// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <mutex>
#include <string>
#include <vector>
#include <map>
#include <utility>

namespace googlebook {
struct M1Light {
    int id;
    int type;
    std::string directory;
    int maximum;
};

// Kernel LED/backlight owner. The production factory always uses real sysfs.
class M1Lights {
public:
    explicit M1Lights(std::string root = "/sys", bool testFilesystem = false)
        : root_(std::move(root)), testFilesystem_(testFilesystem) {}
    int enumerate(std::vector<M1Light>* lights, std::map<int, int>* issues = nullptr);
    int set(int id, unsigned color);
private:
    int discover(std::vector<M1Light>* lights);
    int read(const std::string& path, std::string* value) const;
    int number(const std::string& path, int* value) const;
    int add(std::vector<M1Light>* lights, int id, int type, const std::string& directory);
    std::string root_;
    bool testFilesystem_;
    std::mutex mutex_;
    std::map<int, int> issues_;
};
}
